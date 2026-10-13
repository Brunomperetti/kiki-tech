import json
from io import BytesIO
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database.models import Base
from app.services.external_gtin_candidate_service import ExternalGtinCandidateService


class Response:
    def __init__(self, products):
        self.buffer = BytesIO(json.dumps({"products": products}).encode())
    def __enter__(self):
        return self.buffer
    def __exit__(self, *args):
        return False


def test_external_candidates_do_not_auto_accept_and_require_exact_pack():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        svc = ExternalGtinCandidateService(db)
        svc.review.readiness.report = lambda: {"items": [{"product": {
            "ecomm_id": "21", "name": "Yerba mate 500 g", "ean": None, "brand": "Pampa",
        }}]}
        products = [
            {"code": "4006381333931", "product_name": "Yerba mate 500 g", "brands": "Pampa", "quantity": "500 g"},
            {"code": "5901234123457", "product_name": "Yerba mate 1 kg", "brands": "Pampa", "quantity": "1 kg"},
            {"code": "4006381333932", "product_name": "Yerba mate 500 g", "brands": "Pampa", "quantity": "500 g"},
        ]
        with patch("urllib.request.urlopen", return_value=Response(products)):
            result = svc.lookup("ECOMM:21")
        assert len(result["candidates"]) == 1
        assert result["candidates"][0]["ean"] == "4006381333931"
        assert result["candidates"][0]["confidence"] == "REQUIRES_REVIEW"
        assert result["candidates"][0]["source_url"].startswith("https://world.openfoodfacts.org/product/")


def test_external_lookup_returns_unavailable_without_fabricating():
    import urllib.error
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        svc = ExternalGtinCandidateService(db)
        svc.review.readiness.report = lambda: {"items": [{"product": {
            "ecomm_id": "21", "name": "Yerba mate 500 g", "ean": None, "brand": "Pampa",
        }}]}
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("offline")):
            result = svc.lookup("ECOMM:21")
        assert result["candidates"] == []
        assert result["unavailable"] is True
