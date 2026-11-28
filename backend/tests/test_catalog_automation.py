"""Offline integral pipeline: actual intake/parser/research, mock search+HTTP."""

from copy import deepcopy
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import (
    CatalogSnapshot,
    EcommApiProductEdit,
    KikiAiEditorialDraft,
)
from app.services.documental.catalog_automation import CatalogAutomation
from app.services.documental.storage import Document, Dossier
from app.services.documental.source_intake_storage import SourceIntakeJob
from test_stage3_pipeline import engine as stage3_engine, importer, USER
from test_documental_manufacturer_batch_intake import FIRST, SECOND, HOST
from test_documental_complete_draft_flow import IDENT


@pytest.fixture
def engine(tmp_path, monkeypatch):
    yield from stage3_engine.__wrapped__(tmp_path, monkeypatch)


class Search:
    def __init__(self, results=None, error=False):
        self.calls = []
        self.results = (
            results
            if results is not None
            else [
                {
                    "url": FIRST,
                    "source_kind": "OFFICIAL_CANDIDATE",
                    "title": "Referencia FICTICIA",
                    "snippet": "No acredita hechos",
                    "official_verified": False,
                }
            ]
        )
        self.error = error

    def search(self, identity):
        self.calls.append(deepcopy(identity))
        if self.error:
            raise ConnectionError("SECRET-DO-NOT-STORE")
        return {
            "provider": "SYNTHETIC_TEST",
            "queried_at": "2026-11-28T12:00:00+00:00",
            "results": self.results,
            "requests": 1,
            "cost_known": False,
        }


def automation(db, search=None, **kwargs):
    return CatalogAutomation(
        db, USER, search or Search(), HOST, network_enabled=True, **kwargs
    )


def test_one_action_searches_archives_original_extracts_pending_with_correct_provenance(
    engine,
):
    search = Search()
    with Session(engine) as db:
        service = automation(db, search)
        created = service.create(str(uuid4()), [IDENT])
        assert created["selection_mode"] == "AUTOMATED_SEARCH"
        run, http = importer()
        result = service.step(created["id"], created["revision"], explicit_importer=run)
        row = result["items"][0]
        assert len(search.calls) == 1 and len(http.requests) == 2
        assert search.calls[0]["ecomm_id"] == IDENT
        assert row["public_state"] == "EVIDENCE_REVIEW_REQUIRED"
        assert row["processing"]["phase"] == "EXTRACTED"
        doc = db.get(Document, row["document_id"])
        assert doc.body["retrieval"]["selection_mode"] == "AUTOMATED_SEARCH_CANDIDATE"
        assert doc.body["source"]["review_state"] == "PENDING"
        assert doc.body["source"]["declared_official"] is False
        facts = db.get(Dossier, IDENT).facts
        assert facts and all(
            f["state"] == "PENDING" and f["reviewer"] is None for f in facts
        )
        assert all(f["quote"] in doc.body["sections"][f["location"]] for f in facts)
        assert row["automation"]["search"]["official_verified"] is False
        assert db.scalar(select(EcommApiProductEdit)) is None
        assert db.scalar(select(KikiAiEditorialDraft)) is None
    with Session(engine) as db:
        reloaded = automation(db).detail(created["id"])
        assert reloaded["items"][0]["document_id"] == row["document_id"]
        assert (
            reloaded["commercial_fields_saved"]
            == reloaded["automatic_fact_approvals"]
            == 0
        )


@pytest.mark.parametrize(
    "results,code",
    [
        ([{"url": FIRST, "source_kind": "SECONDARY"}], "NO_AUTHORIZED_SOURCE"),
        (
            [
                {
                    "url": "https://unauthorized.invalid/producto/",
                    "source_kind": "OFFICIAL_CANDIDATE",
                }
            ],
            "NO_AUTHORIZED_SOURCE",
        ),
        (
            [
                {"url": FIRST, "source_kind": "OFFICIAL_CANDIDATE"},
                {"url": SECOND, "source_kind": "OFFICIAL_CANDIDATE"},
            ],
            "AMBIGUOUS_SEARCH_RESULTS",
        ),
        ([], "NO_AUTHORIZED_SOURCE"),
    ],
)
def test_ambiguous_or_secondary_search_results_are_exceptions_not_downloads(
    engine, results, code
):
    with Session(engine) as db:
        service = automation(db, Search(results))
        job = service.create(str(uuid4()), [IDENT])

        def forbidden(*_args, **_kwargs):
            pytest.fail("An unapproved domain/ambiguous source must not be fetched")

        result = service.step(job["id"], job["revision"], explicit_importer=forbidden)
        row = result["items"][0]
        assert row["state"] == "BLOCKED"
        assert row["processing"]["error_code"] == code
        assert row["automation"]["search"]["results"] == [
            {
                "url": r["url"],
                "title": "",
                "snippet": "",
                "source_kind": r["source_kind"],
                "official_verified": False,
                "evidence_approved": False,
            }
            for r in results
        ]
        assert row["document_id"] is None


def test_default_disabled_never_calls_search_or_downloader(engine):
    with Session(engine) as db:
        search = Search()
        service = CatalogAutomation(db, USER, search, HOST)
        job = service.create(str(uuid4()), [IDENT])
        result = service.step(
            job["id"],
            job["revision"],
            explicit_importer=lambda *_a, **_k: pytest.fail("No HTTP"),
        )
        assert search.calls == []
        assert result["items"][0]["processing"]["error_code"] == "PROVIDERS_DISABLED"


def test_search_budget_survives_reopen_and_explicit_retry_without_exposing_errors(
    engine,
):
    with Session(engine) as db:
        service = automation(db, Search(error=True), max_search_requests=1)
        job = service.create(str(uuid4()), [IDENT])
        failed = service.step(job["id"], job["revision"])
        assert failed["items"][0]["processing"]["retryable"]
        assert "SECRET" not in repr(failed)
    with Session(engine) as db:
        search = Search()
        service = automation(db, search)
        retried = service.queue.retry(job["id"], failed["revision"], IDENT)
        result = service.step(job["id"], retried["revision"])
        assert search.calls == []
        assert (
            result["items"][0]["processing"]["error_code"] == "SEARCH_BUDGET_EXHAUSTED"
        )
        assert result["search_requests"] == 1


def test_cached_original_is_reused_across_jobs_without_research_or_autoapproval(engine):
    with Session(engine) as db:
        service = automation(db)
        created = service.create(str(uuid4()), [IDENT])
        run, http = importer()
        result = service.step(created["id"], created["revision"], explicit_importer=run)
        facts = deepcopy(db.get(Dossier, IDENT).facts)
        original_id = result["items"][0]["document_id"]
    with Session(engine) as db:
        search = Search(error=True)
        service = automation(db, search)
        created = service.create(str(uuid4()), [IDENT])
        assert created["items"][0]["automation"]["reused_original"]
        result = service.step(
            created["id"],
            created["revision"],
            explicit_importer=lambda *_a, **_k: pytest.fail("No duplicate download"),
        )
        assert search.calls == [] and len(http.requests) == 2
        assert result["items"][0]["document_id"] == original_id
        assert db.get(Dossier, IDENT).facts == facts
        assert result["items"][0]["public_state"] == "EVIDENCE_REVIEW_REQUIRED"


def test_changed_identity_and_pack_block_before_search_or_assignment(engine):
    with Session(engine) as db:
        search = Search()
        service = automation(db, search)
        job = service.create(str(uuid4()), [IDENT])
        capture = db.scalar(
            select(CatalogSnapshot).where(
                CatalogSnapshot.source == "ECOMM_APP_API_STAGE"
            )
        )
        pages = deepcopy(capture.payload)
        pages[0]["items"][0]["variants"][0]["is_combo"] = True
        capture.payload = pages
        db.commit()
        result = service.step(job["id"], job["revision"])
        assert search.calls == []
        assert result["items"][0]["processing"]["error_code"] == "API_IDENTITY_CHANGED"
        new = service.create(str(uuid4()), [IDENT])
        assert new["items"][0]["state"] == "BLOCKED"
        assert new["items"][0]["processing"]["error_code"] == "PACK_REVIEW_REQUIRED"


def test_create_idempotence_selection_limit_and_foreign_queue_guard(engine):
    with Session(engine) as db:
        service = automation(db)
        key = str(uuid4())
        first = service.create(key, [IDENT])
        assert service.create(key, [IDENT])["id"] == first["id"]
        for ids in ([IDENT, IDENT], [str(1_000_000 + i) for i in range(21)], ["FAKE"]):
            with pytest.raises(ValueError):
                service.create(str(uuid4()), ids)
        job = db.get(SourceIntakeJob, first["id"])
        rows = deepcopy(job.items)
        rows[0]["source_mode"] = "EXACT_OPERATOR_URL"
        job.items = rows
        db.commit()
        with pytest.raises(ValueError, match="circuito integral"):
            service.detail(job.id)


def test_explicit_human_approval_then_idempotent_existing_proposals_without_network(
    engine,
):
    from app.services.documental.local_documents import LocalDocuments
    from app.services.documental.contracts import Provenance
    from app.services.documental.research import Research

    with Session(engine) as db:
        service = automation(db)
        job = service.create(str(uuid4()), [IDENT])
        run, _ = importer()
        pending = service.step(job["id"], job["revision"], explicit_importer=run)
        docid = pending["items"][0]["document_id"]
        doc = db.get(Document, docid)
        LocalDocuments(db, USER).provenance(
            IDENT,
            docid,
            Provenance(
                expected_document_version=doc.version,
                decision="REVIEWED",
                reason="Revisión humana SINTÉTICA de la prueba, no aceptación del fabricante ni cliente.",
            ),
        )
        research = Research(db, USER)
        item = research.dossier(IDENT)
        doc = db.get(Document, docid)
        research.extract(IDENT, item.version, docid, doc.version)
        for factid in [fact["id"] for fact in research.dossier(IDENT).facts]:
            item = research.dossier(IDENT)
            fact = next(f for f in item.facts if f["id"] == factid)
            research.review(
                IDENT,
                item.version,
                factid,
                fact["version"],
                "APPROVED",
                "Aprobación humana explícita SINTÉTICA de la cita del original ficticio.",
            )
        db.commit()
        # An explicit local continuation creates the existing deterministic
        # proposal, without fetching, generating paid AI or saving a fiche.
        ready = service.prepare_proposals(job["id"], pending["revision"])
        row = ready["items"][0]
        assert row["public_state"] == "PROPOSAL_REVIEW_REQUIRED"
        draft = db.get(KikiAiEditorialDraft, row["automation"]["proposal"]["draft_id"])
        assert draft.review_status == "PENDING_REVIEW"
        assert len(db.scalars(select(KikiAiEditorialDraft)).all()) == 1
        assert db.scalar(select(EcommApiProductEdit)) is None
        again = service.prepare_proposals(job["id"], ready["revision"])
        assert again["items"][0]["automation"]["proposal"]["draft_id"] == draft.id
        assert len(db.scalars(select(KikiAiEditorialDraft)).all()) == 1
        from app.services.documental.proposals import Proposals
        from app.services.ecomm_api_product_workspace_service import blank_fields
        from types import SimpleNamespace

        proposals = Proposals(db, USER)
        dto = proposals.latest(IDENT)
        title = dto["fields"]["title"]["value"]
        reviewed = proposals.review(
            IDENT,
            dto["draft_id"],
            dto["revision"],
            {"title": {"decision": "ACCEPTED", "value": title}},
        )
        fields = blank_fields()
        fields["title"] = title
        proposals.apply(
            IDENT,
            dto["draft_id"],
            reviewed["revision"],
            SimpleNamespace(
                expected_version=0,
                status="DRAFT",
                fields=SimpleNamespace(model_dump=lambda: fields),
            ),
        )
        applied = service.prepare_proposals(job["id"], again["revision"])
        assert applied["items"][0]["public_state"] == "DRAFT_SAVED"
        assert len(db.scalars(select(KikiAiEditorialDraft)).all()) == 1
        assert db.scalar(select(EcommApiProductEdit)).version == 1
        with pytest.raises(ValueError):
            service.prepare_proposals(job["id"], pending["revision"])


def test_lost_step_response_replay_has_no_duplicate_search_or_original(engine):
    with Session(engine) as db:
        search = Search()
        service = automation(db, search)
        job = service.create(str(uuid4()), [IDENT])
        run, http = importer()
        result = service.step(job["id"], job["revision"], explicit_importer=run)
        with pytest.raises(ValueError):
            service.step(job["id"], job["revision"], explicit_importer=run)
        db.rollback()
        assert len(search.calls) == 1 and len(http.requests) == 2
        assert (
            service.detail(job["id"])["items"][0]["document_id"]
            == result["items"][0]["document_id"]
        )


def test_global_daily_budget_cannot_be_bypassed_with_new_job_or_cancellation(engine):
    with Session(engine) as db:
        first_search = Search(results=[])
        first = automation(db, first_search, daily_search_limit=1)
        created = first.create(str(uuid4()), [IDENT])
        blocked = first.step(created["id"], created["revision"])
        assert len(first_search.calls) == 1
        first.queue.cancel(created["id"], blocked["revision"])
    with Session(engine) as db:
        second_search = Search()
        second = automation(db, second_search, daily_search_limit=1)
        created = second.create(str(uuid4()), [IDENT])
        blocked = second.step(created["id"], created["revision"])
        assert second_search.calls == []
        assert (
            blocked["items"][0]["processing"]["error_code"]
            == "GLOBAL_SEARCH_DAILY_BUDGET"
        )


def test_reader_not_ready_prevents_search_download_and_quota_reservation(engine):
    with Session(engine) as db:
        search = Search()
        service = automation(db, search, readiness_check=lambda: False)
        job = service.create(str(uuid4()), [IDENT])
        result = service.step(
            job["id"],
            job["revision"],
            explicit_importer=lambda *_a, **_k: pytest.fail("No download"),
        )
        assert search.calls == []
        assert result["search_requests"] == 0
        assert result["items"][0]["processing"]["error_code"] == "READER_UNAVAILABLE"


def test_excessive_cached_sources_block_before_reading_full_originals(engine):
    from app.services.documental.storage import digest

    with Session(engine) as db:
        for index in range(11):
            body = {"associated_ecomm_id": IDENT, "source": {}}
            db.add(
                Document(
                    id="local-" + f"{index+100:032x}",
                    version=1,
                    body=body,
                    digest=digest(body),
                    history=[],
                )
            )
        db.commit()
        search = Search()
        result = automation(db, search).create(str(uuid4()), [IDENT])
        assert result["items"][0]["state"] == "BLOCKED"
        assert result["items"][0]["processing"]["error_code"] == "CACHED_SOURCE_LIMIT"
        assert search.calls == []


@pytest.mark.parametrize("changed", [False, True])
def test_stale_authorized_html_refreshes_same_url_with_pinned_receipt_and_no_search(
    engine, changed
):
    from datetime import datetime, timedelta, timezone
    from app.services.documental.storage import digest

    with Session(engine) as db:
        initial = automation(db)
        created = initial.create(str(uuid4()), [IDENT])
        run, _ = importer()
        acquired = initial.step(
            created["id"], created["revision"], explicit_importer=run
        )
        document = db.get(Document, acquired["items"][0]["document_id"])
        body = deepcopy(document.body)
        old = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
        body["source"].update(registered_at=old, declared_consulted_at=old)
        body["retrieval"]["acquired_at"] = old
        document.body = body
        document.digest = digest(body)
        db.commit()
        from app.services.documental.research import Research

        Research(db, USER).dossier(IDENT)
        db.commit()
        original_version = document.version
        original_sha = body["original"]["sha256"]
        search = Search(error=True)
        service = automation(db, search)
        job = service.create(str(uuid4()), [IDENT])
        item = job["items"][0]
        assert item["automation"]["phase"] == "REFRESH_REQUIRED"
        assert (
            item["automation"]["refresh_receipt"]["document_digest"] == document.digest
        )
        assert item["document_id"] is None
        refresh, http = importer()
        if changed:
            http.content += b"<!-- Cambio documental SINTETICO del test -->"
        result = service.step(job["id"], job["revision"], explicit_importer=refresh)
        row = result["items"][0]
        assert search.calls == [] and len(http.requests) == 2
        assert row["processing"]["phase"] == "EXTRACTED", row
        document = db.get(Document, row["document_id"])
        assert document.version == original_version + int(changed)
        if changed:
            assert document.body["original"]["sha256"] != original_sha
            assert document.body["source"]["review_state"] == "PENDING"
        else:
            assert document.body["original"]["sha256"] == original_sha
        assert not any(f["state"] == "APPROVED" for f in db.get(Dossier, IDENT).facts)
        assert db.scalar(select(EcommApiProductEdit)) is None
        # The successful unchanged-byte observation is a freshness receipt,
        # not human sign-off. Another job reuses it without a third GET.
        again = service.create(str(uuid4()), [IDENT])
        assert again["items"][0]["automation"]["reused_original"]
        assert "refresh_receipt" not in again["items"][0]["automation"]


def test_old_interrupted_job_remains_visible_and_listing_has_no_per_job_queries(engine):
    from sqlalchemy import event
    from datetime import datetime, timedelta, timezone

    with Session(engine) as db:
        service = automation(db)
        oldest = service.create(str(uuid4()), [IDENT])
        original = db.get(SourceIntakeJob, oldest["id"])
        original.created_at = datetime.now(timezone.utc) - timedelta(days=5)
        rows = deepcopy(original.items)
        rows[0].update(
            state="RUNNING",
            claim_token="synthetic-interrupted",
            claim_until=(datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
        )
        original.items = rows
        db.commit()
        for _ in range(22):
            service.create(str(uuid4()), [IDENT])
        queries = []

        def collect(_conn, _cursor, statement, _params, _context, _many):
            if statement.lstrip().upper().startswith("SELECT"):
                queries.append(statement)

        event.listen(engine, "before_cursor_execute", collect)
        try:
            result = service.listing()
        finally:
            event.remove(engine, "before_cursor_execute", collect)
        assert len(result["items"]) == 20
        assert result["items"][0]["id"] == oldest["id"]
        assert result["items"][0]["recoverable_items"] == 1
        assert len(queries) <= 2
