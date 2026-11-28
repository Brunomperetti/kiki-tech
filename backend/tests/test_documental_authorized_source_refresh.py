"""Periodic same-URL checks, offline originals/doubles and durable CAS only."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from app.services.documental.explicit_url_intake import import_explicit_url
from app.services.documental.local_documents import LocalDocuments
from app.services.documental.contracts import Provenance
from app.services.documental.research import Research
from app.services.documental.storage import Document, Dossier, digest
from test_documental_explicit_url_intake import setup, kwargs, fake_downloader
from test_documental_complete_draft_flow import IDENT

USER = SimpleNamespace(id=1)


def old_source(db):
    def downloader(*args, **kw):
        raw, trace = fake_downloader(*args, **kw)
        trace["acquired_at"] = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
        return raw, trace
    result = import_explicit_url(db, USER, **kwargs(downloader=downloader))
    doc = db.get(Document, result["incorporated_document_id"])
    research = Research(db, USER)
    old_date = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
    with patch("app.services.documental.local_documents.now", return_value=old_date):
        LocalDocuments(db, USER).provenance(IDENT, doc.id, Provenance(
            expected_document_version=doc.version, decision="REVIEWED", reason="Revisé el original ficticio íntegro y su procedencia."))
    research.review_document_identity(IDENT, research.dossier(IDENT).version, doc.id, doc.version,
        "APPROVED", "Contrasté el nombre de esta etiqueta ficticia con esta presentación exacta.")
    research.extract(IDENT, research.dossier(IDENT).version, doc.id, doc.version)
    for fact in list(research.dossier(IDENT).facts):
        if not research.blockers(research.dossier(IDENT), fact):
            research.review(IDENT, research.dossier(IDENT).version, fact["id"], fact["version"],
                            "APPROVED", "Revisión humana explícita de esta cita ficticia.")
    db.commit()
    return doc


def receipt(doc):
    return {"document_id": doc.id, "document_version": doc.version, "document_digest": doc.digest,
            "document_sha256": doc.body["original"]["sha256"]}


def refresh(db, doc, **overrides):
    options = {"expected_version": db.get(Dossier, IDENT).version, "selection_mode": "AUTOMATED_SEARCH_CANDIDATE",
               "refresh_existing": True, "expected_refresh_receipt": receipt(doc), "refresh_request_key": str(uuid4())}
    options.update(overrides)
    return import_explicit_url(db, USER, **kwargs(**options))


def test_identical_bytes_leave_document_and_human_approvals_untouched_only_observation_recorded(tmp_path, monkeypatch):
    engine = setup(tmp_path, monkeypatch)
    with Session(engine) as db:
        doc = old_source(db)
        before = (doc.version, doc.digest, deepcopy(doc.body), deepcopy(doc.history), deepcopy(db.get(Dossier, IDENT).facts))
        result = refresh(db, doc)
        assert result["refresh_outcome"] == "UNCHANGED"
        assert (doc.version, doc.digest, doc.body, doc.history, db.get(Dossier, IDENT).facts) == before
        assert any(f["state"] == "APPROVED" for f in before[4])
        event = db.get(Dossier, IDENT).history[-1]
        assert event["action"] == "SOURCE_UNCHANGED_OBSERVED" and event["detail"]["human_review_performed"] is False
        assert result["refresh_receipt"]["prior"] == result["refresh_receipt"]["current"]
        def forbidden(*args, **kw):
            pytest.fail("A second daily observation must not fetch")
        with pytest.raises(ValueError, match="observación"):
            refresh(db, doc, downloader=forbidden)
    engine.dispose()


def test_changed_bytes_replace_same_document_keep_original_and_make_facts_stale_then_pending(tmp_path, monkeypatch):
    engine = setup(tmp_path, monkeypatch)
    with Session(engine) as db:
        doc = old_source(db)
        original_version, original_hash, original_raw = doc.version, doc.body["original"]["sha256"], doc.body["original_base64"]
        def changed(*args, **kw):
            raw, trace = fake_downloader(*args, **kw)
            raw = raw.replace(b"3 frutos secos", b"4 frutos secos")
            return raw, {**trace, "sha256": sha256(raw).hexdigest(), "size": len(raw)}
        result = refresh(db, doc, downloader=changed)
        assert result["incorporated_document_id"] == doc.id
        assert doc.version == original_version + 1
        assert result["refresh_outcome"] == "CHANGED_REQUIRES_HUMAN_REVIEW"
        assert doc.body["source"]["review_state"] == "PENDING" and doc.body["source"]["reviewer"] is None
        assert doc.history[-1]["body"]["original_base64"] == original_raw
        assert doc.history[-1]["body"]["original"]["sha256"] == original_hash
        research = Research(db, USER)
        assert all(f["state"] == "STALE" for f in research.dossier(IDENT).facts)
        research.extract(IDENT, research.dossier(IDENT).version, doc.id, doc.version)
        assert all(f["state"] == "PENDING" for f in research.dossier(IDENT).facts)
        assert all(f["document_version"] == doc.version for f in research.dossier(IDENT).facts)
    engine.dispose()


@pytest.mark.parametrize("change", ["pin", "limit", "revoked", "tamper", "default", "mode"])
def test_invalid_refresh_never_downloads_and_does_not_bypass_existing_guards(tmp_path, monkeypatch, change):
    engine = setup(tmp_path, monkeypatch)
    with Session(engine) as db:
        doc = old_source(db)
        pin = receipt(doc)
        body = deepcopy(doc.body)
        if change == "pin":
            pin["document_version"] += 1
        elif change == "limit":
            doc.version = body["version"] = 8
        elif change == "revoked":
            body["source"]["review_state"] = "REVOKED"
        elif change == "tamper":
            body["original_base64"] = "invalid"
        doc.body, doc.digest = body, digest(body)
        db.commit()
        def forbidden(*args, **kw):
            pytest.fail("Invalid refresh may not fetch")
        with pytest.raises(ValueError):
            import_explicit_url(db, USER, **kwargs(expected_version=db.get(Dossier, IDENT).version,
                downloader=forbidden, refresh_existing=change != "default", expected_refresh_receipt=pin,
                selection_mode="ONE_EXACT_OPERATOR_REVIEWED_URL" if change == "mode" else "AUTOMATED_SEARCH_CANDIDATE"))
    engine.dispose()


def test_concurrent_human_document_review_during_fetch_is_not_overwritten(tmp_path, monkeypatch):
    engine = setup(tmp_path, monkeypatch)
    with Session(engine) as db:
        doc = old_source(db)
        ident = doc.id
        def racing(*args, **kw):
            with Session(engine) as other:
                record = other.get(Document, ident)
                body = deepcopy(record.body)
                body["source"]["review_state"] = "REVOKED"
                record.body, record.digest = body, digest(body)
                record.version += 1
                other.commit()
            return fake_downloader(*args, **kw)
        with pytest.raises(ValueError):
            refresh(db, doc, downloader=racing)
        db.rollback()
        assert db.get(Document, ident).body["source"]["review_state"] == "REVOKED"
    engine.dispose()


@pytest.mark.parametrize("changed", [False, True])
def test_automation_refreshes_exact_stale_original_without_search_or_transferring_decisions(tmp_path, monkeypatch, changed):
    from app.services.documental.catalog_automation import CatalogAutomation
    from app.services.documental.source_intake_storage import SourceIntakeJob
    from test_documental_explicit_url_intake import HOST, fake_parser
    engine = setup(tmp_path, monkeypatch)
    SourceIntakeJob.__table__.create(engine)
    class Search:
        def search(self, *_args, **_kw):
            pytest.fail("A pinned stale original does not require another search")
    with Session(engine) as db:
        doc = old_source(db)
        ident, version, facts = doc.id, doc.version, deepcopy(db.get(Dossier, IDENT).facts)
        automation = CatalogAutomation(db, USER, Search(), HOST, network_enabled=True)
        job = automation.create(str(uuid4()), [IDENT])
        assert job["items"][0]["automation"]["phase"] == "REFRESH_REQUIRED"
        assert job["items"][0]["automation"]["refresh_receipt"] == receipt(doc)
        def downloader(*args, **kw):
            raw, trace = fake_downloader(*args, **kw)
            if changed:
                raw = raw.replace(b"3 frutos secos", b"4 frutos secos")
            return raw, {**trace, "sha256": sha256(raw).hexdigest(), "size": len(raw), "request_count": 2}
        def importer(db, user, **values):
            return import_explicit_url(db, user, **values, downloader=downloader, parser=fake_parser)
        result = automation.step(job["id"], job["revision"], explicit_importer=importer)
        row = result["items"][0]
        assert row["state"] == "IMPORTED", row
        assert row["document_id"] == ident
        assert row["processing"]["refresh_verified"] is True
        assert row["processing"]["http_requests_reported"] == 2
        assert db.get(Document, ident).version == version + int(changed)
        current_facts = db.get(Dossier, IDENT).facts
        if changed:
            # Old human name/presentation equivalence is bound to the previous
            # original hash; a new source requires an explicit new review.
            assert row["processing"]["error_code"] == "DOCUMENT_IDENTITY_MISMATCH"
            assert all(f["state"] == "STALE" for f in current_facts)
            assert not any(f["state"] == "APPROVED" for f in current_facts)
        else:
            assert current_facts == facts
        assert result["automatic_fact_approvals"] == 0
    engine.dispose()


@pytest.mark.parametrize("observed", [False, True])
def test_expired_refresh_lease_only_recovers_when_matching_backend_observation_exists(tmp_path, monkeypatch, observed):
    from app.services.documental.catalog_automation import CatalogAutomation
    from app.services.documental.source_intake_storage import SourceIntakeJob
    from app.services.documental.source_intake_pipeline import identity_pin
    from app.services.editorial_batches.context import sources
    from test_documental_explicit_url_intake import HOST
    engine = setup(tmp_path, monkeypatch)
    SourceIntakeJob.__table__.create(engine)
    with Session(engine) as db:
        doc = old_source(db)
        automation = CatalogAutomation(db, USER, SimpleNamespace(), HOST)
        job = automation.create(str(uuid4()), [IDENT])
        record = db.get(SourceIntakeJob, job["id"])
        rows = deepcopy(record.items)
        rows[0].update(state="RUNNING", attempts=1, claim_token=str(uuid4()),
                       claim_until=(datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat())
        rows[0]["processing"] = {"request_measurement_pending": True, "http_requests_reported": 0}
        record.items = rows
        db.commit()
        if observed:
            refresh(db, doc, refresh_request_key=rows[0]["claim_token"])
        assert identity_pin(sources(db)[IDENT]) == record.items[0]["expected_identity_v2"]
        result = automation.queue.recover(job["id"], job["revision"])
        row = result["items"][0]
        if observed:
            assert row["state"] == "IMPORTED" and row["document_id"] == doc.id
        else:
            assert row["state"] == "BLOCKED" and row["document_id"] is None
            assert row["processing"]["error_code"] == "REFRESH_PROOF_MISSING"
        assert row["claim_until"] is None
    engine.dispose()


@pytest.mark.parametrize("tamper", ["claim", "stored_proof", "variant"])
def test_refresh_receipt_cannot_be_forged_or_replayed_for_another_claim_or_variant(tmp_path, monkeypatch, tamper):
    from app.services.documental.explicit_url_intake import verified_refresh_result
    from test_documental_explicit_url_intake import URL
    engine = setup(tmp_path, monkeypatch)
    with Session(engine) as db:
        doc = old_source(db)
        key = str(uuid4())
        result = refresh(db, doc, refresh_request_key=key)
        proof = deepcopy(result["refresh_receipt"])
        item = {"ecomm_id": IDENT, "url": URL, "claim_token": key,
                "automation": {"refresh_receipt": proof["prior"]}}
        if tamper == "claim":
            item["claim_token"] = str(uuid4())
        elif tamper == "stored_proof":
            proof["observed_at"] = "2000-01-01T00:00:00+00:00"
        else:
            item["ecomm_id"] = "1234567"
        with pytest.raises(ValueError):
            verified_refresh_result(db, item, {"refresh_receipt": proof})
    engine.dispose()
