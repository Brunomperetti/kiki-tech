import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database.models import Base
from app.services.gtin_batch_pilot_service import GtinBatchPilotService


def test_pilot_caps_external_calls_and_does_not_write(monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        service = GtinBatchPilotService(db)
        rows = [{"product": {"ecomm_id": str(i), "sku": str(i), "name": f"Producto {i}", "ean": None}} for i in range(20)]
        monkeypatch.setattr(service.review.readiness, "report", lambda: {"items": rows})
        monkeypatch.setattr(service.internal, "candidates", lambda key: {"candidates": [], "message": "sin resultado"})
        queried = []
        def external(key):
            queried.append(key)
            return {"candidates": [], "message": "Sin coincidencias"}
        monkeypatch.setattr(service.external, "lookup", external)
        result = service.run([f"ECOMM:{i}" for i in range(20)])
        assert result["requested"] == 20
        assert len(queried) == 5
        assert result["summary"]["external_not_checked"] == 15
        assert result["summary"]["no_candidate"] == 5
        assert all(item["status"] == "external_not_checked" for item in result["items"] if not item["external_checked"])
        assert len(result["items"]) == 20


def test_pilot_rejects_duplicates_and_more_than_20():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        service = GtinBatchPilotService(db)
        with pytest.raises(ValueError, match="entre 1 y 20"):
            service.run(["ECOMM:1", "ECOMM:1"])
        with pytest.raises(ValueError, match="entre 1 y 20"):
            service.run([str(i) for i in range(21)])


def test_bulk_or_fractioned_products_are_deprioritized(monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        service = GtinBatchPilotService(db)
        rows = [
            {"product": {"ecomm_id": "a", "sku": "a", "name": "CARDO MARIANO SUELTO X 50 GRS", "ean": None}},
            {"product": {"ecomm_id": "b", "sku": "b", "name": "Galletitas marca envase 200g", "brand": "Marca", "ean": None}},
        ]
        monkeypatch.setattr(service.review.readiness, "report", lambda: {"items": rows})
        monkeypatch.setattr(service.internal, "candidates", lambda key: {"candidates": []})
        requested = []
        def external(key):
            requested.append(key)
            return {"candidates": [], "message": "Sin coincidencias"}
        monkeypatch.setattr(service.external, "lookup", external)
        result = service.run(["ECOMM:a", "ECOMM:b"])
        assert requested == ["ECOMM:b"]
        assert result["summary"]["external_not_checked"] == 1
        assert result["summary"]["no_candidate"] == 1
