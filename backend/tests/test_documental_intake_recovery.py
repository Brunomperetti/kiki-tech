"""Expired documentary leases recover locally without downloads or approvals.

All products, URLs, sessions and documents below are synthetic. SQLite is
discarded per test; production flags/schema are not modified.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.database.models import CatalogSnapshot, EcommApiProductEdit
from app.services.documental.source_intake_queue import SourceIntakeQueue
from app.services.documental.source_intake_storage import SourceIntakeJob
from app.services.documental.storage import Document, digest
from test_documental_complete_draft_flow import IDENT
from test_documental_resumable_source_intake import (
    fixture, prepare_job, fake_importer, selected,
)
from test_documental_manufacturer_batch_intake import FIRST

INSTANT = datetime(2026, 11, 22, 15, 0, tzinfo=timezone.utc)


def interrupt(db, ident, *, deadline=INSTANT, document=False):
    job = db.get(SourceIntakeJob, ident)
    rows = deepcopy(job.items)
    rows[0].update(
        state="RUNNING", attempts=1, claim_token="SYNTHETIC-LEASE-TOKEN",
        claim_until=deadline.isoformat(), next_action="WAIT",
    )
    job.items = rows
    job.revision += 1
    if document:
        body = {
            "associated_ecomm_id": IDENT,
            "source": {"reference_url": FIRST, "review_state": "PENDING"},
            "synthetic": True,
        }
        db.add(Document(
            id="local-" + "9" * 32, version=1, body=body,
            digest=digest(body), history=[],
        ))
    db.commit()
    return job.revision


def coverage_reconciles(report):
    coverage = report["coverage"]
    assert sum(report["counts"].values()) == report["total"]
    assert coverage["total_variants"] == report["total"]
    assert (coverage["documents_recorded"] + coverage["without_recorded_document"]
            + coverage["cancelled"]) == report["total"]
    assert coverage["facts_approved_by_operation"] == 0
    assert coverage["commercial_fields_saved"] == 0


@pytest.mark.parametrize("has_document", [False, True])
def test_expired_lease_recovery_is_local_and_does_not_process_next_item(
    tmp_path, monkeypatch, has_document,
):
    import app.services.documental.source_intake_queue as module
    monkeypatch.setattr(module, "now", lambda: INSTANT)
    engine = fixture(tmp_path)
    with Session(engine) as db:
        queue, first = prepare_job(db)
        revision = interrupt(db, first["id"], document=has_document)
        before_documents = [(d.id, d.digest, deepcopy(d.body)) for d in db.scalars(select(Document))]
        before_capture = deepcopy(db.scalar(select(CatalogSnapshot).where(
            CatalogSnapshot.source == "ECOMM_APP_API_STAGE"
        )).payload)
        preview = queue.detail(first["id"])
        assert preview["recoverable_items"] == 1
        assert preview["items"][0]["recoverable"] is True
        assert "claim_token" not in preview["items"][0]
        coverage_reconciles(preview)

    # A new operator/process can recover after a browser/server restart.
    with Session(engine) as db:
        queue = SourceIntakeQueue(db, SimpleNamespace(id=2), "")
        recovered = queue.recover(first["id"], revision)
        assert recovered["revision"] == revision + 1
        assert recovered["items"][0]["state"] == ("IMPORTED" if has_document else "BLOCKED")
        assert recovered["items"][0]["attempts"] == 1
        assert recovered["items"][1]["state"] == "PENDING"
        assert recovered["items"][1]["attempts"] == 0
        assert recovered["recoverable_items"] == 0
        assert db.get(SourceIntakeJob, first["id"]).history[-1]["action"] == "RECOVERED_OFFLINE"
        assert [(d.id, d.digest, d.body) for d in db.scalars(select(Document))] == before_documents
        assert db.scalar(select(CatalogSnapshot).where(
            CatalogSnapshot.source == "ECOMM_APP_API_STAGE"
        )).payload == before_capture
        assert not db.scalars(select(EcommApiProductEdit)).all()
        coverage_reconciles(recovered)
        # The old worker can no longer complete, and concurrent CAS loses.
        with pytest.raises(ValueError, match="dueño"):
            queue._finish(first["id"], IDENT, "SYNTHETIC-LEASE-TOKEN", None, "late response")
        db.rollback()
        with pytest.raises(ValueError, match="cambió"):
            queue.recover(first["id"], revision)
        db.rollback()
        with pytest.raises(ValueError, match="No hay pasos"):
            queue.recover(first["id"], recovered["revision"])


@pytest.mark.parametrize("until", [
    (INSTANT + timedelta(microseconds=1)).isoformat(),
    "invalid-date", "", "2026-11-22T14:59:00",
])
def test_unexpired_or_invalid_lease_cannot_be_preempted(tmp_path, monkeypatch, until):
    import app.services.documental.source_intake_queue as module
    monkeypatch.setattr(module, "now", lambda: INSTANT)
    engine = fixture(tmp_path)
    with Session(engine) as db:
        queue, first = prepare_job(db)
        revision = interrupt(db, first["id"])
        job = db.get(SourceIntakeJob, first["id"])
        rows = deepcopy(job.items)
        rows[0]["claim_until"] = until
        job.items = rows
        db.commit()
        assert queue.detail(first["id"])["recoverable_items"] == 0
        with pytest.raises(ValueError, match="No hay pasos"):
            queue.recover(first["id"], revision)
        db.rollback()
        assert queue.detail(first["id"])["revision"] == revision
        assert queue.detail(first["id"])["items"][0]["state"] == "RUNNING"


def test_retry_limit_and_cancelled_coverage_preserve_completed_documents(tmp_path):
    engine = fixture(tmp_path)
    with Session(engine) as db:
        queue, first = prepare_job(db)
        moved = queue.step(first["id"], first["revision"], importer=fake_importer)
        cancelled = queue.cancel(first["id"], moved["revision"])
        coverage_reconciles(cancelled)
        assert cancelled["coverage"]["documents_recorded"] == 1
        assert cancelled["coverage"]["cancelled"] == 1
        assert cancelled["recoverable_items"] == 0
        with pytest.raises(ValueError, match="cancelado"):
            queue.recover(first["id"], cancelled["revision"])
        db.rollback()

        queue, first = prepare_job(db, items=[selected()[1]])
        def rejected(*_a, **_k):
            raise TimeoutError("Synthetic source temporarily unavailable")
        for attempt in range(1, 4):
            state = queue.step(first["id"], first["revision"], importer=rejected)
            assert state["items"][0]["attempts"] == attempt
            assert state["max_attempts"] == 3
            if attempt < 3:
                first = queue.retry(first["id"], state["revision"], "9912345")
        assert state["items"][0]["retry_available"] is False
        with pytest.raises(ValueError, match="reintento"):
            queue.retry(first["id"], state["revision"], "9912345")


def test_twenty_variant_coverage_reconciles_and_rejects_duplicate_or_oversized_batch(tmp_path):
    from uuid import uuid4
    engine = fixture(tmp_path)
    with Session(engine) as db:
        snapshot = db.scalar(select(CatalogSnapshot).where(
            CatalogSnapshot.source == "ECOMM_APP_API_STAGE"
        ))
        pages = deepcopy(snapshot.payload)
        parents = []
        entries = []
        for offset in range(20):
            ident = str(9800000 + offset)
            parents.append({
                "code": "SYNTHETIC-PARENT-" + ident,
                "description": "Fictional test seeds 250 g",
                "is_combo": False,
                "variants": [{"id": int(ident), "sku": "SYNTHETIC-" + ident,
                              "variant_description": "250 g", "is_combo": False,
                              "total_stock": 0}],
            })
            entries.append({
                "ecomm_id": ident,
                "url": f"https://naturalseed.com.ar/producto/synthetic-{ident}/",
                "provenance_note": "Synthetic offline source selection, not an authentic product.",
            })
        pages[0]["items"] = parents
        pages[0]["total"] = len(parents)
        snapshot.payload = pages
        db.commit()
        queue = SourceIntakeQueue(db, SimpleNamespace(id=1), "naturalseed.com.ar")
        report = queue.create_explicit(str(uuid4()), entries)
        assert report["total"] == 20
        assert report["coverage"]["without_recorded_document"] == 20
        coverage_reconciles(report)
        original_revision = report["revision"]
        with pytest.raises(ValueError, match="1 y 20"):
            queue.create_explicit(str(uuid4()), entries + [entries[0]])
        with pytest.raises(ValueError, match="repetido"):
            queue.create_explicit(str(uuid4()), [entries[0], entries[0]])
        assert queue.detail(report["id"])["revision"] == original_revision
        cancelled = queue.cancel(report["id"], original_revision)
        assert cancelled["coverage"]["cancelled"] == 20
        assert cancelled["coverage"]["documents_recorded"] == 0
        coverage_reconciles(cancelled)


def test_recovery_route_auth_csrf_offline_flags_and_replay(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.routes import documental_workspace as routes
    from app.core import security
    from app.core.config import Settings
    from app.database.session import get_db

    import app.services.documental.source_intake_queue as module
    monkeypatch.setattr(module, "now", lambda: INSTANT)
    config = Settings(
        _env_file=None, app_session_secret="SYNTHETIC-SESSION-SECRET-NOT-PRODUCTION",
        kiki_document_workspace_enabled=True,
        kiki_document_resumable_intake_enabled=True,
        kiki_document_batch_source_import_enabled=False,
        kiki_document_sitemap_discovery_enabled=False,
        kiki_document_explicit_url_intake_enabled=False,
        kiki_document_parser_kernel_required=False,
        kiki_document_source_fetch_hosts="",
    )
    monkeypatch.setattr(routes, "get_settings", lambda: config)
    monkeypatch.setattr(security, "get_settings", lambda: config)
    monkeypatch.setattr(routes, "reader_available", lambda: pytest.fail("No parser probe for recovery"))
    engine = fixture(tmp_path)
    with Session(engine) as db:
        _, first = prepare_job(db)
        revision = interrupt(db, first["id"])
        token, session = security.create_session(db)
        csrf = security.csrf_token(session.token_hash)
    app = FastAPI()
    app.include_router(routes.router)
    def test_db():
        with Session(engine) as db:
            yield db
    app.dependency_overrides[get_db] = test_db
    path = f"/api/ecomm-app/workspace/sources/intake-jobs/{first['id']}"
    body = {"expected_revision": revision, "confirm": True}
    with TestClient(app) as client:
        assert client.post(path + "/recover", json=body).status_code == 401
        client.cookies.set(security.SESSION_COOKIE, token)
        assert client.post(path + "/recover", json=body).status_code == 403
        assert client.get(path).status_code == 200
        assert client.get(path.rsplit("/", 1)[0]).status_code == 200
        headers = {"X-CSRF-Token": csrf}
        assert client.post(path + "/step", json=body, headers=headers).status_code == 403
        restored = client.post(path + "/recover", json=body, headers=headers)
        assert restored.status_code == 200
        assert restored.json()["counts"]["BLOCKED"] == 1
        assert client.post(path + "/recover", json=body, headers=headers).status_code == 409
        config.kiki_document_resumable_intake_enabled = False
        assert client.get(path).status_code == 403
        assert client.post(path + "/recover", json=body, headers=headers).status_code == 403


@pytest.mark.parametrize("workspace,queue_flag,schema", [
    (True, True, True), (False, True, True), (True, False, True),
    (True, True, False),
])
def test_state_capability_independent_from_downloader(
    tmp_path, monkeypatch, workspace, queue_flag, schema,
):
    from app.api.routes import v2
    from app.core.config import Settings
    from app.services.documental.storage import Document
    engine = fixture(tmp_path)
    config = Settings(
        _env_file=None, kiki_v2_enabled=True,
        kiki_document_workspace_enabled=workspace,
        kiki_document_resumable_intake_enabled=queue_flag,
        kiki_document_source_fetch_hosts="",
    )
    monkeypatch.setattr(v2, "get_settings", lambda: config)
    with Session(engine) as db:
        # Match the existing explicit migration's local document lookup index.
        db.execute(text(f"CREATE INDEX IF NOT EXISTS kiki_evidence_documents_variant ON {Document.__tablename__} (id)"))
        db.commit()
        if not schema:
            SourceIntakeJob.__table__.drop(engine)
        report = v2.capabilities(db, reader_probe=False)
        assert report["document_intake_state"] is (workspace and queue_flag and schema)
        assert report["document_resumable_intake"] is False
        assert report["document_batch_source_import"] is False
        assert report["document_exact_url_manifest"] is False
