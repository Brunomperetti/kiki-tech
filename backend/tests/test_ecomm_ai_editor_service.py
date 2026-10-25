"""AI reuse for Ecomm API: persist suggestions, cap calls, fail closed, never apply."""
import json
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database.models import (
    Base, CatalogSnapshot, EcommApiProductEdit, KikiAiEditorialDraft, KikiEcommAiDailySlot
)
from app.services.ecomm_ai_editor_service import EcommAiEditor
from app.services.ecomm_api_product_workspace_service import EcommApiProductWorkspace
from test_ecomm_api_product_workspace import capture, payload


class Settings:
    kiki_ai_enabled = True
    kiki_ai_api_key = "test-key-never-real"
    kiki_ai_model = "test-ia-model"


class FakeResponse:
    def __init__(self, title="Magnesio con Potasio 30 cápsulas", description="", questions=None):
        self.out = json.dumps({"choices": [{"message": {"content": json.dumps({
            "title": title, "description": description,
            "questions": questions if questions is not None else ["Confirmar composición de pack."],
        })}}]}).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, _):
        return self.out


def seeded(tmp_path):
    engine = create_engine("sqlite:///" + str(tmp_path / "ai.db"))
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(CatalogSnapshot(source="ECOMM_APP_API_STAGE", payload=capture()))
        db.commit()
    return engine


def test_ai_proposes_saves_immutable_and_reuses_without_extra_charge(tmp_path):
    engine = seeded(tmp_path)
    with Session(engine) as db:
        svc = EcommAiEditor(db)
        with patch("app.services.ecomm_ai_editor_service.get_settings", return_value=Settings()):
            with patch("app.services.ecomm_ai_editor_service.urlopen", return_value=FakeResponse()) as provider:
                first = svc.suggest("101", 0)
                assert first["title"] == "Magnesio con Potasio 30 cápsulas"
                assert first["saved_to_product_fields"] is False
                assert first["remaining_today"] == 9
                assert first["source_current"] is True
                second = svc.suggest("101", 0)
                assert second["draft_id"] == first["draft_id"]
                assert second["reused"] is True
                provider.assert_called_once()
        assert len(db.scalars(select(KikiEcommAiDailySlot)).all()) == 1
        assert len(db.scalars(select(KikiAiEditorialDraft)).all()) == 1
        assert db.scalars(select(EcommApiProductEdit)).all() == []
    with Session(engine) as db:
        latest = EcommAiEditor(db).latest("101")
        assert latest["draft"]["title"] == "Magnesio con Potasio 30 cápsulas"
        assert latest["draft"]["source_current"] is True
        assert latest["available"] is True
        assert db.scalar(select(CatalogSnapshot).where(
            CatalogSnapshot.source == "ECOMM_APP_API_STAGE"
        )).payload == capture()


def test_editing_operator_fields_invalidates_ai_proposal(tmp_path):
    engine = seeded(tmp_path)
    with Session(engine) as db:
        with patch("app.services.ecomm_ai_editor_service.get_settings", return_value=Settings()):
            with patch("app.services.ecomm_ai_editor_service.urlopen", return_value=FakeResponse(
                title="Pack x2 Magnesio con Potasio 60 cápsulas"
            )):
                result = EcommAiEditor(db).suggest("102", 0)
        assert result["source_current"]
        EcommApiProductWorkspace(db).save(
            "102", payload(title="", description=""), "DRAFT", 0
        )
        assert not EcommAiEditor(db).latest("102")["draft"]["source_current"]
        with patch("app.services.ecomm_ai_editor_service.get_settings", return_value=Settings()):
            with patch("app.services.ecomm_ai_editor_service.urlopen") as provider:
                with pytest.raises(ValueError, match="otra sesión"):
                    EcommAiEditor(db).suggest("102", 0)
                provider.assert_not_called()


def test_invalid_model_invented_quantity_consumes_attempt_without_draft(tmp_path):
    engine = seeded(tmp_path)
    with Session(engine) as db:
        with patch("app.services.ecomm_ai_editor_service.get_settings", return_value=Settings()):
            with patch("app.services.ecomm_ai_editor_service.urlopen",
                       return_value=FakeResponse(title="Magnesio x 999 cápsulas")):
                with pytest.raises(RuntimeError, match="controles"):
                    EcommAiEditor(db).suggest("101", 0)
        assert len(db.scalars(select(KikiEcommAiDailySlot)).all()) == 1
        assert db.scalars(select(KikiAiEditorialDraft)).all() == []
        assert db.scalars(select(EcommApiProductEdit)).all() == []


def test_unconfigured_ai_makes_no_paid_request_or_mutation(tmp_path):
    engine = seeded(tmp_path)
    class Disabled(Settings):
        kiki_ai_enabled = False
    with Session(engine) as db:
        with patch("app.services.ecomm_ai_editor_service.get_settings", return_value=Disabled()):
            with patch("app.services.ecomm_ai_editor_service.urlopen") as provider:
                with pytest.raises(RuntimeError, match="habilitada"):
                    EcommAiEditor(db).suggest("101", 0)
                provider.assert_not_called()
        assert db.scalars(select(KikiEcommAiDailySlot)).all() == []


def test_quota_and_unique_reservations(tmp_path):
    engine = seeded(tmp_path)
    with Session(engine) as db:
        editor = EcommAiEditor(db)
        for i in range(10):
            editor._reserve("101")
        assert editor._remaining() == 0
        with patch("app.services.ecomm_ai_editor_service.get_settings", return_value=Settings()):
            with patch("app.services.ecomm_ai_editor_service.urlopen") as provider:
                with pytest.raises(ValueError, match="límite"):
                    editor.suggest("101", 0)
                provider.assert_not_called()
        assert len(db.scalars(select(KikiEcommAiDailySlot)).all()) == 10



def test_pack_per_unit_and_container_inference_is_withheld_but_title_remains(tmp_path):
    """Regression: pack x2 60 caps does NOT imply 2 bottles of 60 each."""
    engine = seeded(tmp_path)
    with Session(engine) as db:
        with patch("app.services.ecomm_ai_editor_service.get_settings", return_value=Settings()):
            with patch("app.services.ecomm_ai_editor_service.urlopen", return_value=FakeResponse(
                title="Pack x2 Magnesio con Potasio 60 cápsulas sabor sin sabor",
                description=(
                    "Pack que incluye dos frascos de Magnesio con Potasio, "
                    "cada uno con 60 cápsulas."
                ),
                questions=["Confirmar si son dos frascos de 60 cada uno."],
            )) as provider:
                first = EcommAiEditor(db).suggest("102", 0)
                assert first["title"] == "Pack x2 Magnesio con Potasio 60 cápsulas"
                assert first["description"] == ""
                assert first["warnings"]
                assert any("composición" in q.lower() for q in first["questions"])
                again = EcommAiEditor(db).suggest("102", 0)
                assert again["reused"] is True
                assert again["description"] == ""
                provider.assert_called_once()
        assert len(db.scalars(select(KikiEcommAiDailySlot)).all()) == 1


def test_old_cached_unsafe_draft_is_redacted_on_retrieval_no_new_call(tmp_path):
    """Existing user draft #2 must be reviewed under the newer policy."""
    engine = seeded(tmp_path)
    with Session(engine) as db:
        with patch("app.services.ecomm_ai_editor_service.get_settings", return_value=Settings()):
            with patch("app.services.ecomm_ai_editor_service.urlopen", return_value=FakeResponse(
                title="Pack x2 Magnesio con Potasio 60 cápsulas",
            )):
                EcommAiEditor(db).suggest("102", 0)
        old = db.scalars(select(KikiAiEditorialDraft)).one()
        old.title = "Pack x2 Magnesio con Potasio 60 cápsulas sabor sin sabor"
        old.description = (
            "Pack que incluye dos frascos de Magnesio con Potasio, "
            "cada uno con 60 cápsulas sabor sin sabor."
        )
        db.commit()
        current = EcommAiEditor(db).latest("102")["draft"]
        assert current["source_current"] is True
        assert current["description"] == ""
        assert "sabor sin sabor" not in current["title"].lower()
        assert current["warnings"]
        assert EcommAiEditor(db).suggest("102", 0)["reused"] is True
        # Keep historical audit intact; only the served version is guarded.
        assert db.scalars(select(KikiAiEditorialDraft)).one().description.startswith(
            "Pack que incluye dos frascos"
        )


def test_product_id_or_sku_digits_cannot_justify_commercial_quantity(tmp_path):
    engine = seeded(tmp_path)
    with Session(engine) as db:
        with patch("app.services.ecomm_ai_editor_service.get_settings", return_value=Settings()):
            with patch("app.services.ecomm_ai_editor_service.urlopen", return_value=FakeResponse(
                title="Magnesio x 101 cápsulas"
            )):
                with pytest.raises(RuntimeError, match="controles"):
                    EcommAiEditor(db).suggest("101", 0)
        assert db.scalars(select(KikiAiEditorialDraft)).all() == []


def test_source_explicit_pack_per_unit_detail_can_be_used(tmp_path):
    engine = seeded(tmp_path)
    with Session(engine) as db:
        snap = db.scalars(select(CatalogSnapshot)).one()
        revised = json.loads(json.dumps(snap.payload))
        revised[0]["items"][1]["description"] = (
            "Pack x2 frascos de Magnesio con Potasio, 60 cápsulas cada uno"
        )
        snap.payload = revised
        db.commit()
        with patch("app.services.ecomm_ai_editor_service.get_settings", return_value=Settings()):
            with patch("app.services.ecomm_ai_editor_service.urlopen", return_value=FakeResponse(
                title="Pack x2 frascos de Magnesio con Potasio, 60 cápsulas cada uno",
                description="Pack x2 frascos, 60 cápsulas cada uno.",
            )):
                proposal = EcommAiEditor(db).suggest("102", 0)
        assert proposal["description"] == "Pack x2 frascos, 60 cápsulas cada uno."
        assert proposal["warnings"] == []
