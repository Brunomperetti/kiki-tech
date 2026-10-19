"""Safe editorial review of a generated KIKI AI proposal: internal only."""
import json
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database.models import Base, KikiAiEditorialDraft
from app.services.tiendanube_ai_pilot_service import TiendanubeAiPilotService


class Settings:
    kiki_ai_enabled = True
    kiki_ai_api_key = "test-only"
    kiki_ai_model = "gpt-4.1-mini"


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, _):
        return json.dumps({"choices": [{"message": {"content": json.dumps({
            "title": "Avena · Marca A", "description": "",
            "questions": ["¿Qué ingredientes declara el fabricante?"]
        })}}]}).encode()


def catalog(db, name="Avena"):
    service = TiendanubeAiPilotService(db)
    service.proposals.catalog.repo.save_snapshot("TIENDANUBE", [
        {"slug": "avena", "sku": "A", "name": name, "brand": "Marca A",
         "category": "", "description_present": False}
    ])
    return service


def generate(service):
    with patch("app.services.tiendanube_ai_pilot_service.get_settings", return_value=Settings()):
        with patch("app.services.tiendanube_ai_pilot_service.urlopen", return_value=FakeResponse()):
            return service.draft("avena")


def test_generation_is_saved_without_external_catalog_edits(tmp_path):
    engine = create_engine("sqlite:///" + str(tmp_path / "saved.db"))
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        service = catalog(db)
        result = generate(service)
        assert result["review_status"] == "PENDING_REVIEW"
        assert result["source_current"] is True
        assert result["draft_id"] > 0
        saved = service.saved("avena")
        assert saved["available"] is True
        assert saved["draft"]["title"] == "Avena · Marca A"
        assert saved["draft"]["evidence"][0]["source"] == "Tiendanube CSV"
        assert len(db.scalars(select(KikiAiEditorialDraft)).all()) == 1
        assert service.proposals.catalog.repo.snapshot("TIENDANUBE")[0]["name"] == "Avena"

    # The persisted draft can be recovered after the first database session closes.
    with Session(engine) as db:
        saved = TiendanubeAiPilotService(db).saved("avena")
        assert saved["draft"]["review_status"] == "PENDING_REVIEW"


def test_explicit_editorial_review_and_immutable_decision_history(tmp_path):
    engine = create_engine("sqlite:///" + str(tmp_path / "approved.db"))
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        service = catalog(db)
        draft = generate(service)
        with pytest.raises(ValueError, match="Confirmá"):
            service.review(draft["draft_id"], "APPROVE", "Validado con fuente", False)
        with pytest.raises(ValueError, match="entre 10 y 500"):
            service.review(draft["draft_id"], "APPROVE", "ok", True)
        accepted = service.review(draft["draft_id"], "APPROVE", "Verificado con ficha del fabricante.", True)
        assert accepted["review_status"] == "APPROVED_INTERNAL"
        assert len(accepted["history"]) == 2
        assert service.saved("avena")["draft"]["review_note"] == "Verificado con ficha del fabricante."
        with pytest.raises(ValueError, match="ya tiene una decisión"):
            service.review(draft["draft_id"], "REJECT", "Ahora me arrepentí.", True)


def test_stale_catalog_blocks_review_without_deleting_history(tmp_path):
    engine = create_engine("sqlite:///" + str(tmp_path / "stale.db"))
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        service = catalog(db)
        draft = generate(service)
        catalog(db, name="Avena modificada")
        stale = service.saved("avena")
        assert stale["available"] and stale["draft"]["source_current"] is False
        with pytest.raises(ValueError, match="El CSV cambió"):
            service.review(draft["draft_id"], "APPROVE", "Leí los datos actuales.", True)
        assert service.saved("avena")["draft"]["review_status"] == "PENDING_REVIEW"


def test_review_rejects_invalid_action(tmp_path):
    engine = create_engine("sqlite:///" + str(tmp_path / "action.db"))
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        service = catalog(db)
        draft = generate(service)
        with pytest.raises(ValueError, match="Acción de revisión inválida"):
            service.review(draft["draft_id"], "PUBLISH", "No corresponde publicar", True)


def test_rejected_draft_is_not_published(tmp_path):
    engine = create_engine("sqlite:///" + str(tmp_path / "rejected.db"))
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        service = catalog(db)
        before = service.proposals.catalog.repo.snapshot("TIENDANUBE")
        draft = generate(service)
        result = service.review(draft["draft_id"], "REJECT", "Afirmaciones aún no corroboradas", True)
        assert result["review_status"] == "REJECTED_INTERNAL"
        assert service.proposals.catalog.repo.snapshot("TIENDANUBE") == before
