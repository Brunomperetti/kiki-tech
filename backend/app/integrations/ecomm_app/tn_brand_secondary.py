"""Additional read-only diagnosis when Ecomm–Tiendanube literal SKU matches give zero.

Exact *unique* EAN and exact *unique* full name can produce review-only leads.
Neither signal proves the manufacturer, commercial link, nor usable GTIN.
"""
from collections import Counter, defaultdict
import re
import unicodedata

from ...services.tiendanube_assisted_match_service import variant_conflict
from ...services.tiendanube_quality_audit_service import gtin_status
from .catalog_comparison import _legacy_sku, _str
from .catalog_hybrid_preview import _indexes
from .commercial_audit import _brand_class

SAMPLE_LIMIT = 12


def _sku(value):
    return _str(value).casefold()


def _title(value):
    folded = unicodedata.normalize("NFKD", _str(value))
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    return " ".join(re.findall(r"[a-z0-9]+", folded.casefold()))


def _ean(value):
    code = _str(value)
    return code if gtin_status(code) == "VALID_CHECK_DIGIT" else ""


def _aliases(row):
    values = [
        row.get("sku"), row.get("sku_effective"),
        row.get("sku_product"), row.get("sku_variant"),
        *(row.get("sku_aliases") or []),
    ]
    return {_sku(v) for v in values if _sku(v)}


def diagnose_tn_brand_gaps(stage_pages: list[dict], historical: list[dict], tn: list[dict]) -> dict:
    old_by_id, new_by_id = _indexes(stage_pages, historical)
    old_by_sku = defaultdict(set)
    for old in historical:
        if not isinstance(old, dict):
            continue
        owner = _str(old.get("ecomm_id"))
        for sku in _aliases(old):
            if owner:
                old_by_sku[sku].add(owner)

    tn_with_brand = [x for x in tn if _brand_class(x.get("brand")) == "PRESENT"]
    overlap_ids = set()
    overlap_known_brand_ids = set()
    tn_with_ecomm_sku = 0
    for row in tn:
        ids = old_by_sku.get(_sku(row.get("sku")), set())
        if ids:
            tn_with_ecomm_sku += 1
        if len(ids) == 1:
            identifier = next(iter(ids))
            if len(old_by_id.get(identifier, [])) != 1:
                continue
            overlap_ids.add(identifier)
            if _brand_class(old_by_id[identifier][0].get("brand")) == "PRESENT":
                overlap_known_brand_ids.add(identifier)

    tn_by_ean, old_by_ean = defaultdict(list), defaultdict(list)
    tn_by_title, old_by_title = defaultdict(list), defaultdict(list)
    for item in tn:
        if not isinstance(item, dict):
            continue
        code = _ean(item.get("ean_raw"))
        if code:
            tn_by_ean[code].append(item)
        title = _title(item.get("name"))
        if len(title) >= 18 and len(title.split()) >= 3:
            tn_by_title[title].append(item)
    for old in historical:
        if not isinstance(old, dict):
            continue
        code = _ean(old.get("ean"))
        if code:
            old_by_ean[code].append(old)
        title = _title(old.get("name"))
        if len(title) >= 18 and len(title.split()) >= 3:
            old_by_title[title].append(old)

    counts = Counter()
    matches = []
    for identifier in sorted(old_by_id):
        source_rows = old_by_id[identifier]
        api_rows = new_by_id.get(identifier, [])
        if len(source_rows) != 1 or len(api_rows) != 1:
            continue
        old = source_rows[0]
        if _brand_class(old.get("brand")) == "PRESENT":
            continue
        parent, variant = api_rows[0]
        # A meaningful SKU change must be investigated independently.
        old_sku = _sku(_legacy_sku(old))
        api_sku = _sku(variant.get("sku"))
        if not old_sku or not api_sku:
            counts["missing_sku"] += 1
            continue
        if "".join(old_sku.split()) != "".join(api_sku.split()):
            counts["changed_sku"] += 1
            continue

        alternatives = []
        ean = _ean(old.get("ean"))
        if ean and len(old_by_ean[ean]) == 1 and len(tn_by_ean[ean]) == 1:
            alternatives.append(("VALID_UNIQUE_EAN", tn_by_ean[ean][0]))
        name_key = _title(old.get("name"))
        if name_key and len(old_by_title.get(name_key, [])) == 1 and len(tn_by_title.get(name_key, [])) == 1:
            alternatives.append(("UNIQUE_EXACT_FULL_NAME", tn_by_title[name_key][0]))

        # If both identifiers suggest different TN products, do not choose one.
        tn_identifiers = {
            (_sku(item.get("sku")), _str(item.get("slug")))
            for _, item in alternatives
        }
        if len(tn_identifiers) > 1:
            counts["conflicting_indirect_signals"] += 1
            continue
        if not alternatives:
            continue
        method, tn_row = alternatives[0]
        proposed_brand = _str(tn_row.get("brand"))
        if _brand_class(proposed_brand) != "PRESENT":
            counts["tn_brand_missing"] += 1
            continue
        if variant_conflict(
            old.get("name"), _legacy_sku(old),
            tn_row.get("name"), tn_row.get("sku")
        ):
            counts["presentation_conflict"] += 1
            continue
        # TN SKU pointing to a *different* historical Ecomm ID overrides
        # the weaker name/EAN lead, even if the candidate name is identical.
        sku_owners = old_by_sku.get(_sku(tn_row.get("sku")), set())
        if sku_owners and sku_owners != {identifier}:
            counts["tn_sku_claimed_by_other_id"] += 1
            continue
        counts["review_leads"] += 1
        counts["review_by_" + method.lower()] += 1
        if len(matches) < SAMPLE_LIMIT:
            matches.append({
                "ecomm_id": identifier,
                "ecomm_name": _str(old.get("name")),
                "ecomm_sku": _legacy_sku(old),
                "tn_name": _str(tn_row.get("name")),
                "tn_sku": _str(tn_row.get("sku")),
                "tn_slug": _str(tn_row.get("slug")),
                "tn_brand": proposed_brand,
                "match_basis": method,
                "shared_ean": ean if method == "VALID_UNIQUE_EAN" else None,
                "is_combo": variant.get("is_combo") if isinstance(variant.get("is_combo"), bool) else None,
                "review_status": "NOT_CONFIRMED",
            })

    return {
        "summary": {
            "tn_rows": len(tn),
            "tn_rows_with_brand": len(tn_with_brand),
            "tn_rows_matching_any_ecomm_sku": tn_with_ecomm_sku,
            "ecomm_ids_with_any_tn_sku": len(overlap_ids),
            "ecomm_ids_with_existing_brand_and_tn_sku": len(overlap_known_brand_ids),
            "review_leads": counts["review_leads"],
            "review_by_valid_unique_ean": counts["review_by_valid_unique_ean"],
            "review_by_unique_exact_full_name": counts["review_by_unique_exact_full_name"],
            "conflicting_indirect_signals": counts["conflicting_indirect_signals"],
            "presentation_conflict": counts["presentation_conflict"],
            "tn_sku_claimed_by_other_id": counts["tn_sku_claimed_by_other_id"],
        },
        "leads": matches,
        "sampling_limit": SAMPLE_LIMIT,
        "note": (
            "Diagnóstico sobre copias guardadas: una coincidencia por nombre completo único "
            "o GTIN válido y único es SOLO UNA PISTA PARA REVISIÓN. "
            "No se usa similitud aproximada ni se deduce marca del título. "
            "Una coincidencia exacta de EAN no acredita identidad de marca, "
            "autenticidad ni equivalencia entre packs. "
            "No se aplica ni se registra ninguna marca o vínculo comercial."
        ),
    }
