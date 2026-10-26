"""AI proposals inbox: recover generated work without implying saved product edits."""
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
import pytest

from app.database.models import Base, CatalogSnapshot, KikiAiEditorialDraft, EcommApiProductEdit
from app.services.ecomm_api_product_workspace_service import EcommApiProductWorkspace
from app.services.ecomm_ai_proposal_inbox_service import list_ecomm_ai_proposals
from test_ecomm_api_product_workspace import capture, payload


def build_db(tmp_path):
    engine = create_engine("sqlite:///" + str(tmp_path / "proposals.db"))
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(CatalogSnapshot(source="ECOMM_APP_API_STAGE", payload=capture()))
        db.commit()
        EcommApiProductWorkspace(db).save("101", payload(), "DRAFT", 0)
        for key, name, sku, title in [
            ("ECOMM_API:101", "Magnesio 30 caps", "2500", "Vieja propuesta"),
            ("ECOMM_API:101", "Magnesio 30 caps", "2500", "Nueva propuesta"),
            ("ECOMM_API:102", "Pack x2 Magnesio 60 caps", "2500400", "Segunda ficha"),
            ("TN:legacy", "Fuente externa", "2500", "No mostrar"),
        ]:
            db.add(KikiAiEditorialDraft(
                product_key=key, source_hash="a"*64,
                original_name=name, model="test-model", title=title,
                description="Sin aprobación comercial", questions=[],
                source_facts=[{"field": "sku", "value": sku}], history=[],
                review_status="PENDING_REVIEW", review_note="",
            ))
        db.commit()
    return engine


def test_inbox_one_latest_per_api_variant_and_saved_edit_is_separate(tmp_path):
    engine = build_db(tmp_path)
    with Session(engine) as db:
        result = list_ecomm_ai_proposals(db)
        assert result["total"] == 2
        assert result["summary"] == {
            "products_with_ai_proposals": 2,
            "products_with_saved_edits": 1,
            "products_without_saved_edits": 1,
        }
        assert [item["ecomm_id"] for item in result["items"]] == ["102", "101"]
        assert result["items"][0]["has_saved_product_edit"] is False
        assert result["items"][1]["has_saved_product_edit"] is True
        assert result["items"][1]["product_edit_status"] == "DRAFT"
        assert result["items"][0]["source_freshness"] == "VERIFY_ON_OPEN"
        assert result["external_writes_enabled"] is False
        assert db.scalars(select(EcommApiProductEdit)).one().ecomm_id == "101"


def test_inbox_search_filters_and_pagination(tmp_path):
    engine = build_db(tmp_path)
    with Session(engine) as db:
        assert list_ecomm_ai_proposals(db, query="2500400")["total"] == 1
        assert list_ecomm_ai_proposals(db, query="MAGNESIO")["total"] == 2
        assert list_ecomm_ai_proposals(db, query="Nueva propuesta")["items"][0]["ecomm_id"] == "101"
        assert list_ecomm_ai_proposals(db, saved_filter="without_edit")["items"][0]["ecomm_id"] == "102"
        assert list_ecomm_ai_proposals(db, saved_filter="with_edit")["items"][0]["ecomm_id"] == "101"
        assert list_ecomm_ai_proposals(db, page=1, limit=1)["items"][0]["ecomm_id"] == "102"
        assert list_ecomm_ai_proposals(db, page=2, limit=1)["items"][0]["ecomm_id"] == "101"
        assert list_ecomm_ai_proposals(db, page=3, limit=1)["items"] == []


def test_inbox_invalid_filter_rejected_without_changes(tmp_path):
    engine = build_db(tmp_path)
    with Session(engine) as db:
        with pytest.raises(ValueError, match="Filtro"):
            list_ecomm_ai_proposals(db, saved_filter="approve_all")
        with pytest.raises(ValueError, match="paginación"):
            list_ecomm_ai_proposals(db, page=0)
        assert db.scalars(select(KikiAiEditorialDraft)).all().__len__() == 4
        assert db.scalars(select(EcommApiProductEdit)).all().__len__() == 1
