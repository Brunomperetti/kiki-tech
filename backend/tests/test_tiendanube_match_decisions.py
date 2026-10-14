import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.database.models import Base, TiendanubeMatchDecision
from app.services.tiendanube_assisted_match_service import TiendanubeAssistedMatchService


def test_match_decisions_persist_history_without_external_writes():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        service = TiendanubeAssistedMatchService(db)
        tn = [{"slug": "avena", "sku": "TN1", "name": "Avena Granix 400 gr", "brand": "Granix"}]
        ec = [{"ecomm_id": "E1", "sku": "LOC1", "name": "Avena Granix 400 gr", "brand": "Granix"}]
        service.catalog.repo.save_snapshot("TIENDANUBE", tn)
        service.catalog.repo.save_snapshot("ECOMM_APP", ec)
        report = service.report()
        key = report["items"][0]["source_key"]
        with pytest.raises(ValueError):
            service.decide(key, "wrong", "APPROVED", "Revisado por equipo")
        assert service.decide(key, "E1", "APPROVED", "Marca y presentación verificadas")["status"] == "APPROVED"
        assert service.decide(key, None, "REJECTED", "Se detectó otro código interno")["status"] == "REJECTED"
        row = db.query(TiendanubeMatchDecision).one()
        assert len(row.history) == 2
        assert row.target_ecomm_id is None
        assert service.report()["items"][0]["decision"]["status"] == "REJECTED"
        assert service.catalog.repo.snapshot("TIENDANUBE") == tn
        assert service.catalog.repo.snapshot("ECOMM_APP") == ec


def test_reject_invalid_short_reason():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        service = TiendanubeAssistedMatchService(db)
        with pytest.raises(ValueError):
            service.decide("unused", None, "REJECTED", "no")
