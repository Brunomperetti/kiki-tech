from unittest.mock import patch
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.database.models import Base
from app.services.tiendanube_ai_draft_review_service import TiendanubeAiDraftReviewService


class Settings:
    kiki_ai_enabled = True
    kiki_ai_api_key = "test"
    kiki_ai_daily_request_limit = 1
    kiki_ai_min_regenerate_hours = 24


def test_ai_quotas_prevent_repeat_and_second_product():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        service = TiendanubeAiDraftReviewService(db)
        service.ai.proposals.catalog.repo.save_snapshot("TIENDANUBE", [
            {"slug": "a", "name": "Avena", "description_present": False},
            {"slug": "b", "name": "Harina", "description_present": False},
        ])
        calls = []
        def fake_draft(key):
            calls.append(key)
            return {"title": key, "description": "", "questions": []}
        service.ai.draft = fake_draft
        with patch("app.services.tiendanube_ai_draft_review_service.get_settings", return_value=Settings()):
            service.generate_and_save("a")
            with pytest.raises(ValueError, match="borrador reciente"):
                service.generate_and_save("a")
            with pytest.raises(ValueError, match="límite diario"):
                service.generate_and_save("b")
        assert calls == ["a"]
