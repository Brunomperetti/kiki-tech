"""Review-only opportunities where an ML GTIN is shared but a SKU is unique.

A repeated GTIN can be present on multiple commercial offers or due to poor
source data. A single exact SKU in two snapshots is *review evidence*, never
authorization to assign manufacturer brand or link stock. This report has no
database access and cannot modify any source.
"""
from collections import Counter, defaultdict
import re

from ...services.tiendanube_quality_audit_service import gtin_status
from ...services.tiendanube_assisted_match_service import variant_conflict
from .catalog_comparison import _str
from .commercial_audit import _brand_class

_LIMIT = 12
_MLA = re.compile(r"^(MLA\d+)(?:#\d+)?$", re.IGNORECASE)


def _ml_id(value):
    match = _MLA.match(_str(value))
    return match.group().upper() if match else ""


def _key(value):
    return _str(value).casefold()


def shared_gtin_sku_review(matched, owners_sku, owners_ean, owners_mla,
                           ml_rows, edima_brands):
    counts = Counter()
    all_review_leads = defaultdict(list)
    rejected = []
    for row in ml_rows:
        gtin = _str(row.get("ean"))
        if not gtin or gtin_status(gtin) != "VALID_CHECK_DIGIT":
            continue
        gtin_ids = owners_ean.get(gtin, set())
        if len(gtin_ids) <= 1:
            continue
        counts["shared_gtin_ml_rows"] += 1
        mla = _ml_id(row.get("external_id"))
        edima_names = {
            _str(brand).casefold() for brand in edima_brands.get(mla, set())
        }
        ml_brand = _str(row.get("brand"))
        if len(edima_names) > 1 or (
            _brand_class(ml_brand) == "PRESENT" and edima_names
            and ml_brand.casefold() not in edima_names
        ):
            counts["conflicting_listing_brands"] += 1
            continue
        brand = (
            ml_brand if _brand_class(ml_brand) == "PRESENT"
            else next(iter(edima_brands[mla])) if len(edima_names) == 1 else ""
        )
        if _brand_class(brand) != "PRESENT":
            counts["no_brand_available"] += 1
            continue

        sku_candidates = {
            owner
            for field in ("variant_sku", "sku_effective", "sku", "sku_product")
            for owner in owners_sku.get(_key(row.get(field)), set())
            if _key(row.get(field))
        }
        if len(sku_candidates) != 1:
            counts["no_unique_exact_sku"] += 1
            continue
        counts["unique_sku_despite_shared_gtin"] += 1
        owner = next(iter(sku_candidates))
        variant_sku = _key(row.get("variant_sku"))
        is_variant = (
            bool(variant_sku)
            and owners_sku.get(variant_sku, set()) == {owner}
        )
        if is_variant:
            counts["explicit_unique_variant_sku"] += 1
        else:
            counts["unique_sku_without_variant_proof"] += 1

        mla_ids = owners_mla.get(mla, set())
        if owner not in gtin_ids or (mla_ids and mla_ids != {owner}):
            counts["identity_contradiction"] += 1
            if len(rejected) < _LIMIT:
                rejected.append({
                    "mla": mla,
                    "gtin": gtin,
                    "sku": _str(row.get("variant_sku") or row.get("sku_effective") or row.get("sku")),
                    "gtin_owner_count": len(gtin_ids),
                    "reason": "SKU no pertenece al conjunto GTIN, o referencia MLA histórica contradictoria.",
                })
            continue
        counts["sku_inside_gtin_owners_no_mla_conflict"] += 1
        product = matched.get(owner)
        if not product:
            counts["no_stable_ecomm_id"] += 1
            continue
        historical, variant = product
        if _brand_class(historical.get("brand")) == "PRESENT":
            counts["already_branded_ecomm"] += 1
            continue
        if variant_conflict(
            historical.get("name"),
            historical.get("sku_variant") or historical.get("sku_effective") or historical.get("sku"),
            row.get("title"),
            row.get("variant_sku") or "",
        ):
            counts["presentation_conflict"] += 1
            continue
        counts["sku_consistent_missing_brand_rows"] += 1
        all_review_leads[owner].append({
            "ecomm_id": owner,
            "ecomm_sku": _str(historical.get("sku_variant") or historical.get("sku_effective") or historical.get("sku")),
            "ecomm_name": _str(historical.get("name")),
            "ml_sku": _str(row.get("variant_sku") or row.get("sku_effective") or row.get("sku")),
            "ml_title": _str(row.get("title")),
            "mla": mla,
            "shared_gtin": gtin,
            "shared_gtin_ecomm_owner_count": len(gtin_ids),
            "ml_brand": brand,
            "brand_source": "MERCADOLIBRE_API" if _brand_class(ml_brand) == "PRESENT" else "EDIMA_LINKAGE",
            "exact_variant_sku": is_variant,
            "is_combo": variant.get("is_combo") if isinstance(variant.get("is_combo"), bool) else None,
            "review_status": "NEEDS_HUMAN_VERIFICATION",
        })

    candidates = []
    for owner in sorted(all_review_leads):
        rows = all_review_leads[owner]
        if len({_key(r["ml_brand"]) for r in rows}) != 1:
            counts["conflicting_brands_same_ecomm"] += 1
            continue
        counts["possible_ecomm_brand_review_ids"] += 1
        if len(candidates) < _LIMIT:
            sample = rows[0]
            candidates.append({
                **sample,
                "supporting_mlas": len({r["mla"] for r in rows}),
            })

    return {
        "counts": {
            "shared_gtin_ml_rows": counts["shared_gtin_ml_rows"],
            "unique_sku_despite_shared_gtin": counts["unique_sku_despite_shared_gtin"],
            "explicit_unique_variant_sku": counts["explicit_unique_variant_sku"],
            "unique_sku_without_variant_proof": counts["unique_sku_without_variant_proof"],
            "sku_inside_gtin_owners_no_mla_conflict": counts["sku_inside_gtin_owners_no_mla_conflict"],
            "no_unique_exact_sku": counts["no_unique_exact_sku"],
            "identity_contradiction": counts["identity_contradiction"],
            "no_stable_ecomm_id": counts["no_stable_ecomm_id"],
            "already_branded_ecomm": counts["already_branded_ecomm"],
            "presentation_conflict": counts["presentation_conflict"],
            "sku_consistent_missing_brand_rows": counts["sku_consistent_missing_brand_rows"],
            "possible_ecomm_brand_review_ids": counts["possible_ecomm_brand_review_ids"],
            "conflicting_brands_same_ecomm": counts["conflicting_brands_same_ecomm"],
            "no_brand_available": counts["no_brand_available"],
        },
        "review_leads": candidates,
        "rejected_samples": rejected,
        "sample_limit": _LIMIT,
        "mode": "HYPOTHESIS_REQUIRES_MANUAL_VERIFICATION",
        "policy": (
            "Un SKU idéntico y único puede orientar una investigación si el GTIN "
            "está compartido; NO valida producto, variante, fabricante ni marca. "
            "Se excluyen señales de identidad contradictorias y marcas divergentes. "
            "Los casos de variantes y combos necesitan validación específica. "
            "No se modifica ni aprueba información de KIKI, Ecomm-App o Mercado Libre."
        ),
    }
