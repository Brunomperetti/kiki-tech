from unittest.mock import patch
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.database.models import Base, TiendanubeAiDraftRecord
from app.services.tiendanube_ai_draft_review_service import TiendanubeAiDraftReviewService


def test_saved_draft_human_review_and_stale_block():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        service = TiendanubeAiDraftReviewService(db)
        row = {"slug": "a", "name": "Avena 500g", "brand": "Marca", "description_present": False}
        service.ai.proposals.catalog.repo.save_snapshot("TIENDANUBE", [row])
        service.ai.draft = lambda _key: {"title": "Marca Avena 500g", "description": "",
                                           "questions": [], "status": "AI_DRAFT_UNVERIFIED"}
        class Settings:
            kiki_ai_enabled = True
            kiki_ai_api_key = "test-only"
            kiki_ai_daily_request_limit = 10
            kiki_ai_min_regenerate_hours = 24
        with patch("app.services.tiendanube_ai_draft_review_service.get_settings", return_value=Settings()):
            result = service.generate_and_save("a")
        assert result["status"] == "PENDING_REVIEW"
        assert result["stale"] is False
        reviewed = service.review("a", "APPROVED_INTERNAL", "Verificado por el equipo")
        assert reviewed["status"] == "APPROVED_INTERNAL"
        assert len(reviewed["history"]) == 2
        with pytest.raises(ValueError):
            service.review("a", "REJECTED", "Rechazo posterior sin regenerar")
        service.ai.proposals.catalog.repo.save_snapshot("TIENDANUBE", [
            {**row, "brand": "Otra Marca"}])
        assert service.view("a")["stale"] is True
        assert service.view("a")["status"] == "STALE"
        with pytest.raises(ValueError, match="cambió"):
            service.review("a", "REJECTED", "El fabricante cambió la marca")
        assert db.query(TiendanubeAiDraftRecord).count() == 1


def test_missing_product_cannot_generate_or_review():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        service = TiendanubeAiDraftReviewService(db)
        with pytest.raises(ValueError):
            service.generate_and_save("missing")
        with pytest.raises(ValueError):
            service.review("missing", "APPROVED_INTERNAL", "Razón suficiente de revisión")
