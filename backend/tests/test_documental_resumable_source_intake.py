"""Offline verification of resumable, operator-stepped manufacturer research.

SQLite is only a disposable test harness for the new ORM coordination state;
production requires the explicit PostgreSQL migration. No supplier traffic,
provider writes, paid AI, timer-driven execution or automatic approvals.
"""
from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import CatalogSnapshot
from app.services.documental.source_intake_storage import (
    SourceIntakeBase, SourceIntakeJob,
)
from app.services.documental.source_intake_queue import SourceIntakeQueue
from app.services.documental.storage import Document, digest
from test_documental_manufacturer_batch_intake import (
    FIRST, SECOND, SITEMAP, HASH, HOST, candidate, prepare_two, preview,
    fake_source, parse_source,
)
from test_documental_complete_draft_flow import IDENT


def fixture(tmp_path):
    engine = prepare_two(tmp_path)
    SourceIntakeBase.metadata.create_all(engine)
    return engine


def selected():
    return [
        {"ecomm_id": IDENT, "url": FIRST},
        {"ecomm_id": "9912345", "url": SECOND},
    ]


def prepare_job(db, *, key=None, items=None):
    entries = items or selected()
    queue = SourceIntakeQueue(db, SimpleNamespace(id=1), HOST)
    calls = []

    def discovery(_db, ids, sitemap, hosts):
        calls.append(tuple(ids))
        assert sitemap == SITEMAP and hosts == HOST
        links = [next(x["url"] for x in entries if x["ecomm_id"] == ident)
                 for ident in ids]
        return preview(*(
            candidate(ident, url) for ident, url in zip(ids, links)
        ))

    report = queue.create(
        key or str(uuid4()), SITEMAP, HASH, entries, previewer=discovery,
    )
    assert calls == [tuple(x["ecomm_id"] for x in entries)]
    assert report["mode"] == "MANUAL_RESUMABLE_SOURCE_INTAKE"
    assert report["external_writes_enabled"] is False
    assert report["claims_approved"] == 0
    return queue, report


def fake_importer(db, user, *, sitemap_url, sitemap_sha256, items,
                  configured_hosts):
    assert sitemap_url == SITEMAP and sitemap_sha256 == HASH
    assert configured_hosts == HOST and len(items) == 1
    from app.services.documental.manufacturer_batch_intake import capture_selected
    return capture_selected(
        db, user, sitemap_url=sitemap_url, sitemap_sha256=sitemap_sha256,
        items=items, configured_hosts=configured_hosts,
        previewer=lambda *_a: preview(*(candidate(row["ecomm_id"], row["url"]) for row in items)),
        downloader=fake_source, parser=parse_source,
    )


def test_create_and_resume_in_new_session_without_browser_loop(tmp_path):
    engine = fixture(tmp_path)
    with Session(engine) as db:
        queue, report = prepare_job(db)
        assert report["total"] == 2 and report["revision"] == 1
        assert queue.listing()["items"][0]["id"] == report["id"]
        first = queue.step(report["id"], report["revision"], importer=fake_importer)
        assert first["counts"]["IMPORTED"] == 1
        assert first["counts"]["PENDING"] == 1
        assert first["manual_steps_only"] is True
        # No second source is run in the same request.
    with Session(engine) as db:
        queue = SourceIntakeQueue(db, SimpleNamespace(id=2), HOST)
        state = queue.detail(report["id"])
        assert state["counts"]["IMPORTED"] == 1
        final = queue.step(report["id"], state["revision"], importer=fake_importer)
        assert final["counts"]["IMPORTED"] == 2
        assert final["state"] == "COMPLETED"
        assert all(item["document_id"] for item in final["items"])
        archived = db.scalars(select(Document).where(
            Document.body["source"]["reference_url"].as_string() == SECOND
        )).all()
        assert len(archived) == 1
        assert archived[0].body["source"]["review_state"] == "PENDING"


def test_blocked_source_remains_retryable_without_resetting_other_variants(tmp_path):
    engine = fixture(tmp_path)
    with Session(engine) as db:
        queue, report = prepare_job(db)
        def fail(*args, **kwargs):
            raise TimeoutError("Synthetic manufacturer temporarily unavailable")
        blocked = queue.step(report["id"], report["revision"], importer=fail)
        assert blocked["counts"]["BLOCKED"] == 1
        assert blocked["counts"]["PENDING"] == 1
        assert blocked["items"][0]["processing"]["error_code"] == "SOURCE_UNAVAILABLE"
        # Other products continue while the first is blocked.
        next_step = queue.step(report["id"], blocked["revision"], importer=fake_importer)
        assert next_step["counts"]["IMPORTED"] == 1
        again = queue.retry(report["id"], next_step["revision"], IDENT)
        assert again["items"][0]["state"] == "PENDING"
        completed = queue.step(report["id"], again["revision"], importer=fake_importer)
        assert completed["counts"]["IMPORTED"] == 2
        assert completed["items"][0]["attempts"] == 2
        assert completed["items"][1]["attempts"] == 1


def test_cas_and_idempotency_reject_duplicate_or_stale_requests(tmp_path):
    engine = fixture(tmp_path)
    with Session(engine) as db:
        key = str(uuid4())
        queue, first = prepare_job(db, key=key)
        repeated = queue.create(
            key, SITEMAP, HASH, selected(),
            previewer=lambda *_: pytest.fail("Already created: no second network"),
        )
        assert repeated["id"] == first["id"]
        with pytest.raises(ValueError, match="otro lote"):
            queue.create(
                key, SITEMAP, HASH,
                [{"ecomm_id": IDENT, "url": SECOND}],
                previewer=lambda *_: pytest.fail("No network"),
            )
        moved = queue.step(first["id"], first["revision"], importer=fake_importer)
        with pytest.raises(ValueError, match="cambió"):
            queue.step(first["id"], first["revision"], importer=fake_importer)
        assert queue.detail(first["id"])["revision"] == moved["revision"]


def test_existing_document_after_crash_recovers_without_refetch(tmp_path):
    engine = fixture(tmp_path)
    with Session(engine) as db:
        queue, report = prepare_job(db, items=[selected()[0]])
        job = db.get(SourceIntakeJob, report["id"])
        item = deepcopy(job.items[0])
        item.update({
            "state": "RUNNING", "claim_token": "lost-network-response",
            "claim_until": "2000-01-01T00:00:00+00:00",
            "attempts": 1,
        })
        job.items = [item]
        job.revision += 1
        doc_body = {
            "associated_ecomm_id": IDENT,
            "source": {"reference_url": FIRST, "review_state": "PENDING"},
        }
        db.add(Document(
            id="local-" + "e" * 32, version=1,
            body=doc_body, digest=digest(doc_body), history=[],
        ))
        db.commit()
        recovered = queue.step(
            report["id"], job.revision,
            importer=lambda *_a, **_k: pytest.fail("No repeated network GET"),
        )
        assert recovered["state"] == "COMPLETED"
        assert recovered["items"][0]["state"] == "IMPORTED"
        assert recovered["items"][0]["document_id"] == "local-" + "e" * 32


def test_changed_ecomm_identity_blocks_and_never_calls_external_server(tmp_path):
    engine = fixture(tmp_path)
    with Session(engine) as db:
        queue, report = prepare_job(db, items=[selected()[0]])
        stage = db.scalar(select(CatalogSnapshot).where(
            CatalogSnapshot.source == "ECOMM_APP_API_STAGE"
        ))
        payload = deepcopy(stage.payload)
        payload[0]["items"][0]["variants"][0]["sku"] = "CAMBIO-API"
        stage.payload = payload
        db.commit()
        result = queue.step(
            report["id"], report["revision"],
            importer=lambda *_a, **_k: pytest.fail("No external GET"),
        )
        assert result["state"] == "NEEDS_REVIEW"
        assert "Cambió la identidad" in result["items"][0]["error"]
        with pytest.raises(ValueError, match="Identidad Ecomm"):
            queue.retry(report["id"], result["revision"], IDENT)


def test_cancel_preserves_what_was_already_completed(tmp_path):
    engine = fixture(tmp_path)
    with Session(engine) as db:
        queue, report = prepare_job(db)
        changed = queue.step(report["id"], report["revision"], importer=fake_importer)
        cancelled = queue.cancel(report["id"], changed["revision"])
        assert cancelled["state"] == "CANCELLED"
        assert cancelled["counts"]["IMPORTED"] == 1
        assert cancelled["counts"]["CANCELLED"] == 1
        with pytest.raises(ValueError, match="cancelado"):
            queue.step(report["id"], cancelled["revision"], importer=fake_importer)


def test_migration_is_additive_and_never_runs_at_startup():
    from app.services.documental.source_intake_migration import UP
    assert len(UP) == 2
    assert all(statement.startswith(("CREATE TABLE", "CREATE INDEX")) for statement in UP)
    assert all("DROP " not in statement for statement in UP)
