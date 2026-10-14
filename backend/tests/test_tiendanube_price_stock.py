from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.database.models import Base
from app.services.tiendanube_price_stock_service import TiendanubePriceStockService


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
        svc.catalog.repo.save_snapshot("ECOMM_APP", master)
        result = svc.report()
        assert result["summary"]["comparable_sku_rows"] == 1
        assert result["summary"]["price_different"] == 1
        assert result["summary"]["stock_different"] == 1
        assert result["items"][0]["price_difference"] == "20.00"
        assert result["items"][0]["stock_difference"] == "-2"
        assert svc.catalog.repo.snapshot("TIENDANUBE") == source
        assert svc.catalog.repo.snapshot("ECOMM_APP") == master


def test_missing_values_are_not_zero():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        svc = TiendanubePriceStockService(db)
        svc.catalog.repo.save_snapshot("TIENDANUBE", [
            {"slug": "p", "name": "Product", "sku": "P", "price": None, "stock": "0"}
        ])
        svc.catalog.repo.save_snapshot("ECOMM_APP", [
            {"ecomm_id": "1", "sku": "P", "list_price": "90", "stock": None}
        ])
        result = svc.report()
        assert result["summary"]["price_unavailable"] == 1
        assert result["summary"]["stock_unavailable"] == 1
