from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database.models import Base
from app.services.gtin_candidate_service import GtinCandidateService


def product(pid, name, ean=None, brand=None):
    return {"product": {"ecomm_id": pid, "name": name, "ean": ean, "brand": brand, "sku": pid}}


def test_exact_title_only_and_checksum_validation():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        service = GtinCandidateService(db)
        valid = "4006381333931"
        service.review.readiness.report = lambda: {"items": [
            product("A", "YERBA MATE 500G"),
            product("B", "Yerba Mate 500g", valid, "Marca X"),
            product("C", "Yerba Mate 1kg", "4006381333931", "Marca X"),
            product("D", "Yerba Mate 500g", "4006381333932", "Marca X"),
        ]}
        result = service.candidates("ECOMM:A")
        assert len(result["candidates"]) == 1
        assert result["candidates"][0]["ean"] == valid
        assert result["candidates"][0]["confidence"] == "CANDIDATE_ONLY"


def test_conflicting_valid_codes_are_not_proposed():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        service = GtinCandidateService(db)
        service.review.readiness.report = lambda: {"items": [
            product("A", "Yerba Mate 500g"),
            product("B", "Yerba Mate 500g", "4006381333931"),
            product("C", "Yerba Mate 500g", "5901234123457"),
        ]}
        result = service.candidates("ECOMM:A")
        assert not result["candidates"]
        assert "diferentes" in result["message"]


def test_missing_product_is_rejected():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        service = GtinCandidateService(db)
        service.review.readiness.report = lambda: {"items": []}
        import pytest
        with pytest.raises(ValueError, match="no encontrado"):
            service.candidates("ECOMM:unknown")
