"""Local human source selection; actual durable intake schema, no real network."""
from copy import deepcopy
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import CatalogSnapshot, EcommApiProductEdit, KikiAiEditorialDraft
from app.services.documental.catalog_automation import CatalogAutomation
from app.services.documental.automation_source_selection import select_source
from app.services.documental.source_intake_storage import SourceIntakeJob
from app.services.documental.storage import Document, Dossier
from test_catalog_automation import engine as base_engine, Search
from test_stage3_pipeline import importer, USER
from test_documental_manufacturer_batch_intake import FIRST, SECOND, HOST
from test_documental_complete_draft_flow import IDENT

@pytest.fixture
def engine(tmp_path, monkeypatch):
    yield from base_engine.__wrapped__(tmp_path, monkeypatch)


REASON = "Seleccioné esta referencia candidata tras contrastar dominio e identidad; falta revisión de su original."


def ambiguous(db, *, enabled=True):
    search = Search([{"url": FIRST, "source_kind": "OFFICIAL_CANDIDATE"},
                     {"url": SECOND, "source_kind": "OFFICIAL_CANDIDATE"},
                     {"url": "https://comercio.invalid/arroz/", "source_kind": "SECONDARY"},
                     {"url": "https://unauthorized.invalid/producto/", "source_kind": "OFFICIAL_CANDIDATE"}])
    service = CatalogAutomation(db, USER, search, HOST, network_enabled=enabled)
    created = service.create(str(uuid4()), [IDENT])
    # Persist the same bounded shape as completed search. No external request.
    job = db.get(SourceIntakeJob, created["id"])
    rows = deepcopy(job.items)
    rows[0].update(state="BLOCKED", attempts=1, error="Varias fuentes candidatas")
    rows[0]["automation"].update(search_requests=1, search_daily_counts={"2026-11-28": 1},
        phase="SEARCHING", search={"queried_at": "2026-11-28T00:00:00+00:00", "results": search.results})
    rows[0]["processing"] = {"phase": "BLOCKED", "error_code": "AMBIGUOUS_SEARCH_RESULTS", "retryable": False}
    job.items = rows
    db.commit()
    return service, service.detail(job.id), search


def test_one_explicit_selection_resumes_without_another_search_and_no_autoapproval(engine):
    with Session(engine) as db:
        service, job, search = ambiguous(db)
        before = deepcopy(db.get(SourceIntakeJob, job["id"]).items[0])
        selected = select_source(service, job["id"], job["revision"], IDENT, FIRST, REASON)
        row = selected["items"][0]
        assert row["state"] == "PENDING" and row["url"] == FIRST
        assert row["automation"]["phase"] == "SOURCE_SELECTED_PENDING_REVIEW"
        assert row["automation"]["search_requests"] == before["automation"]["search_requests"]
        assert row["automation"]["search_daily_counts"] == before["automation"]["search_daily_counts"]
        assert row["attempts"] == before["attempts"]
        assert row["automation"]["official_verified"] is False
        run, http = importer()
        finished = service.step(job["id"], selected["revision"], explicit_importer=run)
        assert search.calls == [] and len(http.requests) == 2
        document = db.get(Document, finished["items"][0]["document_id"])
        assert document.body["source"]["review_state"] == "PENDING"
        assert all(fact["state"] == "PENDING" for fact in db.get(Dossier, IDENT).facts)
        assert db.scalar(select(EcommApiProductEdit)) is None
        assert db.scalar(select(KikiAiEditorialDraft)) is None
        assert db.get(SourceIntakeJob, job["id"]).history[-1]["action"] != "FACT_APPROVED"
    with Session(engine) as db:
        reloaded = CatalogAutomation(db, USER, Search(), HOST).detail(job["id"])
        assert reloaded["items"][0]["automation"]["source_selections"][0]["reason"] == REASON


def test_selection_is_local_with_network_disabled_and_preserves_cost_limits(engine):
    with Session(engine) as db:
        service, job, search = ambiguous(db, enabled=False)
        selected = select_source(service, job["id"], job["revision"], IDENT, SECOND, REASON)
        assert selected["search_requests"] == 1 and search.calls == []
        def forbidden(*args, **kwargs):
            pytest.fail("Selection must not enable downloads")
        result = service.step(job["id"], selected["revision"], explicit_importer=forbidden)
        assert result["items"][0]["processing"]["error_code"] == "PROVIDERS_DISABLED"
        assert search.calls == []


@pytest.mark.parametrize("url", ["https://comercio.invalid/arroz/", "https://unauthorized.invalid/producto/", "https://127.0.0.1/private/", FIRST + "?x=1", "https://fabricante-prueba.invalid/unknown/"])
def test_secondary_unconfigured_private_or_unrecorded_url_cannot_be_selected(engine, url):
    with Session(engine) as db:
        service, job, search = ambiguous(db)
        before = deepcopy(db.get(SourceIntakeJob, job["id"]).items)
        with pytest.raises(ValueError):
            select_source(service, job["id"], job["revision"], IDENT, url, REASON)
        db.rollback()
        assert db.get(SourceIntakeJob, job["id"]).items == before and search.calls == []


@pytest.mark.parametrize("change", ["revision", "identity", "running", "cancelled", "completed", "budget", "wrong_variant", "reason"])
def test_cas_identity_active_job_completion_and_attempt_limit_cannot_be_bypassed(engine, change):
    with Session(engine) as db:
        service, job, search = ambiguous(db)
        record = db.get(SourceIntakeJob, job["id"])
        rows = deepcopy(record.items)
        if change == "running":
            rows[0]["state"] = "RUNNING"
        elif change == "cancelled":
            record.state = "CANCELLED"
        elif change == "completed":
            rows[0]["state"] = "IMPORTED"
            rows[0]["document_id"] = "local-" + "a" * 32
        elif change == "budget":
            rows[0]["attempts"] = 3
        elif change == "identity":
            capture = db.scalar(select(CatalogSnapshot).where(CatalogSnapshot.source == "ECOMM_APP_API_STAGE"))
            changed = deepcopy(capture.payload)
            changed[0]["items"][0]["variants"][0]["sku"] = "CHANGED"
            capture.payload = changed
        record.items = rows
        db.commit()
        before = deepcopy(record.items)
        with pytest.raises(ValueError):
            select_source(service, job["id"], job["revision"] + (1 if change == "revision" else 0),
                "1234567" if change == "wrong_variant" else IDENT, FIRST, "corto" if change == "reason" else REASON)
        db.rollback()
        assert db.get(SourceIntakeJob, job["id"]).items == before and search.calls == []


def test_original_already_archived_after_lost_reply_cannot_be_discarded_by_source_swap(engine):
    with Session(engine) as db:
        service, job, search = ambiguous(db)
        record = db.get(SourceIntakeJob, job["id"])
        rows = deepcopy(record.items)
        rows[0]["url"] = FIRST
        record.items = rows
        # A real archived original may predate pin persistence after a crash.
        doc = Document(id="local-" + "f" * 32, version=1,
                       body={"associated_ecomm_id": IDENT, "source": {"reference_url": FIRST}},
                       digest="f" * 64, history=[])
        db.add(doc)
        db.commit()
        with pytest.raises(ValueError, match="original archivado"):
            select_source(service, job["id"], job["revision"], IDENT, SECOND, REASON)
        db.rollback()
        assert db.get(SourceIntakeJob, job["id"]).items[0]["url"] == FIRST
        assert db.get(Document, doc.id) is not None and search.calls == []
