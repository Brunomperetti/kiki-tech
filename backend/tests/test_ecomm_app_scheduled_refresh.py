"""Scheduled refresh must keep the last complete API catalog and all KIKI edits."""
from unittest.mock import patch
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database.models import Base, CatalogSnapshot, EcommApiProductEdit
from app.integrations.ecomm_app.catalog_stage import (
    EcommAppStageService, STAGE_SOURCE, REFRESH_SOURCE,
)
from app.integrations.ecomm_app.public_api import EcommAppApiError
from app.api.routes.ecomm_app import require_refresh_token
from fastapi import HTTPException
from test_ecomm_app_catalog_stage import StubClient


def old_capture():
    # The current copy remains complete and readable until the new one commits.
    return [{
        "version": 1, "page": 1, "total": 1, "total_pages": 1,
        "per_page": 50, "captured_at": "2026-10-23T12:00:00+00:00",
        "items": [{"code": "OLD", "description": "Original",
                   "variants": [{"id": "SAVED", "sku": "OLD",
                                 "total_stock": 1, "is_combo": False}]}],
    }]


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as sess:
        sess.add(CatalogSnapshot(source=STAGE_SOURCE, payload=old_capture()))
        sess.add(EcommApiProductEdit(
            ecomm_id="SAVED", source_sku="OLD", source_snapshot={},
            fields={"title": "Título revisado"}, status="DRAFT",
            version=1, history=[{"version": 1}],
        ))
        sess.commit()
        yield sess
    engine.dispose()


def snapshot(db, source):
    return db.scalar(select(CatalogSnapshot).where(CatalogSnapshot.source == source)).payload


def test_partial_refresh_never_replaces_latest_good_api_or_saved_edits(db):
    client = StubClient(total=201)
    refresh = EcommAppStageService(db, client, REFRESH_SOURCE)
    first = refresh.next_batch()
    assert first["pages_saved"] == 3
    assert not first["complete"]
    assert snapshot(db, STAGE_SOURCE) == old_capture()
    assert len(snapshot(db, REFRESH_SOURCE)) == 3
    edit = db.scalar(select(EcommApiProductEdit))
    assert edit.fields == {"title": "Título revisado"}
    assert edit.version == 1

    done = refresh.next_batch()
    assert done["complete"]
    assert len(snapshot(db, STAGE_SOURCE)) == 5
    assert snapshot(db, STAGE_SOURCE) == snapshot(db, REFRESH_SOURCE)
    edit = db.scalar(select(EcommApiProductEdit))
    assert edit.fields == {"title": "Título revisado"}
    assert edit.version == 1
    assert edit.history == [{"version": 1}]


def test_network_error_keeps_both_old_catalog_and_saved_draft(db):
    client = StubClient(total=201, failure=4)
    refresh = EcommAppStageService(db, client, REFRESH_SOURCE)
    refresh.next_batch()
    with pytest.raises(EcommAppApiError):
        refresh.next_batch()
    assert snapshot(db, STAGE_SOURCE) == old_capture()
    assert len(snapshot(db, REFRESH_SOURCE)) == 3
    assert db.scalar(select(EcommApiProductEdit)).fields["title"] == "Título revisado"


def test_bad_final_ids_do_not_get_promoted(db):
    class BadClient(StubClient):
        def _call(self, method, path, *, params=None, body=None):
            raw = super()._call(method, path, params=params, body=body)
            if params["page"] == 4:
                raw["items"][0]["variants"][0]["id"] = None
            return raw
    client = BadClient(total=201)
    refresh = EcommAppStageService(db, client, REFRESH_SOURCE)
    refresh.next_batch()
    with pytest.raises(EcommAppApiError) as error:
        refresh.next_batch()
    assert error.value.code == "CALIDAD_INVENTARIO"
    assert snapshot(db, STAGE_SOURCE) == old_capture()
    assert db.scalar(select(EcommApiProductEdit)).version == 1


def test_invalid_refresh_source_rejected(db):
    with pytest.raises(ValueError, match="Fuente"):
        EcommAppStageService(db, None, "ECOMM_APP")  # forbidden Excel


def test_scheduler_bearer_requires_a_server_secret():
    class Settings:
        kiki_refresh_token = "secret" * 8
    with patch("app.api.routes.ecomm_app.get_settings", return_value=Settings()):
        require_refresh_token("Bearer " + Settings.kiki_refresh_token)
        with pytest.raises(HTTPException) as error:
            require_refresh_token("Bearer incorrect")
        assert error.value.status_code == 403
    class Empty:
        kiki_refresh_token = ""
    with patch("app.api.routes.ecomm_app.get_settings", return_value=Empty()):
        with pytest.raises(HTTPException) as error:
            require_refresh_token("Bearer anything")
        assert error.value.status_code == 503
