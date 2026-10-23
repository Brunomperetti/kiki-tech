"""Read-only comparison: Ecomm-App API stage versus KIKI historical Excel catalog.

The primary identity is the stable Ecomm variant ID. A matching SKU without
the same ID is only a review hint, NEVER a reconciled identity. This report
does not modify catalog snapshots, stock, linked listings or decisions.
"""
from collections import Counter, defaultdict

from sqlalchemy import select

from ...database.models import CatalogSnapshot
from .catalog_stage import STAGE_SOURCE, stage_status


def _str(value) -> str:
    return str(value).strip() if value is not None else ""


def _format_key(value) -> str:
    """Read-only candidate detection: whitespace/case only, no punctuation."""
    return "".join(_str(value).split()).casefold()


def _legacy_sku(product: dict) -> str:
    return _str(
        product.get("sku_variant")
        or product.get("sku_effective")
        or product.get("sku")
        or product.get("sku_product")
    )


def _stage_variants(stage_pages: list[dict]) -> list[dict]:
    result = []
    for page in stage_pages:
        for parent in page.get("items") or []:
            for variant in parent.get("variants") or []:
                if not isinstance(variant, dict) or variant.get("invalid"):
                    continue
                result.append({
                    "id": _str(variant.get("id")),
                    "sku": _str(variant.get("sku")),
                    "name": _str(variant.get("variant_description") or parent.get("description")),
                    "parent_code": _str(parent.get("code")),
                    "is_combo": variant.get("is_combo") if isinstance(variant.get("is_combo"), bool) else None,
                    "stock": variant.get("total_stock"),
                    "ean": _str(variant.get("barcode") or variant.get("gtin")),
                })
    return result


def compare_stage_to_legacy(stage_pages: list[dict], legacy: list[dict]) -> dict:
    state = stage_status(stage_pages)
    if not state["complete"] or state["pages_saved"] != state["expected_pages"]:
        raise ValueError(
            "La copia API todavía está incompleta. No se puede comparar un catálogo parcial."
        )
    if state["quality"]["parents"] != state["expected_parents"]:
        raise ValueError(
            "La copia API no contiene todos los productos esperados. Revisá la integridad."
        )
    if not isinstance(legacy, list) or not legacy:
        raise ValueError(
            "No existe un inventario histórico de Ecomm-App para comparar."
        )

    staged = _stage_variants(stage_pages)
    historical = [x for x in legacy if isinstance(x, dict)]
    historical_id_counts = Counter(_str(x.get("ecomm_id")) for x in historical if _str(x.get("ecomm_id")))
    stage_id_counts = Counter(x["id"] for x in staged if x["id"])
    historic_by_id = {
        _str(x.get("ecomm_id")): x for x in historical
        if _str(x.get("ecomm_id")) and historical_id_counts[_str(x.get("ecomm_id"))] == 1
    }
    stage_by_id = {
        x["id"]: x for x in staged
        if x["id"] and stage_id_counts[x["id"]] == 1
    }

    matched_ids = set(historic_by_id) & set(stage_by_id)
    stage_by_sku = defaultdict(list)
    stage_by_format = defaultdict(list)
    for item in staged:
        if item["sku"]:
            stage_by_sku[item["sku"]].append(item)
            stage_by_format[_format_key(item["sku"])].append(item)

    summary = Counter()
    samples = {
        "sku_changed_same_id": [],
        "stock_changed_same_id": [],
        "historical_without_id_match": [],
        "api_without_id_match": [],
        "candidate_by_sku": [],
    }

    for identifier in sorted(matched_ids):
        old = historic_by_id[identifier]
        new = stage_by_id[identifier]
        old_sku, new_sku = _legacy_sku(old), new["sku"]
        if old_sku == new_sku:
            summary["same_id_same_sku"] += 1
        elif _format_key(old_sku) == _format_key(new_sku) and old_sku and new_sku:
            summary["same_id_format_sku_changed"] += 1
        else:
            summary["same_id_different_sku"] += 1
        if old_sku != new_sku and len(samples["sku_changed_same_id"]) < 10:
            samples["sku_changed_same_id"].append({
                "ecomm_id": identifier,
                "old_sku": old_sku, "api_sku": new_sku,
                "product": _str(old.get("name") or new["name"]),
                "api_parent_code": new["parent_code"],
            })
        old_stock = old.get("stock")
        new_stock = new["stock"]
        # These values refer to DIFFERENT dates; this is informational only.
        if old_stock is not None and new_stock is not None:
            try:
                from decimal import Decimal
                different = Decimal(str(old_stock)) != Decimal(str(new_stock))
            except Exception:
                different = False
            if different:
                summary["stock_differences_informational"] += 1
                if len(samples["stock_changed_same_id"]) < 8:
                    samples["stock_changed_same_id"].append({
                        "ecomm_id": identifier,
                        "sku": new_sku,
                        "historical_stock": str(old_stock),
                        "api_stock": str(new_stock),
                    })
        old_ean = _str(old.get("ean"))
        if old_ean and new["ean"] and old_ean != new["ean"]:
            summary["gtin_disagreement_when_both_present"] += 1

    unmatched_historic = [
        x for x in historical if _str(x.get("ecomm_id")) not in matched_ids
    ]
    unmatched_api = [x for x in staged if x["id"] not in matched_ids]
    summary["legacy_without_id"] = sum(not _str(x.get("ecomm_id")) for x in historical)
    summary["stage_without_id"] = sum(not x["id"] for x in staged)
    summary["duplicate_legacy_ids"] = sum(count - 1 for count in historical_id_counts.values() if count > 1)
    summary["duplicate_stage_ids"] = sum(count - 1 for count in stage_id_counts.values() if count > 1)

    for old in unmatched_historic:
        sku = _legacy_sku(old)
        item = {
            "ecomm_id": _str(old.get("ecomm_id")),
            "sku": sku,
            "product": _str(old.get("name")),
        }
        if len(samples["historical_without_id_match"]) < 8:
            samples["historical_without_id_match"].append(item)
        if not sku:
            continue
        # SKU is a *possible* identity only for an otherwise unmatched old
        # product; never claim a confirmed match without a stable ID.
        if len(stage_by_sku[sku]) == 1:
            match = stage_by_sku[sku][0]
            basis = "SAME_SKU_DIFFERENT_ID"
        elif len(stage_by_format[_format_key(sku)]) == 1:
            match = stage_by_format[_format_key(sku)][0]
            basis = "FORMAT_ONLY_DIFFERENT_ID"
        else:
            continue
        if match["id"] in matched_ids:
            # Already owned by a different historical ID; report the ambiguity
            # rather than presenting a plausible remap.
            summary["sku_points_to_other_matched_id"] += 1
            continue
        summary["candidate_sku_only"] += 1
        if len(samples["candidate_by_sku"]) < 10:
            samples["candidate_by_sku"].append({
                "historical_id": item["ecomm_id"],
                "historical_sku": sku,
                "api_id": match["id"],
                "api_sku": match["sku"],
                "basis": basis,
            })

    for fresh in unmatched_api[:8]:
        samples["api_without_id_match"].append({
            "api_id": fresh["id"], "sku": fresh["sku"],
            "parent_code": fresh["parent_code"],
            "is_combo": fresh["is_combo"],
        })
    result = {
        "mode": "READ_ONLY_COMPARISON",
        "stage_complete": True,
        "source": STAGE_SOURCE,
        "totals": {
            "historical_products": len(historical),
            "api_products_parent": state["quality"]["parents"],
            "api_variants": len(staged),
            "matched_stable_ids": len(matched_ids),
            "historical_no_stable_id_match": len(unmatched_historic),
            "api_no_stable_id_match": len(unmatched_api),
            "same_id_same_sku": summary["same_id_same_sku"],
            "same_id_format_sku_changed": summary["same_id_format_sku_changed"],
            "same_id_different_sku": summary["same_id_different_sku"],
            "stock_differences_informational": summary["stock_differences_informational"],
            "gtin_disagreement_when_both_present": summary["gtin_disagreement_when_both_present"],
            "candidate_sku_only": summary["candidate_sku_only"],
            "sku_points_to_other_matched_id": summary["sku_points_to_other_matched_id"],
            "legacy_without_id": summary["legacy_without_id"],
            "stage_without_id": summary["stage_without_id"],
            "duplicate_legacy_ids": summary["duplicate_legacy_ids"],
            "duplicate_stage_ids": summary["duplicate_stage_ids"],
        },
        "samples": samples,
        "warning": (
            "Las coincidencias por ID se muestran para diagnóstico. "
            "Los SKU sin ID coincidente son solo candidatos, no vínculos validados. "
            "Las diferencias de stock reflejan momentos de captura distintos y "
            "NO significan que haya que actualizar existencias. "
            "No se cambió la fuente de KIKI ni ninguna decisión."
        ),
    }
    return result


class EcommAppStageComparisonService:
    def __init__(self, db):
        self.db = db

    def report(self) -> dict:
        source = self.db.scalar(
            select(CatalogSnapshot).where(CatalogSnapshot.source == STAGE_SOURCE)
        )
        original = self.db.scalar(
            select(CatalogSnapshot).where(CatalogSnapshot.source == "ECOMM_APP")
        )
        return compare_stage_to_legacy(
            source.payload if source else [],
            original.payload if original else [],
        )
