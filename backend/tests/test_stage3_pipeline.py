"""Actual queue/import/parser/extractor, with synthetic HTTP and disposable DB."""

from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4
import ssl

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.database.models import (
    CatalogSnapshot,
    EcommApiProductEdit,
    KikiAiEditorialDraft,
)
from app.services.documental.explicit_url_intake import import_explicit_url
from app.services.documental.source_fetch import fetch_html
from app.services.documental.source_intake_pipeline import receipt_for_document
from app.services.documental.source_intake_queue import SourceIntakeQueue, CLAIM_TTL
from app.services.documental.source_intake_storage import SourceIntakeJob
from app.services.documental.storage import Document, Dossier, digest
from test_documental_resumable_source_intake import fixture
from test_documental_source_fetch import Resolver, FakeTransport
from test_documental_manufacturer_batch_intake import FIRST, HOST, parse_source
from test_documental_complete_draft_flow import IDENT

USER = SimpleNamespace(id=1)


@pytest.fixture
def engine(tmp_path, monkeypatch):
    import app.services.documental.research as research

    monkeypatch.setattr(
        research, "get_settings", lambda: SimpleNamespace(kiki_admin_username="test")
    )
    result = fixture(tmp_path)
    with Session(result) as db:
        stage = db.scalar(
            select(CatalogSnapshot).where(
                CatalogSnapshot.source == "ECOMM_APP_API_STAGE"
            )
        )
        pages = deepcopy(stage.payload)
        pages[0]["items"][0]["description"] = "Mix Ensaladas y Sopas"
        pages[0]["items"][0]["variants"][0]["variant_description"] = "250 g"
        stage.payload = pages
        db.commit()
    yield result
    result.dispose()


def queue_job(db, *, key=None):
    queue = SourceIntakeQueue(db, USER, HOST)
    report = queue.create_explicit(
        key or str(uuid4()),
        [
            {
                "ecomm_id": IDENT,
                "url": FIRST,
                "provenance_note": "Synthetic exact-variant selection for offline tests only.",
            }
        ],
    )
    return queue, report


def importer(transport=None, *, after=None, parser=parse_source):
    transport = transport or FakeTransport()

    def execute(db, user, **kwargs):
        def download(url, hosts, *, max_bytes):
            return fetch_html(
                url,
                hosts,
                resolver=Resolver(),
                transport=transport,
                max_bytes=max_bytes,
            )

        report = import_explicit_url(
            db, user, **kwargs, downloader=download, parser=parser
        )
        if after:
            after()
        return report

    return execute, transport


def assert_unapproved(db, row):
    assert row["public_state"] == "REVIEW_REQUIRED"
    assert row["processing"]["phase"] == "EXTRACTED"
    assert row["processing"]["candidate_count"] == 3
    document = db.get(Document, row["document_id"])
    assert document.body["source"]["review_state"] == "PENDING"
    assert document.body["source"]["reviewer"] is None
    dossier = db.get(Dossier, IDENT)
    facts = [fact for fact in dossier.facts if fact["document_id"] == document.id]
    assert len(facts) == 3
    assert all(
        fact["state"] == "PENDING" and fact["reviewer"] is None for fact in facts
    )
    assert all(
        fact["quote"] in document.body["sections"][fact["location"]] for fact in facts
    )
    assert not db.scalars(select(EcommApiProductEdit)).all()
    assert not db.scalars(select(KikiAiEditorialDraft)).all()
    return deepcopy(facts)


def test_real_services_archive_and_extract_pending_without_openai_or_approval(engine):
    with Session(engine) as db:
        queue, job = queue_job(db)
        run, transport = importer()
        result = queue.step(job["id"], job["revision"], explicit_importer=run)
        facts = assert_unapproved(db, result["items"][0])
        metadata = result["items"][0]["processing"]
        assert result["pipeline_schema_version"] == "kiki-documental-pipeline-v1"
        assert metadata["candidate_ids"] == [fact["id"] for fact in facts]
        assert (
            metadata["document_sha256"]
            == db.get(Document, result["items"][0]["document_id"]).body["original"][
                "sha256"
            ]
        )
        assert metadata["http_requests_reported"] == 2
        assert metadata["download_attempts"] == 1
        assert len(transport.requests) == 2
        again = queue.complete_archived(job["id"], result["revision"], IDENT)
        assert assert_unapproved(db, again["items"][0]) == facts
        assert len(transport.requests) == 2


def test_lost_importer_response_recovers_original_without_another_http(engine):
    with Session(engine) as db:
        queue, job = queue_job(db)

        def lost():
            raise ConnectionError("SENSITIVE-TOKEN-NEVER-STORE-THIS")

        run, transport = importer(after=lost)
        result = queue.step(job["id"], job["revision"], explicit_importer=run)
        assert_unapproved(db, result["items"][0])
        assert "SENSITIVE" not in repr(result)
        assert len(transport.requests) == 2


def test_process_crash_then_offline_recovery_extracts_once(engine, monkeypatch):
    import app.services.documental.source_intake_queue as module

    with Session(engine) as db:
        queue, job = queue_job(db)
        run, transport = importer()

        def crash(*_a, **_k):
            raise SystemExit("Simulated worker shutdown after document commit")

        monkeypatch.setattr(queue, "_finish", crash)
        with pytest.raises(SystemExit):
            queue.step(job["id"], job["revision"], explicit_importer=run)
        persisted = db.get(SourceIntakeJob, job["id"])
        assert persisted.items[0]["state"] == "RUNNING"
        revision = persisted.revision
    instant = module.now() + CLAIM_TTL + timedelta(seconds=1)
    monkeypatch.setattr(module, "now", lambda: instant)
    with Session(engine) as db:
        queue = SourceIntakeQueue(db, SimpleNamespace(id=2), "")
        result = queue.recover(job["id"], revision)
        facts = assert_unapproved(db, result["items"][0])
        assert result["items"][0]["processing"]["http_requests_reported"] == 2
        assert len(transport.requests) == 2
        with pytest.raises(ValueError, match="cambió"):
            queue.recover(job["id"], revision)
        db.rollback()
        repeated = queue.complete_archived(job["id"], result["revision"], IDENT)
        assert assert_unapproved(db, repeated["items"][0]) == facts


@pytest.mark.parametrize(
    "field,value",
    [
        ("barcode", "036000291452"),
        ("parent_is_combo", True),
        ("parent_is_combo", 0),
        ("parent_code", "CHANGED-FAMILY"),
        ("legacy", None),
    ],
)
def test_changed_raw_identity_and_legacy_job_block_before_http(engine, field, value):
    with Session(engine) as db:
        queue, job = queue_job(db)
        if field == "legacy":
            persisted = db.get(SourceIntakeJob, job["id"])
            items = deepcopy(persisted.items)
            items[0].pop("identity_schema")
            persisted.items = items
        else:
            stage = db.scalar(
                select(CatalogSnapshot).where(
                    CatalogSnapshot.source == "ECOMM_APP_API_STAGE"
                )
            )
            pages = deepcopy(stage.payload)
            if field == "parent_is_combo":
                pages[0]["items"][0]["is_combo"] = value
            elif field == "parent_code":
                pages[0]["items"][0]["code"] = value
            else:
                pages[0]["items"][0]["variants"][0][field] = value
            stage.payload = pages
            # Python's False == 0 must not make this deliberate raw-type
            # corruption disappear in SQLAlchemy's JSON dirty comparison.
            flag_modified(stage, "payload")
        db.commit()
        result = queue.step(
            job["id"],
            job["revision"],
            explicit_importer=lambda *_a, **_k: pytest.fail("No manufacturer request"),
        )
        assert result["items"][0]["public_state"] == "BLOCKED"
        assert result["items"][0]["processing"]["error_code"] in {
            "API_IDENTITY_CHANGED",
            "LEGACY_IDENTITY_REVIEW_REQUIRED",
        }


@pytest.mark.parametrize("field", ["brand", "manufacturer"])
def test_explicit_brand_in_source_map_is_pinned_without_inventing_missing_api_fields(
    engine, monkeypatch, field
):
    import app.services.documental.source_intake_queue as module

    original = module.sources
    declared = {field: "SYNTHETIC-ORIGINAL"}

    def source_map(db):
        catalog = original(db)
        catalog[IDENT].update(declared)
        return catalog

    monkeypatch.setattr(module, "sources", source_map)
    with Session(engine) as db:
        queue, job = queue_job(db)
        declared[field] = "SYNTHETIC-CHANGED"
        result = queue.step(
            job["id"],
            job["revision"],
            explicit_importer=lambda *_a, **_k: pytest.fail(
                "Changed brand must not trigger a request"
            ),
        )
        assert result["items"][0]["processing"]["error_code"] == "API_IDENTITY_CHANGED"


@pytest.mark.parametrize("change", ["sku", "code", "pack"])
def test_shared_identifiers_or_pack_are_exceptions_not_assigned(engine, change):
    with Session(engine) as db:
        stage = db.scalar(
            select(CatalogSnapshot).where(
                CatalogSnapshot.source == "ECOMM_APP_API_STAGE"
            )
        )
        pages = deepcopy(stage.payload)
        first = pages[0]["items"][0]["variants"][0]
        second = pages[0]["items"][1]["variants"][0]
        if change == "sku":
            second["sku"] = first["sku"]
        elif change == "code":
            first["barcode"] = second["barcode"] = "036000291452"
        else:
            first["is_combo"] = True
        stage.payload = pages
        db.commit()
        if change == "pack":
            with pytest.raises(ValueError):
                queue_job(db)
        else:
            queue, job = queue_job(db)
            result = queue.step(
                job["id"],
                job["revision"],
                explicit_importer=lambda *_a, **_k: pytest.fail(
                    "No identity assignment"
                ),
            )
            assert result["items"][0]["public_state"] == "BLOCKED"
            assert result["items"][0]["processing"]["error_code"] == (
                "AMBIGUOUS_API_SKU" if change == "sku" else "AMBIGUOUS_API_CODE"
            )


def test_http_503_is_safe_failed_and_explicit_retry_spends_no_hidden_attempt(engine):
    with Session(engine) as db:
        queue, job = queue_job(db)
        transport = FakeTransport(page_status=503)
        run, _ = importer(transport)
        failed = queue.step(job["id"], job["revision"], explicit_importer=run)
        row = failed["items"][0]
        assert row["public_state"] == "FAILED"
        assert row["processing"]["error_code"] == "SOURCE_HTTP_503"
        assert row["processing"]["http_requests_reported"] == 2
        assert row["attempts"] == 1
        staged = queue.retry(job["id"], failed["revision"], IDENT)
        assert staged["items"][0]["attempts"] == 1
        assert len(transport.requests) == 2
        transport.page_status = 200
        result = queue.step(job["id"], staged["revision"], explicit_importer=run)
        assert_unapproved(db, result["items"][0])
        assert result["items"][0]["processing"]["http_requests_reported"] == 4
        assert len(transport.requests) == 4


@pytest.mark.parametrize(
    "error,code,retryable",
    [
        (
            ssl.SSLCertVerificationError("SENSITIVE-TLS-DETAIL"),
            "SOURCE_TLS_BLOCKED",
            False,
        ),
        (OSError("SENSITIVE-NETWORK-DETAIL"), "SOURCE_NETWORK", True),
    ],
)
def test_transport_failure_records_unknown_http_count_and_no_sensitive_exception(
    engine, error, code, retryable
):
    class RejectTransport:
        def get(self, *_a, **_k):
            raise error

    with Session(engine) as db:
        queue, job = queue_job(db)
        run, _ = importer(RejectTransport())
        result = queue.step(job["id"], job["revision"], explicit_importer=run)
        metadata = result["items"][0]["processing"]
        assert metadata["error_code"] == code
        assert metadata["retryable"] is retryable
        assert metadata["http_requests_reported"] is None
        assert metadata["download_attempts"] == 1
        assert "SENSITIVE" not in repr(result)


def test_pinned_document_metadata_change_blocks_local_reprocessing(engine):
    with Session(engine) as db:
        queue, job = queue_job(db)
        run, _ = importer()
        result = queue.step(job["id"], job["revision"], explicit_importer=run)
        old_facts = assert_unapproved(db, result["items"][0])
        doc = db.get(Document, result["items"][0]["document_id"])
        changed = deepcopy(doc.body)
        changed["source"]["review_state"] = "REVIEWED"
        doc.version += 1
        changed["version"] = doc.version
        doc.body, doc.digest = changed, digest(changed)
        db.commit()
        result = queue.complete_archived(job["id"], result["revision"], IDENT)
        assert result["items"][0]["processing"]["error_code"] == "DOCUMENT_CHANGED"
        assert db.get(Dossier, IDENT).facts == old_facts


def test_explicit_metadata_repin_reextracts_pending_then_new_manifest_reuses_exact_approvals(
    engine,
):
    from app.services.documental.local_documents import LocalDocuments
    from app.services.documental.contracts import Provenance

    with Session(engine) as db:
        queue, job = queue_job(db)
        run, transport = importer()
        result = queue.step(job["id"], job["revision"], explicit_importer=run)
        row = result["items"][0]
        service = LocalDocuments(db, USER)
        doc = db.get(Document, row["document_id"])
        service.provenance(
            IDENT,
            doc.id,
            Provenance(
                expected_document_version=doc.version,
                decision="REVIEWED",
                reason="Human inspection of the explicitly synthetic saved original.",
            ),
        )
        doc = db.get(Document, row["document_id"])
        assert queue.detail(job["id"])["items"][0]["complete_available"] is True
        before_facts = deepcopy(db.get(Dossier, IDENT).facts)
        with pytest.raises(ValueError, match="cambió desde"):
            queue.complete_archived(
                job["id"],
                result["revision"],
                IDENT,
                expected_document_version=doc.version - 1,
                expected_document_digest=doc.digest,
            )
        db.rollback()
        assert queue.detail(job["id"])["revision"] == result["revision"]
        assert db.get(Dossier, IDENT).facts == before_facts
        blocked = queue.complete_archived(job["id"], result["revision"], IDENT)
        assert blocked["items"][0]["processing"]["error_code"] == "DOCUMENT_CHANGED"
        completed = queue.complete_archived(
            job["id"],
            blocked["revision"],
            IDENT,
            expected_document_version=doc.version,
            expected_document_digest=doc.digest,
        )
        assert completed["items"][0]["processing"]["phase"] == "EXTRACTED"
        assert completed["items"][0]["error"] is None
        assert len(db.get(Dossier, IDENT).facts) == 3
        assert all(fact["state"] == "PENDING" for fact in db.get(Dossier, IDENT).facts)
        assert len(transport.requests) == 2
        for fact_id in [fact["id"] for fact in db.get(Dossier, IDENT).facts]:
            case = service.research.dossier(IDENT)
            fact = next(f for f in case.facts if f["id"] == fact_id)
            service.research.review(
                IDENT,
                case.version,
                fact_id,
                fact["version"],
                "APPROVED",
                "Human test decision on the individual synthetic citation.",
            )
        approved = deepcopy(db.get(Dossier, IDENT).facts)
        _, fresh = queue_job(db)
        cached = queue.step(
            fresh["id"],
            fresh["revision"],
            explicit_importer=lambda *_a, **_k: pytest.fail(
                "Known exact original must not be downloaded"
            ),
        )
        assert cached["items"][0]["processing"]["phase"] == "EXTRACTED"
        assert cached["items"][0]["processing"]["download_attempts"] == 0
        assert cached["items"][0]["processing"]["http_requests_reported"] == 0
        assert db.get(Dossier, IDENT).facts == approved
        assert len(transport.requests) == 2


def test_global_lease_prevents_another_job_from_fetching(engine):
    with Session(engine) as db:
        queue, first = queue_job(db)
        _, second = queue_job(db)
        persisted = db.get(SourceIntakeJob, first["id"])
        items = deepcopy(persisted.items)
        items[0]["state"] = "RUNNING"
        items[0]["claim_until"] = "2099-01-01T00:00:00+00:00"
        items[0]["claim_token"] = "synthetic-other-worker"
        persisted.items = items
        db.commit()
        with pytest.raises(ValueError, match="activo"):
            queue.step(
                second["id"],
                second["revision"],
                explicit_importer=lambda *_a, **_k: pytest.fail(
                    "Concurrency limit bypass"
                ),
            )


def test_forged_original_hash_blocks_extraction_without_leaking_error(engine):
    with Session(engine) as db:
        queue, job = queue_job(db)
        run, _ = importer()

        def corrupt(db, user, **kwargs):
            result = run(db, user, **kwargs)
            doc = db.get(Document, result["incorporated_document_id"])
            changed = deepcopy(doc.body)
            changed["original"]["sha256"] = "f" * 64
            doc.body, doc.digest = changed, digest(changed)
            db.commit()
            return result

        result = queue.step(job["id"], job["revision"], explicit_importer=corrupt)
        assert result["items"][0]["processing"]["error_code"] == "ORIGINAL_INTEGRITY"
        assert db.get(Dossier, IDENT).facts == []
        with pytest.raises(ValueError):
            receipt_for_document(
                db,
                db.get(SourceIntakeJob, job["id"]).items[0],
                result["items"][0]["document_id"],
            )


def test_normal_twenty_variant_retry_history_is_preserved_and_maintenance_is_bounded(
    engine,
):
    with Session(engine) as db:
        queue, report = queue_job(db)
        job = db.get(SourceIntakeJob, report["id"])
        events = [job.history[0]] + [
            {"action": action, "variant": variant, "attempt": attempt}
            for variant in range(20)
            for attempt in range(3)
            for action in (
                "CLAIMED",
                "DOWNLOAD_RESERVED",
                "ORIGINAL_PINNED",
                "DOCUMENT_PROCESSED",
                "RETRY_REQUESTED",
            )
        ]
        job.history = events
        db.commit()
        result = queue._update(job, deepcopy(job.items), "MANUAL_INSPECTION")
        assert job.history[: len(events)] == events
        assert result["history_events_dropped"] == 0
        job.history = [
            {"action": "SYNTHETIC_MAINTENANCE", "step": index} for index in range(512)
        ]
        db.commit()
        result = queue._update(job, deepcopy(job.items), "MANUAL_INSPECTION")
        assert len(job.history) == 512
        assert result["history_events_dropped"] == 2
        result = queue._update(job, deepcopy(job.items), "MANUAL_INSPECTION")
        assert len(job.history) == 512
        assert result["history_events_dropped"] == 3
