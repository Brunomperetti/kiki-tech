import json
from unittest.mock import patch
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from app.database.models import Base, KikiAiDailyPilotAttempt
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
            "title": "Avena", "description": "", "questions": []
        })}}]}).encode()


def seed(db):
    svc = TiendanubeAiPilotService(db)
    svc.proposals.catalog.repo.save_snapshot("TIENDANUBE", [
        {"slug": "avena", "sku": "A", "name": "Avena", "brand": "",
         "category": "", "description_present": False}
    ])
    return svc


def test_one_paid_attempt_per_utc_day(tmp_path):
    engine = create_engine("sqlite:///" + str(tmp_path / "ai.db"))
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        svc = seed(db)
        with patch("app.services.tiendanube_ai_pilot_service.get_settings", return_value=Settings()):
            with patch("app.services.tiendanube_ai_pilot_service.urlopen", return_value=FakeResponse()) as mocked:
                result = svc.draft("avena")
                assert result["status"] == "AI_DRAFT_UNVERIFIED"
                with pytest.raises(ValueError, match="único intento diario"):
                    svc.draft("avena")
                assert mocked.call_count == 1
        rows = db.scalars(select(KikiAiDailyPilotAttempt)).all()
        assert len(rows) == 1 and rows[0].status == "COMPLETED"


def test_failed_request_also_consumes_slot(tmp_path):
    engine = create_engine("sqlite:///" + str(tmp_path / "failed.db"))
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        svc = seed(db)
        with patch("app.services.tiendanube_ai_pilot_service.get_settings", return_value=Settings()):
            with patch("app.services.tiendanube_ai_pilot_service.urlopen", side_effect=TimeoutError):
                with pytest.raises(RuntimeError):
                    svc.draft("avena")
            with patch("app.services.tiendanube_ai_pilot_service.urlopen") as mocked:
                with pytest.raises(ValueError, match="único intento diario"):
                    svc.draft("avena")
                mocked.assert_not_called()
