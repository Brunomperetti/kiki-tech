import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.database.models import Base, TiendanubeMatchDecision
from app.services.tiendanube_assisted_match_service import TiendanubeAssistedMatchService



def save_api_catalog(svc, records):
    """Fixtures from the Public API captured stage; no Ecomm XLSX."""
    parents = [
        {
            "code": row["sku"], "description": row["name"],
            "is_combo": False,
            "variants": [{
                "id": row["ecomm_id"], "sku": row["sku"],
                "total_stock": 3, "is_combo": False,
                "gtin": None, "barcode": None,
            }]
        }
        for row in records
    ]
    svc.catalog.repo.save_snapshot("ECOMM_APP_API_STAGE", [
        {
            "version": 1, "page": 1, "total": len(records),
            "total_pages": 1, "per_page": 50,
            "captured_at": "2026-10-26T12:00:00+00:00",
            "items": parents,
        }
    ])


def test_match_decisions_persist_history_without_external_writes():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        service = TiendanubeAssistedMatchService(db)
        tn = [{"slug": "avena", "sku": "TN1", "name": "Avena Granix 400 gr", "brand": "Granix"}]
        ec = [{"ecomm_id": "E1", "sku": "LOC1", "name": "Avena Granix 400 gr", "brand": "Granix"}]
        service.catalog.repo.save_snapshot("TIENDANUBE", tn)
        save_api_catalog(service, ec)
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
        assert len(service.catalog.repo.snapshot("ECOMM_APP_API_STAGE")) == 1


def test_reject_invalid_short_reason():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        service = TiendanubeAssistedMatchService(db)
        with pytest.raises(ValueError):
            service.decide("unused", None, "REJECTED", "no")
