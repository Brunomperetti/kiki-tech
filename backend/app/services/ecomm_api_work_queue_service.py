"""Read-only work queue derived exclusively from the complete Ecomm-App API capture.

Triage automation: identify missing internal editorial work without guessing
brand, GTIN, pack composition or ML/TN publication status. No writes.
"""
from collections import Counter
from datetime import datetime, timezone

from sqlalchemy import select

from ..database.models import CatalogSnapshot, EcommApiProductEdit
from ..integrations.ecomm_app.catalog_stage import STAGE_SOURCE, stage_status

FILTERS = {
    "all", "ai_eligible", "identity", "draft", "ready", "untouched", "pack",
    "missing_title", "missing_brand", "missing_description", "missing_gtin"
}


def _value(raw):
    return str(raw).strip() if raw is not None else ""


def _date(raw):
    if not raw:
        return None
    return raw.isoformat() if isinstance(raw, datetime) else str(raw)


def _queue_item(id_value, sku, product_name, source_gtin, is_combo, captured_at,
                edit, duplicate_sku):
    saved = bool(edit)
    fields = edit.fields or {} if saved else {}
    source_sku_changed = bool(saved and edit.source_sku != sku)
    status = edit.status if saved else "NOT_STARTED"
    # For some products an own GTIN may not exist; missing does not
    # automatically mean noncompliant or that a GTIN should be invented.
    missing = {
        "missing_brand": not bool(_value(fields.get("brand"))),
        "missing_title": not bool(_value(fields.get("title"))),
        "missing_description": not bool(_value(fields.get("description"))),
        "missing_gtin": not bool(_value(source_gtin) or _value(fields.get("proposed_gtin"))),
    }
    identity_issue = duplicate_sku or source_sku_changed or not id_value or not sku
    flags = [k for k, enabled in missing.items() if enabled]
    if is_combo:
        flags.append("pack")
    if identity_issue:
        flags.append("identity")
    # Matches the guards in the batch AI preview: a unique, stable, 
    # API-identified non-combo variant. This is NOT a factual verification
    # of ingredients, GTIN, price or commercial publication readiness.
    if not is_combo and not identity_issue:
        flags.append("ai_eligible")
    flags.append("untouched" if not saved else "draft" if status == "DRAFT" else "ready")
    if identity_issue:
        priority = 0
        reason = "Identidad SKU ambigua, incompleta o modificada; revisar antes de editar."
    elif status == "DRAFT":
        priority = 1
        reason = "Borrador guardado pendiente de continuar o revisar."
    elif is_combo:
        priority = 2
        reason = "Pack/combos requieren verificación de presentación y composición."
    elif status == "READY_FOR_REVIEW":
        priority = 4
        reason = "Ficha preparada para revisión interna; no equivale a publicación."
    else:
        priority = 3
        reason = "Falta preparar los campos comerciales dentro de KIKI."
    return {
        "ecomm_id": id_value, "sku": sku, "product_name": product_name,
        "source_gtin_present": bool(_value(source_gtin)),
        "gtin_source_state": "AVAILABLE_IN_API_CAPTURE" if _value(source_gtin)
        else "NOT_AVAILABLE_IN_API_CAPTURE",
        "is_combo": bool(is_combo),
        "captured_at": captured_at,
        "status": status, "edit_version": edit.version if saved else 0,
        "proposed_brand": _value(fields.get("brand")),
        "proposed_title": _value(fields.get("title")),
        "flags": flags, "identity_issue": identity_issue,
        "priority": priority, "reason": reason,
        "last_edited_at": _date(edit.updated_at) if saved else None,
    }


def build_queue(db, *, query="", filter_name="all", page=1, limit=25):
    if filter_name not in FILTERS:
        raise ValueError("Filtro de cola desconocido.")
    if page < 1 or page > 100000 or limit < 1 or limit > 50 or len(query) > 80:
        raise ValueError("Consulta o paginación fuera de los límites.")
    capture = db.scalar(select(CatalogSnapshot).where(
        CatalogSnapshot.source == STAGE_SOURCE
    ))
    pages = capture.payload if capture else []
    status = stage_status(pages)
    if not status["complete"] or status["quality"].get("duplicate_variant_ids"):
        raise ValueError("La copia API Ecomm está incompleta o contiene IDs de variante duplicados.")

    edits = {
        x.ecomm_id: x for x in db.scalars(select(EcommApiProductEdit)).all()
    }
    sku_owners = Counter(
        _value(v.get("sku")).casefold()
        for p in pages for parent in p.get("items") or []
        for v in parent.get("variants") or []
        if isinstance(v, dict) and not v.get("invalid") and _value(v.get("sku"))
    )
    rows = []
    counts = Counter()
    term = query.casefold().strip()
    for p in pages:
        for parent in p.get("items") or []:
            if not isinstance(parent, dict):
                continue
            for variant in parent.get("variants") or []:
                if not isinstance(variant, dict) or variant.get("invalid"):
                    continue
                ecomm_id = _value(variant.get("id"))
                sku = _value(variant.get("sku"))
                item = _queue_item(
                    ecomm_id, sku, _value(parent.get("description")),
                    variant.get("gtin") or variant.get("barcode"),
                    variant.get("is_combo") is True,
                    p.get("captured_at"), edits.get(ecomm_id),
                    bool(sku and sku_owners[sku.casefold()] > 1),
                )
                counts["total"] += 1
                counts["gtin_in_api_capture"] += int(item["source_gtin_present"])
                counts["gtin_unavailable_in_api_capture"] += int(
                    not item["source_gtin_present"]
                )
                for flag in item["flags"]:
                    counts[flag] += 1
                if term and not any(term in _value(field).casefold()
                                    for field in (
                                        ecomm_id, sku, item["product_name"],
                                        item["proposed_brand"], item["proposed_title"]
                                    )):
                    continue
                if filter_name != "all" and filter_name not in item["flags"]:
                    continue
                rows.append(item)
    # Existing triage priorities remain intact; ai_eligible bypasses the 
    # initial list of packs and exposes simple variants immediately.
    # Identity safety first; saved drafts next; packs before untouched simples.
    rows.sort(key=lambda x: (x["priority"], x["sku"].casefold(), x["ecomm_id"]))
    offset = (page - 1) * limit
    return {
        "source": STAGE_SOURCE,
        "source_snapshot_at": pages[-1].get("captured_at") if pages else None,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "KIKI_INTERNAL_READ_ONLY_TRIAGE",
        "external_writes_enabled": False,
        "total": len(rows), "page": page, "limit": limit,
        "filter": filter_name, "query": query.strip(),
        "summary": {key:counts[key] for key in sorted(FILTERS - {"all"})} | {
            "total": counts["total"],
            "gtin_in_api_capture": counts["gtin_in_api_capture"],
            "gtin_unavailable_in_api_capture": counts["gtin_unavailable_in_api_capture"],
        },
        "gtin_data_quality": {
            "gtin_found_in_capture": counts["gtin_in_api_capture"],
            "gtin_unavailable_in_capture": counts["gtin_unavailable_in_api_capture"],
            "status": "NO_GTIN_EXPOSED_BY_CAPTURE"
            if counts["gtin_in_api_capture"] == 0 else "PARTIAL_OR_COMPLETE_COVERAGE",
            "meaning": (
                "Estos campos NO llegaron en la copia API. No se puede concluir "
                "que los productos carezcan de EAN ni iniciar una corrección masiva."
                if counts["gtin_in_api_capture"] == 0 else
                "La presencia de GTIN corresponde a la copia API, no equivale "
                "a validación de códigos originales de producto."
            ),
        },
        "items": rows[offset:offset + limit],
        "policy": (
            "La cola se deriva exclusivamente de la copia Ecomm-App por API y "
            "de fichas guardadas en KIKI PostgreSQL. Un GTIN que no aparece en "
            "la captura NO es evidencia de ausencia de EAN original. "
            "La falta de marca en KIKI no prueba falta de marca del fabricante. "
            "Los packs y SKUs ambiguos "
            "requieren revisión. No escribe en Ecomm, ML ni Tiendanube."
        ),
    }
