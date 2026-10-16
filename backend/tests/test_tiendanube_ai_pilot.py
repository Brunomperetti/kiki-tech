import json
from unittest.mock import patch
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.database.models import Base
from app.services.tiendanube_ai_pilot_service import TiendanubeAiPilotService


class FakeResponse:
    def __enter__(self):
        return self
    def __exit__(self, *_args):
        return False
    def read(self, _size):
        return json.dumps({"choices": [{"message": {"content": json.dumps({
            "title": "Avena 500 g", "description": "", "questions": ["¿Qué ingredientes contiene?"]
        })}}]}).encode()


def test_ai_draft_uses_existing_evidence_and_no_external_catalog_writes():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        svc = TiendanubeAiPilotService(db)
        original = [{"slug": "avena", "sku": "A", "name": "Avena 500 g",
                     "brand": "Marca A", "category": "", "description_present": False}]
        svc.proposals.catalog.repo.save_snapshot("TIENDANUBE", original)
        class Settings:
            kiki_ai_enabled = True
            kiki_ai_api_key = "test-only"
            kiki_ai_model = "gpt-4.1-mini"
        with patch("app.services.tiendanube_ai_pilot_service.get_settings", return_value=Settings()):
            with patch("app.services.tiendanube_ai_pilot_service.urlopen", return_value=FakeResponse()) as mock:
                result = svc.draft("avena")
                sent = json.loads(mock.call_args.args[0].data)
        assert result["status"] == "AI_DRAFT_UNVERIFIED"
        assert "Avena 500 g" in sent["messages"][1]["content"]
        assert "test-only" not in sent["messages"][1]["content"]
        assert svc.proposals.catalog.repo.snapshot("TIENDANUBE") == original


def test_ai_disabled_rejects_request():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        class Settings:
            kiki_ai_enabled = False
            kiki_ai_api_key = ""
        with patch("app.services.tiendanube_ai_pilot_service.get_settings", return_value=Settings()):
            with pytest.raises(RuntimeError, match="IA no configurada"):
                TiendanubeAiPilotService(db).draft("x")
