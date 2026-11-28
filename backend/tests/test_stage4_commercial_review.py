"""Atomic human review uses actual proposals/editor, without network or providers."""
from copy import deepcopy
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.database.models import EcommApiProductEdit, KikiAiEditorialDraft
from app.services.documental.commercial_review import CommercialReview, selection
from app.services.documental.contracts import CommercialReviewApply
from app.services.documental.proposals import Proposals
from app.services.documental.storage import Dossier
from app.services.ecomm_api_product_workspace_service import EcommApiProductWorkspace
import test_documental_complete_draft_flow as fixture
import test_documental_channel_readiness_guard as guard


class SQLiteContext:
    """Replace only PG bulk projection; proposals/editor are unchanged services.

    PostgreSQL18 smoke exercises the actual Context and SQL locks separately.
    """
    Proposals = Proposals
    Workspace = EcommApiProductWorkspace

    def __init__(self, db, ids, source_map, budget, *, lock):
        self.db = db
        assert lock and budget > 0
        assert set(ids).issubset(source_map)

    def release(self):
        pass


@pytest.fixture
def case(tmp_path, monkeypatch):
    import app.services.documental.research as module

    monkeypatch.setattr(module, "get_settings", lambda: SimpleNamespace(kiki_admin_username="synthetic-test-operator"))
    engine, _stage = fixture.prepare(tmp_path)
    user = SimpleNamespace(id=7)
    with Session(engine) as db:
        guard.install_fake_source(db)
        Proposals(db, user).generate(fixture.IDENT, 0)
    yield engine, user
    engine.dispose()


def service(db, user):
    result = CommercialReview(db, user)
    result.context_type = SQLiteContext
    return result


def decision(row, **overrides):
    return {
        "ecomm_id": row["ecomm_id"], "draft_id": row["draft_id"],
        "expected_revision": row["revision"], "expected_workspace_version": row["workspace_version"],
        "decisions": {"title": {"decision": "ACCEPTED", "value": row["fields"]["title"]["value"]}},
        **overrides,
    }


@pytest.mark.parametrize("ids", [[], [""], [None], ["null"], ["None"], ["1", "1"], [str(n) for n in range(21)]])
def test_selection_is_bounded_exact_and_no_null_identity(ids):
    with pytest.raises(ValueError):
        selection(ids)


def test_preview_no_persist_apply_internal_draft_history_and_replay_conflict(case):
    engine, user = case
    with Session(engine) as db:
        review = service(db, user)
        facts_before = deepcopy(db.get(Dossier, fixture.IDENT).facts)
        preview = review.preview([fixture.IDENT])
        db.rollback()
        row = preview["items"][0]
        assert row["state"] == "REVIEW_REQUIRED"
        assert row["fields"]["title"]["evidence_ids"]
        assert all(f["state"] == "APPROVED" for f in row["evidence"])
        assert db.scalar(select(EcommApiProductEdit)) is None
        result = review.apply(preview["fingerprint"], [decision(row)], [fixture.IDENT])
        db.commit()
        assert result["items"][0]["state"] == "SAVED_DRAFT"
        saved = db.scalar(select(EcommApiProductEdit))
        assert saved.status == "DRAFT" and saved.version == 1
        assert saved.fields["title"] == row["fields"]["title"]["value"]
        assert not saved.fields["description"]
        assert saved.history
        assert db.get(Dossier, fixture.IDENT).facts == facts_before
        applied = db.scalar(select(KikiAiEditorialDraft))
        assert applied.review_status == "APPLIED"
        with pytest.raises(ValueError, match="cambió"):
            review.apply(preview["fingerprint"], [decision(row)], [fixture.IDENT])
        db.rollback()
        assert saved.version == 1
    with Session(engine) as db:
        assert EcommApiProductWorkspace(db).get(fixture.IDENT)["fields"]["title"]


def test_reject_does_not_write_editor_or_approve_facts(case):
    engine, user = case
    with Session(engine) as db:
        review = service(db, user)
        preview = review.preview([fixture.IDENT])
        row = preview["items"][0]
        item = decision(row, decisions={"title": {"decision": "REJECTED", "value": row["fields"]["title"]["value"]}})
        result = review.apply(preview["fingerprint"], [item], [fixture.IDENT])
        db.commit()
        assert result["items"][0]["state"] == "REJECTED"
        assert db.scalar(select(EcommApiProductEdit)) is None
        assert db.scalar(select(KikiAiEditorialDraft)).review_status == "REVIEWED"


@pytest.mark.parametrize("mutate", ["unsupported", "false_claim", "outside", "version", "duplicate"])
def test_no_partial_save_or_new_claims(case, mutate):
    engine, user = case
    with Session(engine) as db:
        review = service(db, user)
        preview = review.preview([fixture.IDENT])
        item = decision(preview["items"][0])
        if mutate == "unsupported":
            item["decisions"] = {"media": {"decision": "ACCEPTED", "value": []}}
        elif mutate == "false_claim":
            item["decisions"]["title"]["value"] = "Cura enfermedades sin gluten"
        elif mutate == "outside":
            item["ecomm_id"] = "different-variant"
        elif mutate == "version":
            item["expected_workspace_version"] += 1
        with pytest.raises(ValueError):
            review.apply(preview["fingerprint"], [item, item] if mutate == "duplicate" else [item], [fixture.IDENT])
        db.rollback()
        assert db.scalar(select(EcommApiProductEdit)) is None
        assert db.scalar(select(KikiAiEditorialDraft)).review_status == "PENDING_REVIEW"


def test_route_auth_csrf_and_confirmation_are_not_optional(monkeypatch):
    import app.api.routes.documental_workspace as routes
    from app.core.security import require_session, require_csrf

    monkeypatch.setattr(routes, "get_settings", lambda: SimpleNamespace(kiki_document_workspace_enabled=True))
    app = FastAPI()
    app.include_router(routes.router)
    client = TestClient(app)
    response = client.post("/api/ecomm-app/workspace/commercial-review/preview", json={"ecomm_ids": [fixture.IDENT]})
    assert response.status_code in {401, 403}
    app.dependency_overrides[require_session] = lambda: SimpleNamespace(id=1)
    response = client.post("/api/ecomm-app/workspace/commercial-review/apply", json={})
    assert response.status_code in {401, 403}
    app.dependency_overrides[require_csrf] = lambda: SimpleNamespace(id=1)
    response = client.post("/api/ecomm-app/workspace/commercial-review/apply", json={"ecomm_ids": [fixture.IDENT], "expected_fingerprint": "a" * 64, "items": []})
    assert response.status_code == 422
    with pytest.raises(ValueError):
        CommercialReviewApply.model_validate({"ecomm_ids": [fixture.IDENT], "expected_fingerprint": "a" * 64, "confirm": False, "items": []})
