import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database.models import Base
from app.services.tiendanube_image_audit_service import TiendanubeImageAuditService


def test_image_import_and_conservative_unique_sku_matching():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        service = TiendanubeImageAuditService(db)
        catalog = [
            {"slug": "one", "name": "One", "sku": "123"},
            {"slug": "two", "name": "Two", "sku": "456"},
            {"slug": "three", "name": "Three", "sku": "456"},
        ]
        service.repo.save_snapshot("TIENDANUBE", catalog)
        csv_data = (
            "store_id,product_id,product_name,image_url,sku\n"
            "1,100,One,https://cdn.example.com/a.jpg,123\n"
            "1,100,One,https://cdn.example.com/b.jpg,123\n"
            "1,101,Two,https://cdn.example.com/c.jpg,456\n"
            "1,102,Other,https://cdn.example.com/d.jpg,555.0\n"
        ).encode()
        imported = service.import_csv(csv_data)
        result = service.report()
        assert imported["images"] == 4
        assert result["summary"]["MATCHED_SKU"] == 1
        assert result["summary"]["AMBIGUOUS_SKU"] == 1
        assert result["summary"]["UNMATCHED_SKU"] == 1
        assert result["items"][0]["image_count"] == 2
        assert service.repo.snapshot("TIENDANUBE") == catalog


def test_reject_invalid_image_url():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        service = TiendanubeImageAuditService(db)
        with pytest.raises(ValueError):
            service.import_csv(
                b"store_id,product_id,product_name,image_url,sku\n1,2,A,http://example.com/a.png,X\n"
            )
