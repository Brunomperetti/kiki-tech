from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database.models import Base
from app.services.tiendanube_csv_service import TiendanubeCsvService


def test_duplicate_sku_groups_distinguish_variants_and_conflicts():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        svc = TiendanubeCsvService(db)
        svc.repo.save_snapshot("TIENDANUBE", [
            {"slug": "tea", "name": "Tea red", "sku": "A", "variant": [{"property": "Color", "value": "red"}]},
            {"slug": "tea", "name": "Tea blue", "sku": "A", "variant": [{"property": "Color", "value": "blue"}]},
            {"slug": "rice", "name": "Rice", "sku": "B", "variant": []},
            {"slug": "flour", "name": "Flour", "sku": "B", "variant": []},
            {"slug": "sugar", "name": "Sugar", "sku": "C", "variant": []},
        ])
        result = svc.duplicate_sku_review()
        assert result["summary"]["groups"] == 2
        assert result["summary"]["affected_rows"] == 4
        assert result["groups"][0]["status"] == "POSSIBLE_SHARED_SKU_VARIANTS"
        assert result["groups"][1]["status"] == "CROSS_PRODUCT_SKU_CONFLICT"
        assert len(svc.repo.snapshot("TIENDANUBE")) == 5
