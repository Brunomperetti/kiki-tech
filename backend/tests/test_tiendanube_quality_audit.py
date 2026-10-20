from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database.models import Base
from app.services.tiendanube_quality_audit_service import TiendanubeQualityAuditService, gtin_status


def test_gtin_check_digit_is_not_automatic_authenticity():
    assert gtin_status("4006381333931") == "VALID_CHECK_DIGIT"
    assert gtin_status("4006381333932") == "INVALID_CHECK_DIGIT"
    assert gtin_status("7798010000000.0") == "UNVERIFIED_FORMAT"
    assert gtin_status("") == "MISSING"


def test_quality_audit_groups_variants_and_never_assumes_missing_images():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        svc = TiendanubeQualityAuditService(db)
        rows = [
            {"slug": "tea", "name": "Té", "sku": "A", "brand": "Marca", "category": "Infusiones",
             "description_present": True, "ean_raw": "4006381333931"},
            {"slug": "tea", "name": "Té", "sku": "B", "brand": "Marca", "category": "Infusiones",
             "description_present": True, "ean_raw": "4006381333931"},
            {"slug": "herbs", "name": "Hierbas", "sku": "C", "brand": "",
             "category": "", "description_present": False, "ean_raw": ""},
        ]
        svc.catalog.repo.save_snapshot("TIENDANUBE", rows)
        result = svc.report()
        assert result["summary"]["products"] == 2
        assert result["summary"]["GTIN_REPEATED"] == 1
        assert result["summary"]["BRAND_MISSING"] == 1
        assert all(item["image_status"] == "NOT_EVALUATED" for item in result["items"])
        assert svc.catalog.repo.snapshot("TIENDANUBE") == rows


def test_repeated_gtin_identifies_other_products_without_guessing_identity():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        svc = TiendanubeQualityAuditService(db)
        svc.catalog.repo.save_snapshot("TIENDANUBE", [
            {"slug": "jabon-jazmin", "name": "Jabón jazmín 100 g", "sku": "J100", "brand": "Sri Sri",
             "category": "Jabones", "description_present": True, "ean_raw": "4006381333931"},
            {"slug": "jabon-menta", "name": "Jabón menta 100 g", "sku": "M100", "brand": "Sri Sri",
             "category": "Jabones", "description_present": True, "ean_raw": "4006381333931"},
            {"slug": "crema", "name": "Crema", "sku": "C", "brand": "Otra",
             "category": "Cremas", "description_present": True, "ean_raw": "4006381333932"},
        ])
        report = svc.report()
        product = next(x for x in report["items"] if x["sku"] == "J100")
        assert "GTIN_REPEATED" in product["issues"]
        assert product["gtin_conflicts"][0]["gtin"] == "4006381333931"
        assert product["gtin_conflicts"][0]["occurrences"] == 2
        assert product["gtin_conflicts"][0]["other_products"][0]["sku"] == "M100"
        assert all(x["sku"] != "C" for x in product["gtin_conflicts"][0]["other_products"])
        assert product["gtin_conflicts"][0]["repeated_within_product"] is False


def test_repeated_gtin_inside_same_product_shows_variant_warning():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        svc = TiendanubeQualityAuditService(db)
        svc.catalog.repo.save_snapshot("TIENDANUBE", [
            {"slug": "jabon", "name": "Jabón", "sku": "J-1", "brand": "Marca",
             "category": "Cuidado", "description_present": True, "ean_raw": "4006381333931"},
            {"slug": "jabon", "name": "Jabón", "sku": "J-2", "brand": "Marca",
             "category": "Cuidado", "description_present": True, "ean_raw": "4006381333931"},
        ])
        entry = svc.report()["items"][0]["gtin_conflicts"][0]
        assert entry["repeated_within_product"] is True
        assert entry["other_products"] == []
