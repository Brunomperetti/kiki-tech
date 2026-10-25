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
    "all", "identity", "draft", "ready", "untouched", "pack",
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
        "summary": dict(counts),
        "items": rows[offset:offset + limit],
        "policy": (
            "La cola se deriva exclusivamente de la copia Ecomm-App por API y "
            "de fichas guardadas en KIKI PostgreSQL. La falta de GTIN o marca "
            "no supone que el dato deba inventarse. Los packs y SKUs ambiguos "
            "requieren revisión. No escribe en Ecomm, ML ni Tiendanube."
        ),
    }
