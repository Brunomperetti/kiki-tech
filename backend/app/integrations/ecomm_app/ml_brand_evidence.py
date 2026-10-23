"""Read-only ML brand evidence for Ecomm products with missing historical brand.

EDIMA exports brand; current ML snapshots can supply it once transformer stores
the BRAND attribute. Review leads require uniquely owned exact identifiers.
A listing is NOT a variant ID and identical family SKU prefixes prove nothing.
"""
from collections import Counter, defaultdict
from datetime import timezone
import re

from sqlalchemy import select

from ...database.models import CatalogSnapshot
from ...services.tiendanube_assisted_match_service import variant_conflict
from ...services.tiendanube_quality_audit_service import gtin_status
from .catalog_comparison import _format_key, _legacy_sku, _str
from .catalog_hybrid_preview import _indexes
from .catalog_stage import STAGE_SOURCE, stage_status
from .commercial_audit import _brand_class
from .ml_shared_gtin_review import shared_gtin_sku_review
from .combo_gtin_audit import combo_gtin_conflict_audit

SAMPLE_LIMIT = 20
MLA_RE = re.compile(r"^(MLA\d+)(?:#\d+)?$", re.IGNORECASE)


def _mla(value):
    matched = MLA_RE.fullmatch(_str(value))
    return matched.group(1).upper() if matched else ""


def _sku(value):
    return _str(value).casefold()


def _ean(value):
    value = _str(value)
    return value if gtin_status(value) == "VALID_CHECK_DIGIT" else ""


def _skus(product):
    return {
        _sku(value)
        for value in [
            product.get("sku"),
            product.get("sku_effective"),
            product.get("sku_variant"),
            product.get("sku_product"),
            *(product.get("sku_aliases") or []),
        ] if _sku(value)
    }


def _row_skus(row):
    return {
        _sku(row.get(field))
        for field in ("variant_sku", "sku_effective", "sku", "sku_product")
        if _sku(row.get(field))
    }


def _edima_brands(rows):
    brands = defaultdict(set)
    for row in rows:
        mla = _mla(row.get("external_id"))
        if mla and _brand_class(row.get("brand")) == "PRESENT":
            brands[mla].add(_str(row["brand"]))
    return brands


def ml_brand_evidence_report(pages, historical, ml_rows, edima_rows, ml_source):
    state = stage_status(pages)
    if not state["complete"] or state["quality"]["parents"] != state["expected_parents"]:
        raise ValueError("La copia API Ecomm debe estar completa para revisar marcas.")
    if not isinstance(historical, list) or not historical:
        raise ValueError("Falta el catálogo histórico Ecomm-App.")

    prior, api = _indexes(pages, historical)
    matched = {}
    owners_sku = defaultdict(set)
    owners_ean = defaultdict(set)
    owners_mla = defaultdict(set)
    for ecomm_id, records in prior.items():
        if len(records) != 1 or len(api.get(ecomm_id, [])) != 1:
            continue
        product, (_, variant) = records[0], api[ecomm_id][0]
        # Cases with a substantive SKU change remain separate.
        historical_sku, api_sku = _legacy_sku(product), _str(variant.get("sku"))
        if not historical_sku or not api_sku or _format_key(historical_sku) != _format_key(api_sku):
            continue
        matched[ecomm_id] = (product, variant)
        for sku in _skus(product):
            owners_sku[sku].add(ecomm_id)
        for ean in [product.get("ean"), *(product.get("ean_aliases") or [])]:
            value = _ean(ean)
            if value:
                owners_ean[value].add(ecomm_id)
        for erow in product.get("ecomm_rows") or []:
            if not isinstance(erow, dict):
                continue
            # Historical links are *only clues*, not verified ML variant IDs.
            for field in ("listing_id", "marketplace_id"):
                mla = _mla(erow.get(field))
                if mla:
                    owners_mla[mla].add(ecomm_id)

    # Unique brand per publication; divergent EDIMA brands for a shared MLA
    # are explicitly withheld rather than arbitrarily selecting one.
    edima_brands = _edima_brands(edima_rows)
    counters = Counter()
    for row in ml_rows:
        if _brand_class(row.get("brand")) == "PRESENT":
            counters["ml_rows_with_brand"] += 1
    for row in edima_rows:
        if _brand_class(row.get("brand")) == "PRESENT":
            counters["edima_rows_with_brand"] += 1

    contributions = defaultdict(list)
    def collect(ecomm_id, brand, mla, title, method, source):
        if ecomm_id not in matched or _brand_class(brand) != "PRESENT":
            return
        product, variant = matched[ecomm_id]
        if _brand_class(product.get("brand")) == "PRESENT":
            return
        if variant_conflict(
            product.get("name"), _legacy_sku(product), title, ""
        ):
            counters["presentation_conflicts"] += 1
            return
        contributions[ecomm_id].append({
            "brand": _str(brand),
            "mla": mla,
            "title": _str(title),
            "match_basis": method,
            "source": source,
        })

    # Preserve EDIMA distinct per-MLA brands even when API has only one
    # listing row and no brand in the transformed snapshot.
    for row in ml_rows:
        mla = _mla(row.get("external_id"))
        if not mla:
            continue
        ml_brand = _str(row.get("brand")) if _brand_class(row.get("brand")) == "PRESENT" else ""
        edima_set = {_str(v).casefold() for v in edima_brands.get(mla, set())}
        if len(edima_set) > 1 or (ml_brand and edima_set and ml_brand.casefold() not in edima_set):
            counters["conflicting_listing_brands"] += 1
            continue
        if ml_brand:
            brand, source = ml_brand, ml_source
        elif len(edima_set) == 1:
            brand, source = next(iter(edima_brands[mla])), "EDIMA_LINKAGE"
        else:
            continue

        skus = _row_skus(row)
        sku_candidates = {
            owner for sku in skus for owner in owners_sku.get(sku, set())
        }
        # Effective variant SKU may be absent: a product-level SKU in ML with
        # multiple Ecomm owners is never considered unique.
        direct = next(iter(sku_candidates)) if len(sku_candidates) == 1 else None
        ean = _ean(row.get("ean"))
        ean_candidates = owners_ean.get(ean, set()) if ean else set()
        by_ean = next(iter(ean_candidates)) if len(ean_candidates) == 1 else None
        by_mla = next(iter(owners_mla[mla])) if len(owners_mla[mla]) == 1 else None

        # If two positive independent signals point to different products,
        # withhold the whole listing. No weak signal can override a conflict.
        positives = {candidate for candidate in (direct, by_ean, by_mla) if candidate}
        if len(positives) > 1 or len(sku_candidates) > 1 or len(ean_candidates) > 1 or len(owners_mla[mla]) > 1:
            counters["ambiguous_or_conflicting_identifiers"] += 1
            continue
        if not positives:
            continue
        owner = next(iter(positives))
        method = (
            "UNIQUE_EXACT_ML_SKU" if direct else
            "UNIQUE_VALID_ML_GTIN" if by_ean else
            "UNIQUE_HISTORICAL_MLA_REFERENCE"
        )
        collect(owner, brand, mla, row.get("title"), method, source)
        counters["listing_rows_with_matching_identity"] += 1

    # EDIMA-only rows, useful when the ML snapshot is old or doesn't include
    # a given MLA. Exact unique valid GTIN or historical MLA reference only.
    mlas_in_ml = {_mla(row.get("external_id")) for row in ml_rows}
    owners_edima_ean = defaultdict(set)
    for row in edima_rows:
        values = {_ean(e) for e in row.get("gtins") or []}
        values.discard("")
        if len(values) == 1:
            owners_edima_ean[next(iter(values))].add(_mla(row.get("external_id")))
    for row in edima_rows:
        mla = _mla(row.get("external_id"))
        if not mla or mla in mlas_in_ml:
            continue
        brand_set = {_str(v).casefold() for v in edima_brands.get(mla, set())}
        if len(brand_set) != 1:
            continue
        brand = next(iter(edima_brands[mla]))
        eans = {_ean(e) for e in row.get("gtins") or []}
        eans.discard("")
        owner_from_ean = None
        if len(eans) == 1:
            ean = next(iter(eans))
            ecomm_ids = owners_ean.get(ean, set())
            if len(ecomm_ids) == 1 and owners_edima_ean[ean] == {mla}:
                owner_from_ean = next(iter(ecomm_ids))
        owner_from_mla = next(iter(owners_mla[mla])) if len(owners_mla[mla]) == 1 else None
        owners = {x for x in (owner_from_ean, owner_from_mla) if x}
        if len(owners) > 1 or len(owners_mla[mla]) > 1:
            counters["ambiguous_or_conflicting_identifiers"] += 1
            continue
        if not owners:
            continue
        collect(next(iter(owners)), brand, mla, row.get("title"),
                "UNIQUE_VALID_EDIMA_GTIN" if owner_from_ean else "UNIQUE_HISTORICAL_MLA_REFERENCE",
                "EDIMA_LINKAGE")

    samples = []
    for ecomm_id in sorted(contributions):
        rows = contributions[ecomm_id]
        distinct = {_str(x["brand"]).casefold() for x in rows}
        if len(distinct) != 1:
            counters["ecomm_brand_conflicts"] += 1
            continue
        counters["unique_brand_review_leads"] += 1
        product, variant = matched[ecomm_id]
        if variant.get("is_combo") is True:
            counters["combo_leads"] += 1
        if len(samples) < SAMPLE_LIMIT:
            sample = rows[0]
            samples.append({
                "ecomm_id": ecomm_id,
                "ecomm_name": _str(product.get("name")),
                "ecomm_sku": _legacy_sku(product),
                "ml_brand": sample["brand"],
                "mla": sample["mla"],
                "ml_title": sample["title"],
                "ml_source": sample["source"],
                "match_basis": sample["match_basis"],
                "is_combo": variant.get("is_combo") if isinstance(variant.get("is_combo"), bool) else None,
                "supporting_listings": len({r["mla"] for r in rows}),
                "review_status": "NEEDS_HUMAN_VERIFICATION",
            })

    counts_missing = sum(
        _brand_class(old[0].get("brand")) != "PRESENT"
        for key, old in prior.items()
        if len(old) == 1 and len(api.get(key, [])) == 1
    )
    blockers = ml_brand_blocker_diagnostics(
        matched, owners_sku, owners_ean, owners_mla,
        ml_rows, edima_rows, edima_brands,
    )
    shared_gtin = shared_gtin_sku_review(
        matched, owners_sku, owners_ean, owners_mla, ml_rows, edima_brands
    )
    combo_audit = combo_gtin_conflict_audit(
        matched, owners_sku, owners_ean, owners_mla, ml_rows,
        edima_brands, pages,
    )
    return {
        "combo_gtin_audit": combo_audit,
        "shared_gtin_review": shared_gtin,
        "diagnostics": blockers,
        "available": bool(ml_rows or edima_rows),
        "mode": "REVIEW_ONLY_ML_BRAND_EVIDENCE",
        "activation_allowed": False,
        "sources": {
            "ml_source": ml_source,
            "ml_rows": len(ml_rows),
            "ml_rows_with_brand": counters["ml_rows_with_brand"],
            "edima_rows": len(edima_rows),
            "edima_rows_with_brand": counters["edima_rows_with_brand"],
        },
        "summary": {
            "missing_historical_brand": counts_missing,
            "unique_brand_review_leads": counters["unique_brand_review_leads"],
            "combo_leads": counters["combo_leads"],
            "conflicting_listing_brands": counters["conflicting_listing_brands"],
            "ambiguous_identifiers": counters["ambiguous_or_conflicting_identifiers"],
            "conflicting_brands_per_ecomm_id": counters["ecomm_brand_conflicts"],
        },
        "candidates": samples,
        "sampling_limit": SAMPLE_LIMIT,
        "policy": (
            "Marcas de publicaciones ML o del reporte EDIMA, NO marcas de fabricante "
            "verificadas. Exigir SKU único, GTIN válido y único o referencia MLA "
            "histórica única; señales incompatibles y marcas contradictorias se excluyen. "
            "MLA no identifica la variante. Combos requieren revisión. "
            "No se crea ni aprueba ningún vínculo, alias, stock o marca."
        ),
    }


def ml_brand_blocker_diagnostics(matched, owners_sku, owners_ean, owners_mla,
                                 ml_rows, edima_rows, edima_brands):
    """Explain discarded ML rows without weakening a single identity gate.

    Reasons overlap: one row may have a shared historical MLA AND a shared
    product SKU. Preserve the full cause list while sampling at most 8 rows.
    This routine only analyzes the existing in-memory snapshot dictionaries.
    """
    diagnostics = Counter()
    examples = []
    ambiguous_mlas = set()
    available_edima_mlas = {
        mla for mla, values in edima_brands.items() if len({v.casefold() for v in values}) == 1
    }
    ml_mlas = {_mla(row.get("external_id")) for row in ml_rows}
    for row in ml_rows:
        mla = _mla(row.get("external_id"))
        if not mla:
            diagnostics["invalid_mla_rows"] += 1
            continue
        brands_edima = {brand.casefold() for brand in edima_brands.get(mla, set())}
        ml_has_brand = _brand_class(row.get("brand")) == "PRESENT"
        if mla in available_edima_mlas:
            diagnostics["rows_with_edima_mla"] += 1
        if len(brands_edima) > 1 or (
            ml_has_brand and brands_edima and _str(row["brand"]).casefold() not in brands_edima
        ):
            diagnostics["brand_disagreements"] += 1
            continue
        if not ml_has_brand and len(brands_edima) != 1:
            diagnostics["rows_without_brand_in_either_source"] += 1
            continue
        diagnostics["rows_with_brand_available"] += 1
        skus = _row_skus(row)
        sku_candidates = {
            owner for sku in skus for owner in owners_sku.get(sku, set())
        }
        gtin = _ean(row.get("ean"))
        ean_candidates = owners_ean.get(gtin, set()) if gtin else set()
        mla_candidates = owners_mla.get(mla, set())
        unique_signals = {
            next(iter(owners))
            for owners in (sku_candidates, ean_candidates, mla_candidates)
            if len(owners) == 1
        }
        reason_codes = []
        if len(mla_candidates) > 1:
            reason_codes.append("SHARED_HISTORICAL_MLA")
        if len(sku_candidates) > 1:
            reason_codes.append("SHARED_SKU")
        if len(ean_candidates) > 1:
            reason_codes.append("SHARED_GTIN")
        if len(unique_signals) > 1:
            reason_codes.append("IDENTITY_SIGNAL_CONFLICT")
        if reason_codes:
            diagnostics["ambiguous_ml_rows"] += 1
            ambiguous_mlas.add(mla)
            for code in reason_codes:
                diagnostics[code] += 1
            direct_variant = _sku(row.get("variant_sku"))
            direct_owners = owners_sku.get(direct_variant, set()) if direct_variant else set()
            if len(mla_candidates) > 1 and len(direct_owners) == 1:
                diagnostics["shared_mla_with_unique_variant_sku"] += 1
            if len(examples) < 8:
                examples.append({
                    "mla": mla,
                    "ml_sku": _str(row.get("variant_sku") or row.get("sku_effective") or row.get("sku")),
                    "reason_codes": reason_codes,
                    "sku_owner_count": len(sku_candidates),
                    "gtin_owner_count": len(ean_candidates),
                    "historical_mla_owner_count": len(mla_candidates),
                    "unique_variant_sku_present": len(direct_owners) == 1,
                    "classification": "HUMAN_REVIEW_ONLY",
                })
            continue
        if not unique_signals:
            diagnostics["rows_without_unique_identity"] += 1
            continue
        owner = next(iter(unique_signals))
        product = matched.get(owner)
        if not product:
            diagnostics["rows_not_stable_ecomm_id"] += 1
        elif _brand_class(product[0].get("brand")) == "PRESENT":
            diagnostics["rows_matching_already_branded_ecomm"] += 1
        else:
            diagnostics["rows_pointing_to_missing_brand_ecomm"] += 1

    diagnostics["edima_only_rows"] = sum(
        _mla(row.get("external_id")) not in ml_mlas for row in edima_rows
    )
    return {
        "counts": {
            "ml_rows_with_brand_available": diagnostics["rows_with_brand_available"],
            "ml_rows_with_matching_edima_mla": diagnostics["rows_with_edima_mla"],
            "ml_rows_without_brand_in_either_source": diagnostics["rows_without_brand_in_either_source"],
            "ml_rows_with_brand_disagreements": diagnostics["brand_disagreements"],
            "ml_rows_ambiguous": diagnostics["ambiguous_ml_rows"],
            "distinct_mlas_ambiguous": len(ambiguous_mlas),
            "shared_historical_mla": diagnostics["SHARED_HISTORICAL_MLA"],
            "shared_sku": diagnostics["SHARED_SKU"],
            "shared_gtin": diagnostics["SHARED_GTIN"],
            "identity_signal_conflicts": diagnostics["IDENTITY_SIGNAL_CONFLICT"],
            "shared_mla_with_unique_variant_sku": diagnostics["shared_mla_with_unique_variant_sku"],
            "ml_rows_without_unique_identity": diagnostics["rows_without_unique_identity"],
            "ml_rows_matching_already_branded_ecomm": diagnostics["rows_matching_already_branded_ecomm"],
            "ml_rows_pointing_to_missing_brand_ecomm": diagnostics["rows_pointing_to_missing_brand_ecomm"],
            "edima_rows_not_in_ml_snapshot": diagnostics["edima_only_rows"],
        },
        "examples": examples,
        "sample_limit": 8,
        "policy": (
            "Una misma fila puede presentar múltiples motivos y las cantidades "
            "por causa NO son sumables. Los MLA compartidos pueden representar "
            "variantes de una publicación. Un SKU de variante único es solo una "
            "pista: no se promueve a vínculo ni se asigna ninguna marca."
        ),
    }


class EcommMlBrandEvidenceService:
    def __init__(self, db):
        self.db = db

    def report(self):
        snapshots = {}
        captured_at = {}
        for name in (STAGE_SOURCE, "ECOMM_APP", "MERCADOLIBRE_API",
                     "MERCADOLIBRE", "EDIMA_LINKAGE"):
            row = self.db.scalar(
                select(CatalogSnapshot).where(CatalogSnapshot.source == name)
            )
            snapshots[name] = row.payload if row else []
            captured_at[name] = (
                row.updated_at.replace(tzinfo=timezone.utc).isoformat()
                if row and row.updated_at and row.updated_at.tzinfo is None
                else row.updated_at.isoformat() if row and row.updated_at else None
            )
        # Prefer ML API if present, but use Excel fallback when API absent.
        ml_source = "MERCADOLIBRE_API" if snapshots["MERCADOLIBRE_API"] else "MERCADOLIBRE"
        result = ml_brand_evidence_report(
            snapshots[STAGE_SOURCE], snapshots["ECOMM_APP"],
            snapshots[ml_source], snapshots["EDIMA_LINKAGE"], ml_source,
        )
        result["source_dates"] = {
            "ecomm_api_stage": captured_at[STAGE_SOURCE],
            "ecomm_historical": captured_at["ECOMM_APP"],
            "ml_snapshot": captured_at[ml_source],
            "edima": captured_at["EDIMA_LINKAGE"],
        }
        return result
