from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.database.models import Base
from app.services.tiendanube_price_stock_service import TiendanubePriceStockService

def save_ecomm_api_stage(svc, rows):
    """Complete capture: never a spreadsheet-derived canonical snapshot."""
    parents = [{
        "code": row["sku"], "description": row.get("name", row["sku"]),
        "is_combo": False,
        "variants": [{
            "id": row["ecomm_id"], "sku": row["sku"],
            "total_stock": row.get("stock"), "is_combo": False,
            "barcode": None, "gtin": None,
        }],
    } for row in rows]
    svc.catalog.repo.save_snapshot("ECOMM_APP_API_STAGE", [{
        "version": 1, "page": 1, "total": len(rows),
        "total_pages": 1, "per_page": 50,
        "captured_at": "2026-10-26T12:00:00+00:00", "items": parents,
    }])




def test_compares_only_unambiguous_skus_without_writes():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        svc = TiendanubePriceStockService(db)
        source = [
            {"slug": "a", "name": "Producto A", "sku": "A", "price": "120.00", "stock": "3"},
            {"slug": "b", "name": "Producto B", "sku": "B", "price": "50.00", "stock": "0"},
            {"slug": "c", "name": "Producto C", "sku": "B", "price": "50.00", "stock": "2"},
        ]
        master = [
            {"ecomm_id": "1", "sku": "A", "list_price": "100.00", "price": "180", "stock": "5"},
            {"ecomm_id": "2", "sku": "B", "list_price": "50", "stock": "2"},
        ]
        svc.catalog.repo.save_snapshot("TIENDANUBE", source)
        save_ecomm_api_stage(svc, master)
        result = svc.report()
        assert result["summary"]["comparable_sku_rows"] == 1
        assert result["summary"]["price_different"] == 0
        assert result["summary"]["price_unavailable"] == 1
        assert result["summary"]["stock_different"] == 1
        assert result["items"][0]["price_difference"] is None
        assert result["items"][0]["ecomm_list_price"] is None
        assert result["ecomm_source"] == "ECOMM_APP_API_STAGE"
        assert result["ecomm_price_available"] is False
        assert result["items"][0]["stock_difference"] == "-2"
        assert svc.catalog.repo.snapshot("TIENDANUBE") == source
        assert len(svc.catalog.repo.snapshot("ECOMM_APP_API_STAGE")) == 1


def test_missing_values_are_not_zero():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        svc = TiendanubePriceStockService(db)
        svc.catalog.repo.save_snapshot("TIENDANUBE", [
            {"slug": "p", "name": "Product", "sku": "P", "price": None, "stock": "0"}
        ])
        save_ecomm_api_stage(svc, [
            {"ecomm_id": "1", "sku": "P", "list_price": "90", "stock": None}
        ])
        result = svc.report()
        assert result["summary"]["price_unavailable"] == 1
        assert result["summary"]["stock_unavailable"] == 1


def test_mercadolibre_unique_sku_price_is_displayed_but_stock_not_inferred():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        svc = TiendanubePriceStockService(db)
        svc.catalog.repo.save_snapshot("TIENDANUBE", [{"slug": "a", "name": "A", "sku": "A", "price": "120", "stock": "4"}])
        save_ecomm_api_stage(svc, [{"ecomm_id": "1", "sku": "A", "list_price": "110", "stock": "7"}])
        svc.catalog.repo.save_snapshot("MERCADOLIBRE_API", [
            {"external_id": "MLA123", "sku": "A", "price": "151", "stock": "999"}
        ])
        item = svc.report()["items"][0]
        assert item["ml_status"] == "ONE_SKU_CANDIDATE"
        assert item["ml_price"] == "151"
        assert item["ml_stock"] is None
        assert item["ml_listing_ids"] == ["MLA123"]
        assert svc.catalog.repo.snapshot("MERCADOLIBRE_API")[0]["stock"] == "999"


def test_mercadolibre_multiple_offers_are_not_a_single_price():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        svc = TiendanubePriceStockService(db)
        svc.catalog.repo.save_snapshot("TIENDANUBE", [{"slug": "a", "name": "A", "sku": "A", "price": "120", "stock": "4"}])
        save_ecomm_api_stage(svc, [{"ecomm_id": "1", "sku": "A", "list_price": "110", "stock": "7"}])
        svc.catalog.repo.save_snapshot("MERCADOLIBRE_API", [
            {"external_id": "MLA123", "sku": "A", "price": "151"},
            {"external_id": "MLA124", "sku": "A", "price": "169"},
        ])
        report = svc.report()
        item = report["items"][0]
        assert item["ml_status"] == "MULTIPLE_LISTINGS"
        assert item["ml_listing_count"] == 2
        assert item["ml_price"] is None
        assert report["summary"]["ml_multiple_listings"] == 1


def test_mercadolibre_no_exact_variant_sku_does_not_guess():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        svc = TiendanubePriceStockService(db)
        svc.catalog.repo.save_snapshot("TIENDANUBE", [{"slug": "a", "name": "A", "sku": "A-30", "price": "120", "stock": "4"}])
        save_ecomm_api_stage(svc, [{"ecomm_id": "1", "sku": "A-30", "list_price": "110", "stock": "7"}])
        svc.catalog.repo.save_snapshot("MERCADOLIBRE_API", [{"external_id": "MLA123", "sku": "A-60", "price": "151"}])
        item = svc.report()["items"][0]
        assert item["ml_status"] == "NO_EXACT_SKU"
        assert item["ml_price"] is None


def test_all_ml_offer_prices_are_visible_separately_without_misleading_aggregate():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        svc = TiendanubePriceStockService(db)
        svc.catalog.repo.save_snapshot("TIENDANUBE", [{"slug": "a", "name": "A", "sku": "A", "price": "120", "stock": "4"}])
        save_ecomm_api_stage(svc, [{"ecomm_id": "1", "sku": "A", "list_price": "110", "stock": "7"}])
        svc.catalog.repo.save_snapshot("MERCADOLIBRE_API", [
            {"external_id": "MLA2", "title": "Oferta 2", "sku": "A", "price": "169.00", "status": "paused"},
            {"external_id": "MLA1", "title": "Oferta 1", "sku": "A", "price": "151.00", "status": "active"},
            {"external_id": "MLA3", "title": "Oferta 3", "sku": "A", "price": None, "status": "active"},
        ])
        item = svc.report()["items"][0]
        assert item["ml_status"] == "MULTIPLE_LISTINGS"
        assert item["ml_price"] is None
        assert [offer["external_id"] for offer in item["ml_offers"]] == ["MLA1", "MLA2", "MLA3"]
        assert [offer["price"] for offer in item["ml_offers"]] == ["151.00", "169.00", None]
        assert item["ml_offers"][1]["listing_status"] == "paused"
        assert item["ml_stock"] is None


def test_legacy_ecomm_excel_and_legacy_ml_are_never_used_even_if_present():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        svc = TiendanubePriceStockService(db)
        svc.catalog.repo.save_snapshot("TIENDANUBE", [
            {"slug": "a", "name": "Producto API", "sku": "A", "price": "120", "stock": "3"}
        ])
        # Poisoned legacy values would cause a false comparison if read.
        svc.catalog.repo.save_snapshot("ECOMM_APP", [
            {"ecomm_id": "EXCEL", "sku": "A", "list_price": "1", "stock": "9999"}
        ])
        svc.catalog.repo.save_snapshot("MERCADOLIBRE", [
            {"external_id": "LEGACY_ML", "sku": "A", "price": "2"}
        ])
        save_ecomm_api_stage(svc, [
            {"ecomm_id": "API-1", "sku": "A", "stock": 7}
        ])
        report = svc.report()
        assert report["available"] is True
        assert report["items"][0]["ecomm_id"] == "API-1"
        assert report["items"][0]["ecomm_stock"] == "7"
        assert report["items"][0]["ecomm_list_price"] is None
        assert report["items"][0]["ml_status"] == "NO_SNAPSHOT"
        assert report["ml_available"] is False


def test_no_completed_api_stage_blocks_price_comparison_instead_of_using_excel():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        svc = TiendanubePriceStockService(db)
        svc.catalog.repo.save_snapshot("TIENDANUBE", [
            {"slug": "a", "name": "A", "sku": "A", "price": "50", "stock": "3"}
        ])
        svc.catalog.repo.save_snapshot("ECOMM_APP", [
            {"ecomm_id": "1", "sku": "A", "list_price": "40", "stock": "3"}
        ])
        result = svc.report()
        assert result["available"] is False
        assert result["items"] == []
        assert "Excel" in result["warning"]


def test_mixed_api_and_tn_skus_do_not_guess_identity():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        svc = TiendanubePriceStockService(db)
        svc.catalog.repo.save_snapshot("TIENDANUBE", [
            {"slug": "a", "name": "A", "sku": "A", "price": "50", "stock": "3"}
        ])
        save_ecomm_api_stage(svc, [
            {"ecomm_id": "1", "sku": "A", "stock": 4},
            {"ecomm_id": "2", "sku": "A", "stock": 6},
        ])
        report = svc.report()
        assert report["available"]
        assert report["summary"]["comparable_sku_rows"] == 0


def test_tn_ml_price_difference_calculated_only_for_one_api_offer():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        svc = TiendanubePriceStockService(db)
        svc.catalog.repo.save_snapshot("TIENDANUBE", [
            {"slug": "a", "name": "A", "sku": "A", "price": "120", "stock": "4"}
        ])
        save_ecomm_api_stage(svc, [
            {"ecomm_id": "1", "sku": "A", "stock": 7},
        ])
        svc.catalog.repo.save_snapshot("MERCADOLIBRE_API", [
            {"external_id": "MLA123", "sku": "A", "price": "100"}
        ])
        result = svc.report()
        assert result["items"][0]["tn_ml_price_difference"] == "20"
        assert result["items"][0]["tn_ml_price_difference_pct"] == "20.00"
        assert result["summary"]["tn_ml_price_different"] == 1
