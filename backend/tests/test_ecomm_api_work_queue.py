"""API-only queue triage, stable IDs, no provider writes, and meaningful pagination."""
from copy import deepcopy

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database.models import Base, CatalogSnapshot, EcommApiProductEdit
from app.services.ecomm_api_product_workspace_service import EcommApiProductWorkspace
from app.services.ecomm_api_work_queue_service import build_queue
from test_ecomm_api_product_workspace import capture, payload


def db_fixture(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    engine = create_engine("sqlite:///" + str(tmp_path / "queue.db"))
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(CatalogSnapshot(source="ECOMM_APP_API_STAGE", payload=capture()))
        db.add(CatalogSnapshot(source="ECOMM_APP", payload=[
            {"ecomm_id": "999", "sku": "invalid", "brand": "Excel brand"}
        ]))
        db.commit()
    return engine


def test_untouched_editorial_queue_sorted_and_read_only(tmp_path):
    engine = db_fixture(tmp_path)
    with Session(engine) as db:
        view = build_queue(db)
        assert view["source"] == "ECOMM_APP_API_STAGE"
        assert view["mode"] == "KIKI_INTERNAL_READ_ONLY_TRIAGE"
        assert view["summary"]["total"] == 2
        assert view["summary"]["untouched"] == 2
        assert view["summary"]["missing_brand"] == 2
        assert view["summary"]["missing_description"] == 2
        assert view["summary"]["missing_gtin"] == 2
        assert view["summary"]["pack"] == 1
        assert view["items"][0]["ecomm_id"] == "102"  # pack priority before simple
        assert view["items"][0]["is_combo"]
        assert view["external_writes_enabled"] is False
        assert not db.scalars(select(EcommApiProductEdit)).all()


def test_saved_draft_and_ready_status_filters_preserve_origins(tmp_path):
    engine = db_fixture(tmp_path)
    with Session(engine) as db:
        workspace = EcommApiProductWorkspace(db)
        workspace.save("102", payload(), "DRAFT", 0)
        workspace.save("101", payload(title="Simple confirmed"), "READY_FOR_REVIEW", 0)
        view = build_queue(db)
        assert view["summary"]["draft"] == 1
        assert view["summary"]["ready"] == 1
        assert view["summary"]["missing_brand"] == 0
        assert view["summary"]["missing_title"] == 0
        assert view["summary"]["missing_gtin"] == 2  # no invented GTIN
        assert view["items"][0]["ecomm_id"] == "102"
        assert build_queue(db, filter_name="draft")["items"][0]["ecomm_id"] == "102"
        assert build_queue(db, filter_name="ready")["items"][0]["ecomm_id"] == "101"
        assert build_queue(db, query="2500400")["total"] == 1
        assert build_queue(db, query="Vitamin")["total"] == 2
        assert build_queue(db, page=1, limit=1)["items"][0]["ecomm_id"] == "102"
        assert build_queue(db, page=2, limit=1)["items"][0]["ecomm_id"] == "101"
        assert db.scalar(select(CatalogSnapshot).where(
            CatalogSnapshot.source == "ECOMM_APP_API_STAGE"
        )).payload == capture()


def test_ambiguous_sku_and_changed_identity_get_priority(tmp_path):
    engine = db_fixture(tmp_path)
    with Session(engine) as db:
        workspace = EcommApiProductWorkspace(db)
        workspace.save("102", payload(), "DRAFT", 0)
        snapshot = db.scalar(select(CatalogSnapshot).where(
            CatalogSnapshot.source == "ECOMM_APP_API_STAGE"
        ))
        changed = deepcopy(snapshot.payload)
        changed[0]["items"][1]["variants"][0]["sku"] = "2500"
        snapshot.payload = changed
        db.commit()
        view = build_queue(db, filter_name="identity")
        assert view["total"] == 2
        assert all(item["priority"] == 0 for item in view["items"])
        assert all(item["identity_issue"] for item in view["items"])
        assert view["summary"]["identity"] == 2


def test_missing_or_incomplete_api_stage_blocks_queue(tmp_path):
    engine = db_fixture(tmp_path)
    with Session(engine) as db:
        stage = db.scalar(select(CatalogSnapshot).where(
            CatalogSnapshot.source == "ECOMM_APP_API_STAGE"
        ))
        db.delete(stage)
        db.commit()
        with pytest.raises(ValueError, match="incompleta"):
            build_queue(db)

    engine2 = db_fixture(tmp_path / "next")
    with Session(engine2) as db:
        stage = db.scalar(select(CatalogSnapshot).where(
            CatalogSnapshot.source == "ECOMM_APP_API_STAGE"
        ))
        wrong = deepcopy(stage.payload)
        wrong[0]["total_pages"] = 2
        stage.payload = wrong
        db.commit()
        with pytest.raises(ValueError, match="incompleta"):
            build_queue(db)


def test_unrecognized_filter_and_beyond_page_are_safe(tmp_path):
    engine = db_fixture(tmp_path)
    with Session(engine) as db:
        with pytest.raises(ValueError, match="Filtro"):
            build_queue(db, filter_name="export-ML")
        with pytest.raises(ValueError, match="paginación"):
            build_queue(db, page=0)
        final = build_queue(db, page=10, limit=1)
        assert final["total"] == 2 and final["items"] == []
