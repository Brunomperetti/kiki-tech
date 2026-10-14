import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database.models import Base, TiendanubeMatchDecision
from app.services.tiendanube_assisted_match_service import TiendanubeAssistedMatchService


def test_batch_reject_requires_preview_and_preserves_external_snapshots():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        svc = TiendanubeAssistedMatchService(db)
        tn = [{"slug": "product-a", "name": "Producto Marca 500 gramos", "sku": "OTHER1",
               "brand": "Marca"}]
        ec = [{"ecomm_id": "E1", "sku": "EC1", "name": "Producto Marca 500 gramos",
               "brand": "Marca"}]
        svc.catalog.repo.save_snapshot("TIENDANUBE", tn)
        svc.catalog.repo.save_snapshot("ECOMM_APP", ec)
        key = svc.report()["items"][0]["source_key"]
        assert svc.bulk_preview([key])["count"] == 1
        with pytest.raises(ValueError):
            svc.bulk_reject([key], "no")
        assert svc.bulk_reject([key], "Rechazado tras revisión manual")["updated"] == 1
        record = db.query(TiendanubeMatchDecision).one()
        assert record.status == "REJECTED"
        assert len(record.history) == 1
        with pytest.raises(ValueError):
            svc.bulk_reject([key], "Volver a rechazar sin revisión")
        assert svc.catalog.repo.snapshot("TIENDANUBE") == tn
        assert svc.catalog.repo.snapshot("ECOMM_APP") == ec


def test_batch_reject_prevents_duplicate_keys_and_too_many_items():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        svc = TiendanubeAssistedMatchService(db)
        with pytest.raises(ValueError):
            svc.bulk_preview(["x", "x"])
        with pytest.raises(ValueError):
            svc.bulk_preview([str(i) for i in range(51)])
