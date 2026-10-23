"""Dry-run hybrid inventory inspection: historical commercial fields + staged API stock.

ALL values are read from existing PostgreSQL snapshots. This module never
updates a snapshot, maps SKUs across IDs, authorizes a channel listing, or
reports an old API snapshot as live inventory.
"""
from collections import Counter, defaultdict

from sqlalchemy import select

from ...database.models import CatalogSnapshot
from .catalog_stage import STAGE_SOURCE, stage_status
from .catalog_comparison import _format_key, _legacy_sku, _str


MAX_IDS = 5


def _present(value) -> bool:
    return value is not None and value != ""


def _sku_relation(old: str, new: str) -> str:
    if old == new:
        return "SAME_SKU"
    if old and new and _format_key(old) == _format_key(new):
        return "FORMAT_ONLY"
    return "SUBSTANTIVE_CHANGE"


def _indexes(pages: list[dict], legacy: list[dict]):
    old_by_id = defaultdict(list)
    new_by_id = defaultdict(list)
    for product in legacy:
        if isinstance(product, dict):
            identifier = _str(product.get("ecomm_id"))
            if identifier:
                old_by_id[identifier].append(product)
    for page in pages:
        for parent in page.get("items") or []:
            if not isinstance(parent, dict):
                continue
            for variant in parent.get("variants") or []:
                if not isinstance(variant, dict) or variant.get("invalid"):
                    continue
                identifier = _str(variant.get("id"))
                if identifier:
                    new_by_id[identifier].append((parent, variant))
    return old_by_id, new_by_id


def hybrid_catalog_preview(stage_pages: list[dict], legacy: list[dict], ids: list[str]) -> dict:
    if not isinstance(ids, list) or not 1 <= len(ids) <= MAX_IDS:
        raise ValueError("Seleccioná entre 1 y 5 IDs de variante Ecomm para la simulación.")
    normalized = [_str(identifier) for identifier in ids]
    if any(not item.isascii() or not item.isdecimal() or len(item) > 30 for item in normalized):
        raise ValueError("Ingresá solamente IDs internos numéricos válidos.")
    if len(set(normalized)) != len(normalized):
        raise ValueError("No repitas el mismo ID: cada fila de la simulación representa una variante.")
    stage = stage_status(stage_pages)
    if not stage["complete"] or stage["quality"]["parents"] != stage["expected_parents"]:
        raise ValueError("La copia API está incompleta. No se puede simular un catálogo parcial.")
    if not isinstance(legacy, list) or not legacy:
        raise ValueError("Falta el inventario histórico; no se puede verificar la información comercial.")

    old_by_id, new_by_id = _indexes(stage_pages, legacy)
    counts = Counter()
    # Coverage is based on unique stable IDs in BOTH sources, never SKU guesses.
    for key, old_rows in old_by_id.items():
        new_rows = new_by_id.get(key, [])
        if len(old_rows) != 1 or len(new_rows) != 1:
            continue
        old = old_rows[0]
        counts["matched_unique_ids"] += 1
        if _present(old.get("list_price")) or _present(old.get("price")):
            counts["legacy_price_present"] += 1
        if _present(old.get("cost")):
            counts["legacy_cost_present"] += 1
        if _present(old.get("brand")):
            counts["legacy_brand_present"] += 1
        if _present(old.get("ean")):
            counts["legacy_gtin_present"] += 1
        if _present(new_rows[0][1].get("total_stock")):
            counts["api_stock_present"] += 1

    samples = []
    for identifier in normalized:
        old_rows = old_by_id.get(identifier, [])
        api_rows = new_by_id.get(identifier, [])
        if len(old_rows) > 1 or len(api_rows) > 1:
            samples.append({
                "ecomm_id": identifier, "identity": "AMBIGUOUS_DUPLICATE_ID",
                "sku_relation": None, "legacy": None, "api": None,
                "warning": "ID repetido dentro de una fuente. No combinar ni elegir arbitrariamente.",
            })
            continue

        old = old_rows[0] if old_rows else None
        parent, variant = api_rows[0] if api_rows else (None, None)
        if old and variant:
            identity = "MATCHED_STABLE_ID"
        elif old:
            identity = "HISTORICAL_ONLY"
        elif variant:
            identity = "API_ONLY"
        else:
            identity = "NOT_FOUND"

        prior = _legacy_sku(old) if old else ""
        current = _str(variant.get("sku")) if variant else ""
        warehouses = variant.get("warehouses") if variant else None
        samples.append({
            "ecomm_id": identifier,
            "identity": identity,
            "sku_relation": _sku_relation(prior, current) if old and variant else None,
            "legacy": {
                "name": old.get("name"),
                "sku": prior,
                "brand": old.get("brand"),
                "list_price": old.get("list_price") if _present(old.get("list_price")) else old.get("price"),
                "cost": old.get("cost"),
                "ean": old.get("ean"),
                "historical_stock": old.get("stock"),
                "source": "ECOMM_APP (Excel histórico)",
            } if old else None,
            "api": {
                "parent_code": parent.get("code"),
                "sku": current,
                "variant_id": variant.get("id"),
                "is_combo": variant.get("is_combo")
                if isinstance(variant.get("is_combo"), bool) else None,
                "total_stock": variant.get("total_stock"),
                "warehouses": [
                    {"id": x.get("id"), "stock": x.get("stock")}
                    for x in warehouses if isinstance(x, dict)
                ] if isinstance(warehouses, list) else None,
                "source": "ECOMM_APP_API_STAGE (copia capturada)",
            } if variant else None,
            "warning": (
                "Mismo ID: valores mostrados en paralelo; no se generó una ficha híbrida operativa."
                if old and variant else
                "ID sin correspondencia en una de las fuentes: no inferir equivalencia por nombre o SKU."
            ),
        })

    return {
        "mode": "READ_ONLY_HYBRID_PREVIEW",
        "activation_allowed": False,
        "stage_capture_started": stage.get("first_page_at"),
        "stage_capture_finished": stage.get("last_page_at"),
        "coverage": {
            "matched_unique_ids": counts["matched_unique_ids"],
            "legacy_price_present": counts["legacy_price_present"],
            "legacy_cost_present": counts["legacy_cost_present"],
            "legacy_brand_present": counts["legacy_brand_present"],
            "legacy_gtin_present": counts["legacy_gtin_present"],
            "api_stock_present": counts["api_stock_present"],
        },
        "rows": samples,
        "warning": (
            "Esta simulación solo lee el Excel histórico y la copia API guardada. "
            "El stock API NO es en tiempo real: corresponde al momento en que se capturó el catálogo. "
            "Los precios y costos se mantienen identificados como datos históricos. "
            "No se crearon vínculos, alias, productos ni publicaciones; NO se activó sincronización."
        ),
    }


class EcommHybridCatalogService:
    def __init__(self, db):
        self.db = db

    def preview(self, ids: list[str]) -> dict:
        api = self.db.scalar(select(CatalogSnapshot).where(CatalogSnapshot.source == STAGE_SOURCE))
        legacy = self.db.scalar(select(CatalogSnapshot).where(CatalogSnapshot.source == "ECOMM_APP"))
        return hybrid_catalog_preview(api.payload if api else [], legacy.payload if legacy else [], ids)
