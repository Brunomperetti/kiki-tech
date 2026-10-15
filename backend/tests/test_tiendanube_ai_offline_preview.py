import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database.models import Base
from app.services.tiendanube_ai_offline_preview_service import TiendanubeAiOfflinePreviewService


def test_offline_simulation_uses_source_facts_and_does_not_write():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        svc = TiendanubeAiOfflinePreviewService(db)
        original = [{"slug": "avena", "sku": "A1", "name": "Avena 500 g",
                     "brand": "Granix", "category": "Cereales",
                     "description_present": False}]
        svc.proposals.catalog.repo.save_snapshot("TIENDANUBE", original)
        result = svc.preview("avena")
        assert result["status"] == "OFFLINE_SIMULATION"
        assert result["title"] == "Granix · Avena 500 g"
        assert result["description"] == ""
        assert result["questions"]
        assert result["evidence"]
        assert svc.proposals.catalog.repo.snapshot("TIENDANUBE") == original
        with pytest.raises(ValueError):
            svc.preview("no-existe")
