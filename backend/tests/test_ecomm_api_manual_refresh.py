"""Regression checks for the operator-triggered Ecomm API refresh."""
from datetime import timedelta
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.models import Base, CatalogSnapshot, EcommApiProductEdit
from app.integrations.ecomm_app.catalog_stage import STAGE_SOURCE
from app.services import ecomm_api_refresh_job_service as jobs
from test_ecomm_app_catalog_stage import StubClient
from test_ecomm_app_scheduled_refresh import old_capture


@pytest.fixture
def sessions():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        db.add(CatalogSnapshot(source=STAGE_SOURCE, payload=old_capture()))
        db.add(EcommApiProductEdit(
            ecomm_id="SAVED", source_sku="OLD", source_snapshot={},
            fields={"title": "Guardado antes de actualizar"},
            status="DRAFT", version=1, history=[{"version": 1}],
        ))
        db.commit()
    yield factory
    engine.dispose()


def test_manual_start_is_persistent_and_rejects_simultaneous_scheduled_start(sessions):
    with sessions() as db:
        owner = jobs.start_job(db, "MANUAL")
        assert jobs.job_status(db)["status"] == "RUNNING"
        assert "owner" not in jobs.job_status(db)
        with pytest.raises(HTTPException) as error:
            jobs.start_job(db, "SCHEDULED")
        assert error.value.status_code == 409
        with pytest.raises(HTTPException):
            jobs.require_active(db, origin="SCHEDULED")
        assert jobs.require_active(db, owner=owner, origin="MANUAL") == owner


def test_manual_worker_promotes_complete_capture_and_preserves_saved_edits(sessions):
    class Settings:
        ecomm_app_api_token = "demo-read-only-token"
    with sessions() as db:
        owner = jobs.start_job(db, "MANUAL")
    with (
        patch.object(jobs, "SessionLocal", sessions),
        patch.object(jobs, "EcommAppInventoryClient",
                     return_value=StubClient(total=201)),
        patch.object(jobs, "get_settings", return_value=Settings()),
    ):
        jobs.run_manual_refresh(owner)
    with sessions() as db:
        run = jobs.job_status(db)
        assert run["status"] == "SUCCESS"
        assert run["pages_saved"] == 5
        assert run["expected_pages"] == 5
        assert run["variants"] == 201
        stage = db.scalar(select(CatalogSnapshot).where(
            CatalogSnapshot.source == STAGE_SOURCE
        ))
        assert len(stage.payload) == 5
        edit = db.scalar(select(EcommApiProductEdit))
        assert edit.fields["title"] == "Guardado antes de actualizar"
        assert edit.history == [{"version": 1}]


def test_manual_worker_error_keeps_live_capture_and_all_edits(sessions):
    class Settings:
        ecomm_app_api_token = "demo-read-only-token"
    with sessions() as db:
        owner = jobs.start_job(db, "MANUAL")
    with (
        patch.object(jobs, "SessionLocal", sessions),
        patch.object(jobs, "EcommAppInventoryClient",
                     return_value=StubClient(total=201, failure=4)),
        patch.object(jobs, "get_settings", return_value=Settings()),
    ):
        jobs.run_manual_refresh(owner)
    with sessions() as db:
        assert jobs.job_status(db)["status"] == "FAILED"
        live = db.scalar(select(CatalogSnapshot).where(
            CatalogSnapshot.source == STAGE_SOURCE
        ))
        assert live.payload == old_capture()
        edit = db.scalar(select(EcommApiProductEdit))
        assert edit.fields["title"] == "Guardado antes de actualizar"


def test_stale_job_can_be_restarted_without_accepting_old_worker(sessions):
    with sessions() as db:
        old_owner = jobs.start_job(db, "MANUAL")
        record = db.scalar(select(CatalogSnapshot).where(
            CatalogSnapshot.source == jobs.JOB_SOURCE
        ))
        payload = dict(record.payload[0])
        payload["heartbeat_at"] = (jobs.utcnow() - timedelta(hours=1)).isoformat()
        record.payload = [payload]
        db.commit()
        assert jobs.job_status(db)["status"] == "INTERRUPTED"
        new_owner = jobs.start_job(db, "SCHEDULED")
        assert new_owner != old_owner
        with pytest.raises(HTTPException):
            jobs.require_active(db, owner=old_owner)
