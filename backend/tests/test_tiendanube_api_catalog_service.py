"""New TN-to-Ecomm comparison must never consume an Ecomm XLSX snapshot."""
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database.models import Base
from app.services.tiendanube_api_catalog_service import TiendanubeApiCatalogService


def stage(parents, *, total_pages=1):
    return [{
        "version": 1, "page": 1, "total": len(parents),
        "total_pages": total_pages, "per_page": 50,
        "captured_at": "2026-10-26T12:00:00+00:00",
        "items": parents,
    }]


def parent(pid, sku, stock, combo=False):
    return {
        "code": sku, "description": "Artículo", "is_combo": combo,
        "variants": [{
            "id": pid, "sku": sku, "total_stock": stock,
            "is_combo": combo, "barcode": None, "gtin": None
        }],
    }


def test_tn_api_report_ignores_old_spreadsheet_and_checks_exact_unique_sku():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        svc = TiendanubeApiCatalogService(db)
        svc.repo.save_snapshot("TIENDANUBE", [
            {"slug": "a", "name": "A", "sku": "A", "stock": "9", "price": "99"},
            {"slug": "b", "name": "B", "sku": "B", "stock": "0", "price": "90"},
            {"slug": "c", "name": "C", "sku": "D", "stock": "2", "price": "22"},
            {"slug": "d", "name": "D", "sku": "D", "stock": "3", "price": "33"},
        ])
        svc.repo.save_snapshot("ECOMM_APP", [
            {"ecomm_id": "OLD", "sku": "A", "stock": 999, "list_price": 1},
            {"ecomm_id": "OLD-B", "sku": "B", "stock": 999, "list_price": 1},
        ])
        svc.repo.save_snapshot("ECOMM_APP_API_STAGE", stage([
            parent("API-A", "A", 4),
            parent("API-B1", "B", 8),
            parent("API-B2", "B", 10),
            parent("API-D", "D", 5),
        ]))
        result = svc.report()
        assert result["available"]
        assert result["ecomm_source"] == "ECOMM_APP_API_STAGE"
        assert result["summary"]["MATCHED_SKU"] == 1
        assert result["summary"]["SKU_AMBIGUOUS_ECOMM"] == 1
        assert result["summary"]["SKU_DUPLICATE_TN"] == 2
        assert result["items"][0]["matched_ecomm_id"] == "API-A"
        assert result["items"][0]["ecomm_stock_at_capture"] == 4
        assert result["items"][1]["matched_ecomm_id"] is None
        assert result["external_writes_enabled"] is False
        assert svc.repo.snapshot("ECOMM_APP")[0]["ecomm_id"] == "OLD"


def test_tn_api_report_fails_closed_without_full_capture():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        svc = TiendanubeApiCatalogService(db)
        svc.repo.save_snapshot("TIENDANUBE", [
            {"slug": "a", "name": "A", "sku": "A", "stock": "1"}
        ])
        svc.repo.save_snapshot("ECOMM_APP", [
            {"ecomm_id": "LEGACY", "sku": "A", "stock": 100}
        ])
        missing = svc.report()
        assert missing["available"] is False
        assert missing["items"] == []
        assert "Excel" in missing["warning"]

        svc.repo.save_snapshot("ECOMM_APP_API_STAGE", stage([
            parent("P", "A", 3)
        ], total_pages=2))
        incomplete = svc.report()
        assert incomplete["available"] is False
        assert incomplete["items"] == []


def test_api_report_requires_tn_csv_without_guessing_records():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        svc = TiendanubeApiCatalogService(db)
        svc.repo.save_snapshot("ECOMM_APP_API_STAGE", stage([
            parent("P", "A", 3)
        ]))
        report = svc.report()
        assert report["available"] is False
        assert report["items"] == []
