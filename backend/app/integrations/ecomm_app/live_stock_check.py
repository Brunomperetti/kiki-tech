"""Explicit, bounded Ecomm-App stock verification by immutable variant ID.

The vendor SKU endpoint returns parent products with sibling variants. An exact
SKU alone never proves product identity. Only a unique (exact SKU, variant ID)
pair is treated as a verified observation. Read-only; does not persist stock.
"""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from sqlalchemy import select

from ...database.models import CatalogSnapshot
from .catalog_hybrid_preview import hybrid_catalog_preview
from .catalog_stage import STAGE_SOURCE
from .public_api import API_PREFIX, EcommAppApiError, _items


def _identity(value) -> str:
    return str(value).strip() if value is not None else ""


def _decimal(value):
    if isinstance(value, bool) or value is None or value == "":
        return None
    try:
        result = Decimal(str(value))
        return result if result.is_finite() else None
    except (InvalidOperation, TypeError, ValueError):
        return None


def verify_current_stock(stage: list[dict], legacy: list[dict], ids: list[str], client) -> dict:
    # Prevent consulting IDs outside a fully staged inventory. This already
    # validates allowed IDs, uniqueness, stage completeness and source presence.
    preview = hybrid_catalog_preview(stage, legacy, ids)
    permitted = []
    outcomes = []
    for row in preview["rows"]:
        item = {
            "ecomm_id": row["ecomm_id"],
            "sku": row["api"]["sku"] if row["api"] else None,
            "is_combo": row["api"]["is_combo"] if row["api"] else None,
            "historical_stock": row["legacy"]["historical_stock"] if row["legacy"] else None,
            "captured_stock": row["api"]["total_stock"] if row["api"] else None,
            "current_stock": None,
            "warehouses": None,
            "status": "NOT_ELIGIBLE",
            "reason": "El ID no está presente una sola vez en ambas fuentes; no se consultó por SKU.",
        }
        outcomes.append(item)
        if row["identity"] == "MATCHED_STABLE_ID" and row["api"] and row["api"]["sku"]:
            permitted.append(item)

    if permitted:
        asked_skus = list(dict.fromkeys(item["sku"] for item in permitted))
        # Official /consulta endpoint is read-only even though it uses POST.
        data = client._call(
            "POST", f"{API_PREFIX}/productos/consulta",
            body={"skus": asked_skus},
        )
        products, _ = _items(data)
        if products is None:
            raise EcommAppApiError(
                502, "FORMATO_INESPERADO",
                "La respuesta actual de Ecomm-App no contiene productos reconocibles.",
            )
        matches = {}
        for parent in products:
            variants = parent.get("variants")
            if not isinstance(variants, list):
                continue
            for variant in variants:
                if isinstance(variant, dict):
                    sku = variant.get("sku")
                    if isinstance(sku, str) and sku in asked_skus:
                        matches.setdefault(sku, []).append(variant)

        for item in permitted:
            found = matches.get(item["sku"], [])
            if len(found) == 0:
                item["status"] = "SKU_NOT_FOUND"
                item["reason"] = "El SKU exacto de la copia no apareció en la consulta actual."
                continue
            if len(found) != 1:
                item["status"] = "AMBIGUOUS_SKU"
                item["reason"] = "El mismo SKU aparece más de una vez; no se eligió una variante."
                continue
            variant = found[0]
            if _identity(variant.get("id")) != item["ecomm_id"]:
                item["status"] = "ID_MISMATCH"
                item["reason"] = (
                    "El SKU corresponde ahora a otro ID. No usar este stock "
                    "ni asumir un vínculo comercial."
                )
                continue
            stock = _decimal(variant.get("total_stock"))
            if stock is None:
                item["status"] = "STOCK_NOT_REPORTED"
                item["reason"] = "Coinciden SKU e ID, pero no se informó stock numérico."
                continue
            warehouses = variant.get("warehouses")
            if not isinstance(warehouses, list):
                item["status"] = "WAREHOUSES_NOT_REPORTED"
                item["reason"] = "El SKU y el ID coinciden, pero falta desglose de depósitos."
                continue
            parsed_warehouses = []
            for warehouse in warehouses:
                if not isinstance(warehouse, dict):
                    parsed_warehouses = []
                    break
                qty = _decimal(warehouse.get("stock"))
                w_id = warehouse.get("id", warehouse.get("warehouse_id"))
                if qty is None or w_id is None:
                    parsed_warehouses = []
                    break
                parsed_warehouses.append({"id": w_id, "stock": warehouse.get("stock")})
            if not parsed_warehouses:
                item["status"] = "WAREHOUSES_NOT_REPORTED"
                item["reason"] = "Desglose de depósitos ausente o incompleto."
                continue
            total_from_warehouses = sum(
                (_decimal(w["stock"]) for w in parsed_warehouses), Decimal(0)
            )
            if total_from_warehouses != stock:
                item["status"] = "WAREHOUSE_TOTAL_CONFLICT"
                item["reason"] = (
                    "El total de stock no coincide con la suma de depósitos. "
                    "No puede validarse el stock para sincronización."
                )
                item["current_stock"] = variant.get("total_stock")
                item["warehouses"] = parsed_warehouses
                continue
            item["status"] = "IDENTITY_AND_STOCK_VERIFIED"
            item["reason"] = (
                "SKU e ID exactos y únicos, con total igual a depósitos. "
                "Es una lectura puntual, NO autoriza sincronizar stock ni publicar."
            )
            item["current_stock"] = variant.get("total_stock")
            item["warehouses"] = parsed_warehouses

    return {
        "mode": "READ_ONLY_LIVE_STOCK_VERIFICATION",
        "activation_allowed": False,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "snapshot_captured_at": preview["stage_capture_finished"],
        "queried_skus": len({row["sku"] for row in permitted}),
        "rows": outcomes,
        "warning": (
            "Consulta puntual a Ecomm-App. Se exige SKU literal e ID de variante único, "
            "más suma de depósitos consistente. Los demás SKUs hermanos se ignoran. "
            "El stock puede cambiar después de esta respuesta; combos requieren "
            "validación comercial adicional. No se guarda ni sincroniza nada."
        ),
    }


class EcommLiveStockService:
    def __init__(self, db, client):
        self.db = db
        self.client = client

    def verify(self, ids: list[str]) -> dict:
        stage = self.db.scalar(
            select(CatalogSnapshot).where(CatalogSnapshot.source == STAGE_SOURCE)
        )
        legacy = self.db.scalar(
            select(CatalogSnapshot).where(CatalogSnapshot.source == "ECOMM_APP")
        )
        return verify_current_stock(
            stage.payload if stage else [],
            legacy.payload if legacy else [],
            ids,
            self.client,
        )
