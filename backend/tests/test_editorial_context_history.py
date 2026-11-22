"""Read-only batch projections retain human decisions, never synthesize sign-offs."""

from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.services.documental.proposals import Proposals
from app.services.documental.research import Research, identity_digest
from app.services.editorial_batches.context import Context
from app.services.editorial_batches.preview_projection import project, _edit_projection
from app.services.ecomm_api_product_workspace_service import (
    blank_fields,
    review_schedule,
)


def test_batch_inspection_retains_exact_document_identity_decision():
    reference = {
        "name": "Producto de prueba",
        "presentation": "250 g",
        "is_combo": False,
    }
    record = {"document_id": "doc-1", "decision": "APPROVED"}
    history = [{"action": "DOCUMENT_IDENTITY_REVIEW", "detail": record}]
    original = deepcopy(history)
    fact = {
        "id": "fact-1",
        "field": "product_name",
        "value": reference["name"],
        "unit": None,
        "state": "APPROVED",
        "document_id": "doc-1",
        "document_version": 1,
        "document_hash": "a" * 64,
        "version": 1,
    }
    edit = {
        "version": 0,
        "fields": blank_fields(),
        "source_sku_changed": False,
        "source": {},
        "status": "DRAFT",
        "review_schedule": {"review_due": False},
    }

    class PreviewResearch:
        def __init__(self, *_args):
            pass

        def reference(self, _ident):
            return reference

        def blockers(self, case, _fact):
            # This is the real historical lookup that raised AttributeError
            # whenever the batch contained a document with approved facts.
            assert (
                Research._equivalence_record(case, SimpleNamespace(id="doc-1"))
                == record
            )
            assert (
                Research._equivalence_record(case, SimpleNamespace(id="other-doc"))
                is None
            )
            case.history.append({"action": "UNSAVED_TEST_CHANGE"})
            return []

    ctx = object.__new__(Context)
    ctx.dossiers = {
        "123": SimpleNamespace(
            version=3,
            identity_digest=identity_digest(reference),
            facts=[fact],
            history=history,
        )
    }
    ctx.documents = {
        "doc-1": SimpleNamespace(
            id="doc-1",
            version=1,
            digest="a" * 64,
            body={
                "associated_ecomm_id": "123",
                "sections": {"1": "Producto de prueba"},
            },
        )
    }
    ctx.Research, ctx.Proposals = PreviewResearch, Proposals
    ctx.Workspace = lambda _db: SimpleNamespace(get=lambda _ident: edit)
    result = ctx.inspect(object(), SimpleNamespace(id=1), "123")
    assert result["approved_fact_count"] == 1
    assert result["conflicts"] is False
    assert history == original  # preview cannot change approvals/history


def projected(history):
    values = {
        "ecomm_id": "123",
        "status": "READY_FOR_CHANNELS",
        "review_events": history,
    }
    return _edit_projection(SimpleNamespace(**values, _mapping=values))


def test_preview_save_does_not_reset_monthly_review_and_confirmation_is_preserved(
    monkeypatch,
):
    import app.services.ecomm_api_product_workspace_service as workspace

    monkeypatch.setattr(
        workspace, "_now", lambda: datetime(2026, 11, 22, tzinfo=timezone.utc)
    )
    initial = {
        "new_status": "READY_FOR_CHANNELS",
        "previous_status": "DRAFT",
        "at": "2026-11-01T10:00:00+00:00",
        "changes": {"title": "initial"},
    }
    edit = {
        "new_status": "READY_FOR_CHANNELS",
        "previous_status": "READY_FOR_CHANNELS",
        "at": "2026-11-20T10:00:00+00:00",
        "changes": {"title": "changed"},
    }
    review = {
        "action": "REVIEW_CONFIRMED",
        "new_status": "READY_FOR_CHANNELS",
        "previous_status": "READY_FOR_CHANNELS",
        "changes": {},
        "at": "2026-11-21T10:00:00+00:00",
    }
    pending = review_schedule(projected([initial, edit]))
    assert pending["review_reason"] == "CONTENT_CHANGED"
    assert pending["last_review_at"] == initial["at"]
    current = review_schedule(projected([initial, edit, review]))
    assert current["review_reason"] == "CURRENT"
    assert current["last_review_at"] == review["at"]
    later = {**edit, "at": "2026-11-22T09:00:00+00:00"}
    changed = review_schedule(projected([initial, edit, review, later]))
    assert changed["review_reason"] == "CONTENT_CHANGED"
    assert changed["last_review_at"] == review["at"]


def test_project_rejects_editorial_review_budget_before_materializing_rows():
    class Oversize:
        def scalar(self, query):
            sql = str(query)
            assert "jsonb_path_query_array" in sql
            assert "history" in sql and "fields" in sql
            return 65_537

        def execute(self, *_args, **_kwargs):
            pytest.fail("Oversized history must be rejected before reading payloads")

    with pytest.raises(ValueError, match="revisiones editoriales"):
        project(Oversize(), ["123"], 65_536)


def test_project_budgets_filtered_documentary_decisions_before_reading_them():
    class Oversize:
        calls = 0

        def scalar(self, query, *_args):
            self.calls += 1
            if self.calls == 1:
                return 0
            sql = str(query)
            assert "DOCUMENT_IDENTITY_REVIEW" in sql
            assert "octet_length(history::text)" in sql
            assert "octet_length(identity::text)" in sql
            return 65_537

        def execute(self, query, *_args):
            assert "review_events" in str(query)
            return []

    with pytest.raises(ValueError, match="decisiones documentales"):
        project(Oversize(), ["123"], 65_536)
