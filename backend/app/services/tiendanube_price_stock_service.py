"""Read-only price and stock comparison; only unique exact-SKU matches qualify."""
from collections import Counter
from decimal import Decimal, InvalidOperation

from .tiendanube_csv_service import TiendanubeCsvService


def decimal_or_none(value):
    if value is None or str(value).strip() == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


class TiendanubePriceStockService:
    def __init__(self, db):
        self.catalog = TiendanubeCsvService(db)

    def report(self):
        reconciled = self.catalog.report()
        if not reconciled["available"]:
            return {"available": False, "summary": {}, "items": []}
        ecomm = self.catalog.repo.snapshot("ECOMM_APP")
        ecomm_by_id = {
            str(row.get("ecomm_id")): row
            for row in ecomm if row.get("ecomm_id")
        }
        results = []
        for row in reconciled["items"]:
            if row["status"] != "MATCHED_SKU" or not row["matched_ecomm_id"]:
                continue
            product = ecomm_by_id.get(str(row["matched_ecomm_id"]))
            if product is None:
                continue
            tn_price = decimal_or_none(row.get("price"))
            # Ecomm canonical price can be marketplace-preferred, not Tiendanube price.
            ec_price = decimal_or_none(product.get("list_price"))
            tn_stock = decimal_or_none(row.get("stock"))
            ec_stock = decimal_or_none(product.get("stock"))
            price_state = ("UNAVAILABLE" if tn_price is None or ec_price is None
                           else "EQUAL" if tn_price == ec_price else "DIFFERENT")
            stock_state = ("UNAVAILABLE" if tn_stock is None or ec_stock is None
                           else "EQUAL" if tn_stock == ec_stock else "DIFFERENT")
            results.append({
                "sku": row["sku"], "name": row["name"],
                "ecomm_id": row["matched_ecomm_id"],
                "tiendanube_price": str(tn_price) if tn_price is not None else None,
                "ecomm_list_price": str(ec_price) if ec_price is not None else None,
                "price_difference": str(tn_price - ec_price) if price_state == "DIFFERENT" else None,
                "tiendanube_stock": str(tn_stock) if tn_stock is not None else None,
                "ecomm_stock": str(ec_stock) if ec_stock is not None else None,
                "stock_difference": str(tn_stock - ec_stock) if stock_state == "DIFFERENT" else None,
                "price_state": price_state, "stock_state": stock_state,
            })
        prices = Counter(item["price_state"] for item in results)
        stocks = Counter(item["stock_state"] for item in results)
        return {
            "available": True,
            "summary": {
                "comparable_sku_rows": len(results),
                "price_different": prices["DIFFERENT"],
                "price_equal": prices["EQUAL"],
                "price_unavailable": prices["UNAVAILABLE"],
                "stock_different": stocks["DIFFERENT"],
                "stock_equal": stocks["EQUAL"],
                "stock_unavailable": stocks["UNAVAILABLE"],
            },
            "items": results,
            "policy": "Precios: referencia contra precio de lista Ecomm, no paridad obligatoria entre canales. Stock: instantáneas de momentos distintos pueden diferir. No se escribe en canales.",
        }
