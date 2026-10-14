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
