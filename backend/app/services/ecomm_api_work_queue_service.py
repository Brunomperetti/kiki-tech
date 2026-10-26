"""Read-only work queue derived exclusively from the complete Ecomm-App API capture.

Triage automation: identify missing internal editorial work without guessing
brand, GTIN, pack composition or ML/TN publication status. No writes.
"""
from collections import Counter
from datetime import datetime, timezone

from sqlalchemy import select

from ..database.models import CatalogSnapshot, EcommApiProductEdit
from ..integrations.ecomm_app.catalog_stage import STAGE_SOURCE, stage_status
from .ecomm_api_product_workspace_service import _readiness, blank_fields, review_schedule
from .ecomm_channel_coverage_service import build_channel_coverage

FILTERS = {
    "all", "ai_eligible", "identity", "draft", "ready", "untouched", "pack",
    "missing_title", "missing_brand", "missing_description", "missing_gtin",
    "ready_for_channels", "needs_completion", "review_due", "missing_source_name",
    "ml_candidate", "tn_candidate", "ml_no_exact", "tn_no_exact",
    "both_candidates", "channel_review", "neither_sku_in_snapshots"
}


def _value(raw):
    return str(raw).strip() if raw is not None else ""


def _date(raw):
    if not raw:
        return None
    return raw.isoformat() if isinstance(raw, datetime) else str(raw)


def _queue_item(id_value, sku, product_name, source_gtin, is_combo, captured_at,
                edit, duplicate_sku, coverage):
    saved = bool(edit)
    fields = edit.fields or {} if saved else {}
    source_sku_changed = bool(saved and edit.source_sku != sku)
    status = edit.status if saved else "NOT_STARTED"
    # For some products an own GTIN may not exist; missing does not
    # automatically mean noncompliant or that a GTIN should be invented.
    # Pending editorial fields are meaningful ONLY in fichas that someone
    # already started. Untouched API products are not "missing" three times:
    # they already have source names, but no commercial overlay in KIKI.
    # They are counted once under "untouched" and "needs_completion".
    missing = {
        "missing_source_name": not bool(_value(product_name)),
        "missing_brand": saved and not bool(_value(fields.get("brand"))),
        "missing_title": saved and not bool(_value(fields.get("title"))),
        "missing_description": saved and not bool(_value(fields.get("description"))),
        # GTIN absent from the API is a source-coverage issue (shown separately).
        # Only started, incomplete fichas receive a GTIN documentation flag.
        "missing_gtin": saved and not bool(
            _value(source_gtin) or _value(fields.get("proposed_gtin"))
        ),
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
    if not is_combo and not identity_issue and _value(product_name):
        flags.append("ai_eligible")
    flags.append("untouched" if not saved else "draft" if status == "DRAFT"
                 else "ready_for_channels" if status == "READY_FOR_CHANNELS" else "ready")
    # An untouched product is not an incomplete edited fiche. Separate
    # commercial production from evidence of listings in both channels.
    if saved and not _readiness({**blank_fields(), **fields})["ready"]:
        flags.append("needs_completion")
    ml = (coverage or {}).get("ml") or {"status": "UNAVAILABLE"}
    tn = (coverage or {}).get("tn") or {"status": "UNAVAILABLE"}
    if ml["status"] == "SKU_CANDIDATE":
        flags.append("ml_candidate")
    if tn["status"] == "SKU_CANDIDATE":
        flags.append("tn_candidate")
    if ml["status"] == "NO_EXACT_SKU_IN_SNAPSHOT":
        flags.append("ml_no_exact")
    if tn["status"] == "NO_EXACT_SKU_IN_SNAPSHOT":
        flags.append("tn_no_exact")
    if ml["status"] == "SKU_CANDIDATE" and tn["status"] == "SKU_CANDIDATE":
        flags.append("both_candidates")
    if (coverage or {}).get("review_required"):
        flags.append("channel_review")
    if (coverage or {}).get("combined") == "NO_EXACT_EVIDENCE_IN_BOTH_SNAPSHOTS":
        flags.append("neither_sku_in_snapshots")
    if review_schedule(edit)["review_due"]:
        flags.append("review_due")
    if identity_issue:
        priority = 0
        reason = "Identidad SKU ambigua, incompleta o modificada; revisar antes de editar."
    elif missing["missing_source_name"]:
        priority = 1
        reason = "La API no informó un nombre para esta variante: verificar antes de redactar."
    elif status == "DRAFT":
        priority = 1
        reason = "Borrador guardado pendiente de continuar o revisar."
    elif review_schedule(edit)["review_due"]:
        priority = 1
        reason = "Venció la revisión mensual: volver a corroborar fuentes y presentación."
    elif "channel_review" in flags:
        priority = 2
        reason = "La copia del canal tiene SKU repetidos, packs o conflictos. Verificar antes de vincular."
    elif status == "READY_FOR_CHANNELS":
        priority = 6
        reason = "Ficha comercial completa en KIKI; todavía falta verificar cada canal."
    elif is_combo:
        priority = 2
        reason = "Pack/combos requieren verificación de presentación y composición."
    elif status == "READY_FOR_REVIEW":
        priority = 5
        reason = "Ficha preparada para revisión interna; no equivale a publicación."
    elif "ml_no_exact" in flags or "tn_no_exact" in flags:
        priority = 3
        reason = (
            "No se encontró SKU exacto en la copia de uno o ambos canales. "
            "Antes de crear publicaciones, verificar el catálogo actual."
        )
    elif "both_candidates" in flags:
        priority = 5
        reason = "Ambos canales tienen un candidato por SKU. Confirmar identidad antes de cambiar publicaciones."
    elif "ml_candidate" in flags or "tn_candidate" in flags:
        priority = 4
        reason = "Hay al menos una coincidencia de SKU en un canal; verificar presentación y el otro canal."
    else:
        priority = 4
        reason = "Organizar ficha comercial y comprobar el estado de los canales disponibles."
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
        "source_name_present": bool(_value(product_name)),
        "commercial_edit_started": saved,
        "channel_coverage": coverage or {
            "ml": {"status": "UNAVAILABLE"},
            "tn": {"status": "UNAVAILABLE"},
            "combined": "SOURCES_UNAVAILABLE", "review_required": False,
        },
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
    channel_matrix = build_channel_coverage(db, pages)
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
                    variant.get("is_combo") is True or parent.get("is_combo") is True,
                    p.get("captured_at"), edits.get(ecomm_id),
                    bool(sku and sku_owners[sku.casefold()] > 1),
                    channel_matrix["items_by_id"].get(ecomm_id),
                )
                counts["total"] += 1
                counts["source_name_present"] += int(item["source_name_present"])
                counts["source_name_missing"] += int(not item["source_name_present"])
                counts["editorial_started"] += int(item["commercial_edit_started"])
                counts["editorial_brand_saved"] += int(bool(item["proposed_brand"]))
                counts["editorial_title_saved"] += int(bool(item["proposed_title"]))
                counts["editorial_description_saved"] += int(
                    bool(_value((edits.get(ecomm_id).fields or {}).get("description")))
                    if edits.get(ecomm_id) else False
                )
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
            "source_name_present": counts["source_name_present"],
            "source_name_missing": counts["source_name_missing"],
            "editorial_started": counts["editorial_started"],
            "editorial_brand_saved": counts["editorial_brand_saved"],
            "editorial_title_saved": counts["editorial_title_saved"],
            "editorial_description_saved": counts["editorial_description_saved"],
            "gtin_in_api_capture": counts["gtin_in_api_capture"],
            "gtin_unavailable_in_api_capture": counts["gtin_unavailable_in_api_capture"],
        },
        "channel_coverage": {
            "summary": channel_matrix["summary"],
            "sources": channel_matrix["sources"],
            "policy": channel_matrix["policy"],
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
            "Se cruzan los ID/SKU de Ecomm API con copias ML API y TN CSV. "
            "Los cruces son candidatos, no publicaciones certificadas; un SKU "
            "ausente en un snapshot no equivale a producto no publicado. "
            "Los nombres ya presentes en la API no son títulos faltantes. "
            "Las alertas de marca, título y descripción se refieren SOLO a fichas "
            "que el equipo comenzó a editar y todavía no completó. "
            "La falta de marca en KIKI no prueba falta de marca del fabricante. "
            "Los packs y SKUs ambiguos "
            "requieren revisión. No escribe en Ecomm, ML ni Tiendanube."
        ),
    }
