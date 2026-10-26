"""Read-only, Ecomm-variant-first coverage matrix for ML API and TN CSV.

A SKU match is NOT a verified linkage or proof of a correct listing. Missing
SKU evidence in old snapshots does NOT prove an item is unpublished. Never
use the historical Ecomm XLSX or ML spreadsheet as a fallback.
"""
from collections import Counter, defaultdict

from sqlalchemy import select

from ..database.models import CatalogSnapshot
from ..integrations.ecomm_app.catalog_stage import STAGE_SOURCE
from .tiendanube_assisted_match_service import variant_conflict
from .ecomm_api_product_workspace_service import _gtin_check_digit_valid


def _text(value):
    return str(value).strip() if value is not None else ""


def _sku(value):
    return _text(value).casefold()


def _valid_ean(value):
    code = _text(value)
    return code if code and _gtin_check_digit_valid(code) else ""


def _review_candidate(candidate, source_name, source_sku, *, is_combo, source_gtin):
    # SKU never establishes equality of presentation, pack, manufacturer or GTIN.
    actual_name = _text(candidate.get("name") or candidate.get("title"))
    if source_gtin and _text(candidate.get("ean")):
        other = _text(candidate["ean"])
        if _valid_ean(source_gtin) and _valid_ean(other) and source_gtin != other:
            return "GTIN_CONFLICT"
    if actual_name and variant_conflict(source_name, source_sku, actual_name, source_sku):
        return "PRESENTATION_CONFLICT"
    # A pack needs proof of composition; a matching string is insufficient.
    if is_combo:
        return "PACK_REVIEW"
    return "SKU_CANDIDATE"


def _channel_result(rows, *, snapshot_available, original_name, sku, is_combo,
                    source_gtin, ambiguous_api_sku, name_field, snapshot_at,
                    source):
    base = {
        "source": source, "snapshot_available": snapshot_available,
        "snapshot_at": snapshot_at,
        "status": "UNAVAILABLE", "matching_rows": 0,
        "listing_ids": [], "candidate_name": None,
        "candidate_quality": {
            "title_present": False, "brand_present": False,
            "description_present": False, "ean_present": False,
        },
        "note": "", "confirmed_listing": False,
    }
    if not snapshot_available:
        return {**base, "note": "Falta una captura del canal. No se puede afirmar si está publicado."}
    if not sku or ambiguous_api_sku:
        return {
            **base, "status": "AMBIGUOUS_API_SKU",
            "note": "El SKU Ecomm falta o tiene varios dueños. No se asignan publicaciones.",
        }
    if not rows:
        return {
            **base, "status": "NO_EXACT_SKU_IN_SNAPSHOT",
            "note": "Sin coincidencia por SKU exacto en la copia; NO prueba ausencia real de publicación.",
        }
    if len(rows) != 1:
        return {
            **base, "status": "MULTIPLE_SKU_ROWS", "matching_rows": len(rows),
            "listing_ids": [
                _text(row.get("external_id") or row.get("slug"))
                for row in rows
            ][:8],
            "note": "El SKU apunta a varias filas del canal. Revisar variantes y duplicados.",
        }
    row = rows[0]
    kind = _review_candidate(
        row, original_name, sku, is_combo=is_combo, source_gtin=source_gtin
    )
    note = {
        "SKU_CANDIDATE": "SKU único exacto, identidad comercial pendiente de verificar.",
        "PACK_REVIEW": "Pack/combos: verificar composición y presentación antes de vincular.",
        "PRESENTATION_CONFLICT": "SKU igual, posible diferencia de contenido, sabor o presentación.",
        "GTIN_CONFLICT": "SKU igual, pero los GTIN válidos informados son diferentes.",
    }[kind]
    return {
        **base, "status": kind, "matching_rows": 1,
        "listing_ids": [_text(row.get("external_id") or row.get("slug"))],
        "candidate_name": _text(row.get(name_field)) or None,
        "candidate_quality": {
            "title_present": bool(_text(row.get(name_field))),
            "brand_present": bool(_text(row.get("brand"))),
            "description_present": bool(row.get("description_present")) if source == "TIENDANUBE_CSV" else False,
            "ean_present": bool(_valid_ean(row.get("ean_raw") or row.get("ean"))),
        },
        "note": note, "confirmed_listing": False,
        "listing_statuses": [_text(row.get("status"))] if source == "MERCADOLIBRE_API" else [],
    }


def build_channel_coverage(db, pages):
    """Map all API variant IDs to independently classified channel evidence."""
    ml_snap = db.scalar(select(CatalogSnapshot).where(
        CatalogSnapshot.source == "MERCADOLIBRE_API"
    ))
    tn_snap = db.scalar(select(CatalogSnapshot).where(
        CatalogSnapshot.source == "TIENDANUBE"
    ))
    ml_rows = ml_snap.payload if ml_snap and isinstance(ml_snap.payload, list) else []
    tn_rows = tn_snap.payload if tn_snap and isinstance(tn_snap.payload, list) else []
    ml_available = bool(ml_rows)
    tn_available = bool(tn_rows)

    sku_owners = Counter()
    for page in pages:
        for parent in page.get("items") or []:
            for v in parent.get("variants") or []:
                if isinstance(v, dict) and not v.get("invalid") and _sku(v.get("sku")):
                    sku_owners[_sku(v["sku"])] += 1

    ml_index = defaultdict(list)
    ml_variations_missing_sku = 0
    for row in ml_rows:
        if not isinstance(row, dict):
            continue
        external_id = _text(row.get("external_id"))
        # Parent SKU cannot identify a Mercado Libre variation without its
        # own SELLER_SKU. Never create spurious coverage by inherited SKU.
        variant_sku = _sku(row.get("variant_sku"))
        if "#" in external_id:
            if not variant_sku:
                ml_variations_missing_sku += 1
                continue
            key = variant_sku
        else:
            key = variant_sku or _sku(
                row.get("sku_product") or row.get("sku_effective") or row.get("sku")
            )
        if key:
            ml_index[key].append(row)

    tn_index = defaultdict(list)
    for row in tn_rows:
        if isinstance(row, dict) and _sku(row.get("sku")):
            tn_index[_sku(row["sku"])].append(row)

    records = {}
    totals = {"ml": Counter(), "tn": Counter(), "combined": Counter()}
    for page in pages:
        for parent in page.get("items") or []:
            if not isinstance(parent, dict):
                continue
            for var in parent.get("variants") or []:
                if not isinstance(var, dict) or var.get("invalid"):
                    continue
                ident = _text(var.get("id"))
                sku = _text(var.get("sku"))
                if not ident:
                    continue
                name = _text(parent.get("description") or var.get("variant_description"))
                combo = var.get("is_combo") is True or parent.get("is_combo") is True
                gtin = _text(var.get("gtin") or var.get("barcode"))
                ambiguous = bool(sku and sku_owners[_sku(sku)] != 1)
                ml = _channel_result(
                    ml_index.get(_sku(sku), []), snapshot_available=ml_available,
                    original_name=name, sku=sku, is_combo=combo,
                    source_gtin=gtin, ambiguous_api_sku=ambiguous,
                    name_field="title",
                    snapshot_at=ml_snap.updated_at.isoformat() if ml_snap else None,
                    source="MERCADOLIBRE_API",
                )
                tn = _channel_result(
                    tn_index.get(_sku(sku), []), snapshot_available=tn_available,
                    original_name=name, sku=sku, is_combo=combo,
                    source_gtin=gtin, ambiguous_api_sku=ambiguous,
                    name_field="name",
                    snapshot_at=tn_snap.updated_at.isoformat() if tn_snap else None,
                    source="TIENDANUBE_CSV",
                )
                both_candidate = ml["status"] == "SKU_CANDIDATE" and tn["status"] == "SKU_CANDIDATE"
                neither_exact = (
                    ml["status"] == "NO_EXACT_SKU_IN_SNAPSHOT"
                    and tn["status"] == "NO_EXACT_SKU_IN_SNAPSHOT"
                )
                risk = any(
                    item["status"] in (
                        "MULTIPLE_SKU_ROWS", "PRESENTATION_CONFLICT",
                        "GTIN_CONFLICT", "PACK_REVIEW", "AMBIGUOUS_API_SKU"
                    )
                    for item in (ml, tn)
                )
                combined = (
                    "IDENTITY_REVIEW" if risk else
                    "BOTH_CHANNELS_CANDIDATE" if both_candidate else
                    "NO_EXACT_EVIDENCE_IN_BOTH_SNAPSHOTS" if neither_exact else
                    "SOURCES_UNAVAILABLE" if not ml_available and not tn_available else
                    "PARTIAL_CHANNEL_EVIDENCE"
                )
                totals["ml"][ml["status"]] += 1
                totals["tn"][tn["status"]] += 1
                totals["combined"][combined] += 1
                records[ident] = {
                    "ecomm_id": ident, "sku": sku, "ml": ml, "tn": tn,
                    "combined": combined, "review_required": risk,
                    "never_confirmed_by_sku_alone": True,
                }

    return {
        "items_by_id": records,
        "summary": {
            "api_variants": len(records),
            "ml": dict(totals["ml"]), "tn": dict(totals["tn"]),
            "combined": dict(totals["combined"]),
            "ml_rows_unmatchable_variation_sku": ml_variations_missing_sku,
        },
        "sources": {
            "ecomm": STAGE_SOURCE,
            "ml": {
                "name": "MERCADOLIBRE_API", "available": ml_available,
                "updated_at": ml_snap.updated_at.isoformat() if ml_snap else None,
                "rows": len(ml_rows),
            },
            "tn": {
                "name": "TIENDANUBE_CSV", "available": tn_available,
                "updated_at": tn_snap.updated_at.isoformat() if tn_snap else None,
                "rows": len(tn_rows),
            },
        },
        "policy": (
            "Cobertura orientativa por variante API y SKU exacto, no vínculos aprobados. "
            "Un SKU no confirma presentación o composición; múltiples publicaciones "
            "o packs exigen revisión. Una copia antigua sin coincidencia no demuestra "
            "que el producto no esté publicado. No se consulta Excel Ecomm ni ML."
        ),
    }
