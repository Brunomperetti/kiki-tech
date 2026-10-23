"""Read-only review of contradictory ML GTIN versus Ecomm SKU with combo flags.

The public Ecomm inventory-stage snapshot retains parent/variant is_combo, SKU,
GTIN and stock but contains NO bill-of-materials/component membership field.
Consequently the analysis can flag *possible* combo/component patterns, never
identify or confirm a component or overwrite any catalogue link.
"""
from collections import Counter, defaultdict

from ...services.sku_family_service import compare_family_skus
from ...services.tiendanube_quality_audit_service import gtin_status
from .catalog_comparison import _str
from .commercial_audit import _brand_class
from .ml_shared_gtin_review import _key, _ml_id

SAMPLE_LIMIT = 12


def _combo_flags(variant, parent_combo=None):
    """Keep Ecomm's explicit variant flag separate from a parent flag."""
    flag = variant.get("is_combo") if isinstance(variant, dict) else None
    return {
        "variant_is_combo": flag if isinstance(flag, bool) else None,
        "parent_is_combo": parent_combo if isinstance(parent_combo, bool) else None,
        "api_gtin": _str((variant or {}).get("barcode") or (variant or {}).get("gtin")),
    }


def combo_gtin_conflict_audit(
    matched, owners_sku, owners_ean, owners_mla, ml_rows,
    edima_brands, stage_pages,
):
    """Classify contradictory IDs from existing snapshots, without side effects.

    This deliberately reproduces the relevant *identity and brand* gates in
    shared_gtin_sku_review so counters align with that diagnostic.
    Group examples by Ecomm SKU owner + GTIN, not by duplicate MLA rows.
    """
    flags_by_id = {}
    for page in stage_pages:
        for parent in page.get("items") or []:
            for variant in parent.get("variants") or []:
                if not isinstance(variant, dict):
                    continue
                identifier = _str(variant.get("id"))
                if identifier:
                    flags_by_id[identifier] = _combo_flags(
                        variant, parent.get("is_combo")
                    )

    counts = Counter()
    grouped = defaultdict(lambda: {
        "mlas": set(), "reason_codes": set(), "titles": set(),
    })
    distinct_ml_ids = set()
    distinct_gtins = set()
    distinct_sku_ids = set()

    for row in ml_rows:
        gtin = _str(row.get("ean"))
        if gtin_status(gtin) != "VALID_CHECK_DIGIT":
            continue
        gtin_owners = owners_ean.get(gtin, set())
        if len(gtin_owners) <= 1:
            continue

        mla = _ml_id(row.get("external_id"))
        edima_set = {_key(x) for x in edima_brands.get(mla, set())}
        ml_brand = _str(row.get("brand"))
        if len(edima_set) > 1 or (
            _brand_class(ml_brand) == "PRESENT"
            and edima_set and _key(ml_brand) not in edima_set
        ):
            continue
        if (_brand_class(ml_brand) != "PRESENT" and len(edima_set) != 1):
            continue

        sku_owners = {
            owner
            for field in ("variant_sku", "sku_effective", "sku", "sku_product")
            for owner in owners_sku.get(_key(row.get(field)), set())
            if _key(row.get(field))
        }
        if len(sku_owners) != 1:
            continue
        sku_owner = next(iter(sku_owners))
        mla_owners = owners_mla.get(mla, set())
        outside_gtin = sku_owner not in gtin_owners
        mla_conflict = bool(mla_owners and mla_owners != {sku_owner})
        if not (outside_gtin or mla_conflict):
            continue

        counts["contradictory_ml_rows"] += 1
        if outside_gtin:
            counts["sku_outside_gtin_owners_rows"] += 1
        if mla_conflict:
            counts["mla_reference_conflict_rows"] += 1

        distinct_ml_ids.add(mla)
        distinct_gtins.add(gtin)
        distinct_sku_ids.add(sku_owner)

        sku_info = matched.get(sku_owner)
        sku_record = sku_info[0] if sku_info else {}
        sku_flags = flags_by_id.get(sku_owner, _combo_flags(sku_info[1] if sku_info else {}))
        sku_is_combo = sku_flags["variant_is_combo"]
        counts[
            "sku_variant_combo_yes_rows" if sku_is_combo is True else
            "sku_variant_combo_no_rows" if sku_is_combo is False else
            "sku_variant_combo_unknown_rows"
        ] += 1

        owners = []
        gtin_has_noncombo = False
        gtin_has_combo = False
        gtin_unknown = False
        related_to_any = False
        for identifier in sorted(gtin_owners):
            info = matched.get(identifier)
            owner_record = info[0] if info else {}
            flags = flags_by_id.get(identifier, _combo_flags(info[1] if info else {}))
            gtin_has_noncombo |= flags["variant_is_combo"] is False
            gtin_has_combo |= flags["variant_is_combo"] is True
            gtin_unknown |= flags["variant_is_combo"] is None
            family = compare_family_skus(
                _str(sku_record.get("sku_variant") or sku_record.get("sku_effective") or sku_record.get("sku")),
                _str(owner_record.get("sku_variant") or owner_record.get("sku_effective") or owner_record.get("sku")),
            )
            related_to_any |= bool(family["related"])
            owners.append({
                "ecomm_id": identifier,
                "sku": _str(owner_record.get("sku_variant") or owner_record.get("sku_effective") or owner_record.get("sku")),
                "name": _str(owner_record.get("name")),
                **flags,
                "family_rule": family["rule"] if family["related"] else None,
                "identity_confirmed": False,
            })

        if gtin_has_noncombo:
            counts["gtin_has_noncombo_owner_rows"] += 1
        if gtin_has_combo:
            counts["gtin_has_combo_owner_rows"] += 1
        if gtin_unknown:
            counts["gtin_has_unknown_combo_owner_rows"] += 1
        if related_to_any:
            counts["numeric_family_hint_rows"] += 1

        # These are diagnostic buckets, not a bill-of-materials classification.
        if sku_is_combo is True and gtin_has_noncombo:
            category = "COMBO_SKU_WITH_NONCOMBO_GTIN_OWNER"
            counts["possible_combo_component_pattern_rows"] += 1
        elif sku_is_combo is True:
            category = "COMBO_SKU_COMPONENTS_UNKNOWN"
        elif sku_is_combo is False and gtin_has_combo:
            category = "NONCOMBO_SKU_GTIN_HAS_COMBO_OWNER"
        elif sku_is_combo is False:
            category = "SKU_NOT_FLAGGED_COMBO"
        else:
            category = "SKU_COMBO_FLAG_UNKNOWN"
        counts[category] += 1

        key = (sku_owner, gtin)
        group = grouped[key]
        group["mlas"].add(mla)
        group["titles"].add(_str(row.get("title")))
        if outside_gtin:
            group["reason_codes"].add("SKU_OUTSIDE_GTIN_OWNERS")
        if mla_conflict:
            group["reason_codes"].add("HISTORICAL_MLA_CONFLICT")
        group.update({
            "ecomm_id_by_sku": sku_owner,
            "ecomm_sku": _str(sku_record.get("sku_variant") or sku_record.get("sku_effective") or sku_record.get("sku")),
            "ecomm_name": _str(sku_record.get("name")),
            "gtin": gtin,
            "gtin_owner_count": len(gtin_owners),
            "gtin_owners": owners[:8],
            "ecomm_variant_is_combo": sku_flags["variant_is_combo"],
            "ecomm_parent_is_combo": sku_flags["parent_is_combo"],
            "ecomm_api_gtin": sku_flags["api_gtin"],
            "category": category,
            "numeric_sku_family_hint": related_to_any,
            "review_status": "DIAGNOSTIC_ONLY",
            "component_membership_confirmed": False,
        })

    counts["distinct_mlas"] = len(distinct_ml_ids)
    counts["distinct_gtins"] = len(distinct_gtins)
    counts["distinct_sku_ids"] = len(distinct_sku_ids)
    counts["distinct_sku_gtin_cases"] = len(grouped)
    cases = []
    for group in grouped.values():
        cases.append({
            **{k: v for k, v in group.items() if k not in ("mlas", "titles", "reason_codes")},
            "mlas": sorted(group["mlas"])[:8],
            "mla_count": len(group["mlas"]),
            "ml_titles": sorted(x for x in group["titles"] if x)[:2],
            "reason_codes": sorted(group["reason_codes"]),
        })
    cases.sort(key=lambda x: (
        0 if x["category"] == "COMBO_SKU_WITH_NONCOMBO_GTIN_OWNER" else 1,
        -x["mla_count"], x["ecomm_id_by_sku"], x["gtin"],
    ))
    return {
        "mode": "COMBO_GTIN_DIAGNOSTIC_ONLY",
        "components_available_in_snapshot": False,
        "activation_allowed": False,
        "counts": {
            key: counts[key] for key in (
                "contradictory_ml_rows", "distinct_mlas", "distinct_gtins",
                "distinct_sku_ids", "distinct_sku_gtin_cases",
                "sku_outside_gtin_owners_rows", "mla_reference_conflict_rows",
                "sku_variant_combo_yes_rows", "sku_variant_combo_no_rows",
                "sku_variant_combo_unknown_rows",
                "gtin_has_noncombo_owner_rows", "gtin_has_combo_owner_rows",
                "gtin_has_unknown_combo_owner_rows",
                "numeric_family_hint_rows",
                "possible_combo_component_pattern_rows",
                "COMBO_SKU_WITH_NONCOMBO_GTIN_OWNER",
                "COMBO_SKU_COMPONENTS_UNKNOWN",
                "NONCOMBO_SKU_GTIN_HAS_COMBO_OWNER",
                "SKU_NOT_FLAGGED_COMBO", "SKU_COMBO_FLAG_UNKNOWN",
            )
        },
        "examples": cases[:SAMPLE_LIMIT],
        "sample_limit": SAMPLE_LIMIT,
        "policy": (
            "El campo is_combo de la API de Ecomm-App describe una señal por ficha/variante, "
            "pero el snapshot de inventario NO informa la composición de los packs ni la "
            "relación componente→combo. Que el GTIN corresponda a una ficha sin combo "
            "NO demuestra que sea un componente del pack. Las familias SKU numéricas "
            "son indicios comerciales, no evidencia de composición. No se asignan "
            "marcas, stock, GTIN ni vínculos."
        ),
        "next_step": (
            "Si predominan posibles patrones de combo, solicitar un endpoint o export "
            "de composición de combos que incluya ID de variante padre y IDs/cantidades "
            "de componentes. Si predominan productos sin señal de combo, investigar el GTIN "
            "y la asignación SKU/MLA en el origen."
        ),
    }
