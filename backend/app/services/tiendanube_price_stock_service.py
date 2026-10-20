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
        # Compare only Mercado Libre listings with the SAME literal variant SKU as TN.
        # Listing prices are offer prices; multiple offers are not a single price.
        # Do not infer ML stock: neither listing snapshot guarantees it is comparable.
        from .reconciliation_service import ReconciliationService
        ml_source = ReconciliationService(self.catalog.repo.db)._choose_ml_source("AUTO")
        ml_record = self.catalog.repo.snapshot_record(ml_source)
        ml_listings = (ml_record.payload or []) if ml_record else []
        by_ml_sku = {}
        for listing in ml_listings:
            sku = str(listing.get("variant_sku") or listing.get("sku_effective") or listing.get("sku") or "").strip()
            if sku:
                by_ml_sku.setdefault(sku.casefold(), []).append(listing)
        ml_available = ml_record is not None
        ml_snapshot_at = ml_record.updated_at.isoformat() if ml_record else None
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
            ml_matches = by_ml_sku.get(str(row["sku"]).strip().casefold(), []) if ml_available else []
            if not ml_available:
                ml_status = "NO_SNAPSHOT"
            elif len(ml_matches) == 0:
                ml_status = "NO_EXACT_SKU"
            elif len(ml_matches) > 1:
                ml_status = "MULTIPLE_LISTINGS"
            else:
                ml_status = "ONE_SKU_CANDIDATE"
            ml_price = decimal_or_none(ml_matches[0].get("price")) if len(ml_matches) == 1 else None
            # Keep every row of matching offer evidence, including prices and
            # missing prices. NEVER choose a single price from multiple offers.
            ml_offers = []
            for offer in ml_matches:
                offer_price = decimal_or_none(offer.get("price"))
                ml_offers.append({
                    "external_id": str(offer.get("external_id") or ""),
                    "title": str(offer.get("title") or ""),
                    "price": str(offer_price) if offer_price is not None else None,
                    "listing_status": str(offer.get("status") or ""),
                })
            ml_offers.sort(key=lambda item: (item["external_id"], item["title"], item["price"] or ""))
            ml_status_label = ("Múltiples ofertas ML" if len(ml_matches) > 1
                               else "Sin coincidencia SKU" if ml_available and not ml_matches
                               else "Sin snapshot ML" if not ml_available else "SKU único en snapshot")
            results.append({
                "ml_status": ml_status,
                "ml_status_label": ml_status_label,
                "ml_listing_count": len(ml_matches),
                "ml_offers": ml_offers,
                "ml_listing_ids": [str(item.get("external_id") or "") for item in ml_matches if item.get("external_id")],
                "ml_price": str(ml_price) if ml_price is not None else None,
                "ml_stock": None,
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
                "ml_sku_single_candidate": sum(item["ml_status"] == "ONE_SKU_CANDIDATE" for item in results),
                "ml_multiple_listings": sum(item["ml_status"] == "MULTIPLE_LISTINGS" for item in results),
                "ml_not_comparable": sum(item["ml_status"] in {"NO_SNAPSHOT", "NO_EXACT_SKU"} for item in results),
            },
            "ml_available": ml_available,
            "ml_source": ml_source if ml_available else None,
            "ml_snapshot_at": ml_snapshot_at,
            "items": results,
            "policy": "TN frente a precio de lista Ecomm: diferencias no son errores automáticos. ML: se muestran por separado todos los precios de las filas del último snapshot con SKU exactamente coincidente. No prueban identidad de presentación ni vigencia actual; con múltiples ofertas no se calcula un precio único. Stock ML no comparable. Sin escrituras externas.",
        }
