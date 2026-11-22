"""Versioned operator classification, using only disposable synthetic documents."""

from copy import deepcopy
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import CatalogSnapshot, EcommApiProductEdit
from app.services.documental.storage import Dossier
from app.services.documental.taxonomy_review import (
    TaxonomyReview,
    current_review,
    histories_for,
)
from app.services.documental.commercial_plan import summarize_inspections
from app.services.documental.taxonomy_alignment import align_taxonomy, seo_field_audit
import test_documental_complete_draft_flow as draft_fixture
import test_documental_channel_readiness_guard as guard_fixture


@pytest.fixture
def database(tmp_path, monkeypatch):
    import app.services.documental.research as research_module

    monkeypatch.setattr(
        research_module,
        "get_settings",
        lambda: SimpleNamespace(kiki_admin_username="synthetic-reviewer"),
    )
    engine, stage = draft_fixture.prepare(tmp_path)
    with Session(engine) as db:
        guard_fixture.install_fake_source(db)
        db.commit()
    yield engine, stage
    engine.dispose()


def approve(service, state, **overrides):
    values = {
        "expected_version": state["expected_version"],
        "expected_workspace_version": state["expected_workspace_version"],
        "expected_fingerprint": state["evidence_fingerprint"],
        "channel": state["channel"],
        "decision": "APPROVED",
        "taxonomy_revision": "KIKI-vocabulary-synthetic-v1",
        "target_category": state["source_pair"]["category"],
        "target_subcategory": state["source_pair"]["subcategory"],
        "reason": "Comprobé las citas de categoría, identidad y presentación de prueba.",
        **overrides,
    }
    return service.review(draft_fixture.IDENT, **values)


def test_human_mapping_persists_with_citations_and_does_not_save_fiche(database):
    engine, stage = database
    with Session(engine) as db:
        service = TaxonomyReview(db, SimpleNamespace(id=1))
        state = service.get(draft_fixture.IDENT)
        assert state["state"] == "NONE" and state["can_approve"]
        before_facts = deepcopy(db.get(Dossier, draft_fixture.IDENT).facts)
        result = approve(service, state)
        assert result["state"] == "APPROVED"
        assert result["mapping_version"] == 1
        assert len(result["record"]["evidence_ids"]) == 2
        assert result["record"]["review_kind"] == "HUMAN_EXPLICIT"
        assert result["record"]["reviewer"].startswith("synthetic-reviewer")
        assert not result["official_external_category_verified"]
        assert result["external_category_ids"] is None
        assert result["editorial_fields_applied"] is False
        assert db.get(Dossier, draft_fixture.IDENT).facts == before_facts
        assert db.scalar(select(EcommApiProductEdit)) is None
        assert db.scalar(select(CatalogSnapshot)).payload == stage
    with Session(engine) as db:
        restored = TaxonomyReview(db, SimpleNamespace(id=2)).get(draft_fixture.IDENT)
        assert restored["state"] == "APPROVED"
        assert restored["record"]["taxonomy_revision"] == "KIKI-vocabulary-synthetic-v1"
        assert len(restored["history"]) == 1


def test_two_operators_cannot_silently_replace_the_same_revision(database):
    engine, _ = database
    with Session(engine) as first, Session(engine) as second:
        one, two = (
            TaxonomyReview(first, SimpleNamespace(id=1)),
            TaxonomyReview(second, SimpleNamespace(id=2)),
        )
        a, b = one.get(draft_fixture.IDENT), two.get(draft_fixture.IDENT)
        approve(one, a)
        with pytest.raises(ValueError, match="otra sesión"):
            approve(two, b, taxonomy_revision="not-accepted")
        second.rollback()
        assert (
            two.get(draft_fixture.IDENT)["record"]["taxonomy_revision"]
            != "not-accepted"
        )


def test_revocation_preserves_previous_mapping_and_fact_history(database):
    engine, _ = database
    with Session(engine) as db:
        service = TaxonomyReview(db, SimpleNamespace(id=1))
        approved = approve(service, service.get(draft_fixture.IDENT))
        facts = deepcopy(db.get(Dossier, draft_fixture.IDENT).facts)
        result = approve(
            service,
            approved,
            decision="REVOKED",
            target_category="Must not replace original",
        )
        assert result["state"] == "REVOKED"
        assert result["mapping_version"] == 2
        assert result["record"]["target_pair"] == approved["record"]["target_pair"]
        assert db.get(Dossier, draft_fixture.IDENT).facts == facts
        assert len(result["history"]) == 2


def test_channel_mappings_do_not_transfer_between_channels(database):
    engine, _ = database
    with Session(engine) as db:
        service = TaxonomyReview(db, SimpleNamespace(id=1))
        approve(service, service.get(draft_fixture.IDENT, "ML"))
        for channel in ("KIKI", "TN", "ECOMM"):
            assert service.get(draft_fixture.IDENT, channel)["state"] == "NONE"


def test_changed_document_invalidates_mapping_and_old_decision(database):
    engine, _ = database
    with Session(engine) as db:
        service = TaxonomyReview(db, SimpleNamespace(id=1))
        approved = approve(service, service.get(draft_fixture.IDENT))
        from app.services.documental.storage import Document

        doc = db.get(Document, draft_fixture.DOCUMENT_ID)
        doc.version += 1
        db.commit()
        state = service.get(draft_fixture.IDENT)
        assert state["state"] == "STALE"
        assert not state["can_approve"]
        assert state["record"] == approved["record"]
        with pytest.raises(ValueError):
            approve(service, approved)
        db.rollback()


def test_same_ean_or_sku_never_transfers_approval_to_pack(database):
    engine, _ = database
    with Session(engine) as db:
        service = TaxonomyReview(db, SimpleNamespace(id=1))
        approve(service, service.get(draft_fixture.IDENT))
        snapshot = db.scalar(select(CatalogSnapshot))
        pages = deepcopy(snapshot.payload)
        other = deepcopy(pages[0]["items"][0]["variants"][0])
        other.update(
            id="PACK-SYNTHETIC-2", is_combo=True, variant_description="Pack x2 de 250 g"
        )
        pages[0]["items"][0]["variants"].append(other)
        snapshot.payload = pages
        db.commit()
        state = service.get("PACK-SYNTHETIC-2")
        assert state["state"] == "NONE"
        assert not state["can_approve"]
        assert not state["record"]


def test_invalid_fingerprint_reason_and_channel_are_rejected(database):
    engine, _ = database
    with Session(engine) as db:
        service = TaxonomyReview(db, SimpleNamespace(id=1))
        state = service.get(draft_fixture.IDENT)
        for override in (
            {"expected_fingerprint": "0" * 64},
            {"reason": "short"},
            {"channel": "OTHER"},
        ):
            with pytest.raises(ValueError):
                approve(service, state, **override)
            db.rollback()
        assert service.get(draft_fixture.IDENT)["mapping_version"] == 0


def test_workspace_version_change_requires_new_mapping(database):
    engine, _ = database
    with Session(engine) as db:
        service = TaxonomyReview(db, SimpleNamespace(id=1))
        approved = approve(service, service.get(draft_fixture.IDENT))
        db.add(
            EcommApiProductEdit(
                ecomm_id=draft_fixture.IDENT,
                source_sku="9995",
                source_snapshot={},
                fields={},
                status="DRAFT",
                version=1,
                history=[],
            )
        )
        db.commit()
        assert service.get(draft_fixture.IDENT)["state"] == "STALE"
        with pytest.raises(ValueError, match="ficha cambió"):
            approve(
                service,
                approved,
                expected_version=service.get(draft_fixture.IDENT)["expected_version"],
            )
        db.rollback()


def test_history_budget_and_cross_identity_reuse_fail_closed(database):
    engine, _ = database
    with Session(engine) as db:
        service = TaxonomyReview(db, SimpleNamespace(id=1))
        result = approve(service, service.get(draft_fixture.IDENT))
        with pytest.raises(ValueError, match="límite"):
            histories_for(db, [draft_fixture.IDENT], byte_limit=1)
        history = histories_for(db, [draft_fixture.IDENT], byte_limit=1_000_000)
        _r, _item, _edit, inspection = service._context(draft_fixture.IDENT)
        assert (
            current_review(inspection, history[draft_fixture.IDENT])["state"]
            == "APPROVED"
        )
        inspection["ecomm_id"] = "OTHER-VARIANT"
        assert (
            current_review(inspection, history[draft_fixture.IDENT])["state"] == "STALE"
        )
        assert result["mapping_version"] == 1


def test_commercial_plan_consumes_mapping_without_rewriting_source():
    from test_documental_taxonomy_alignment import inspected, category_facts

    row = inspected(
        taxonomy=category_facts(),
        supported_proposal_fields=["category", "subcategory", "seo_keywords"],
    )
    row["reviewed_taxonomy_mapping"] = {
        "state": "APPROVED",
        "mapping_version": 1,
        "record": {
            "source_pair": {"category": "Semillas", "subcategory": "Mix de semillas"},
            "target_pair": {"category": "Dietética", "subcategory": "Semillas"},
        },
    }
    taxonomy = align_taxonomy(row, {})
    assert taxonomy["state"] == "REVIEWED_INTERNAL_MAPPING"
    assert taxonomy["source_approved"]["category"] == "Semillas"
    assert (
        taxonomy["reviewed_mapping"]["record"]["target_pair"]["category"] == "Dietética"
    )
    assert seo_field_audit(row, taxonomy)["seo_keywords"] == "REVIEW_TAXONOMY"
    report = summarize_inspections([("101", row)], {})
    assert report["items"][0]["next_task"] == "GENERATE"
    assert "category" not in report["items"][0]["fields_supported"]
    assert "seo_keywords" not in report["items"][0]["fields_supported"]


def test_request_contract_requires_explicit_confirmation():
    from pydantic import ValidationError
    from app.api.routes.ecomm_api_workspace import TaxonomyReviewRequest

    data = dict(
        expected_version=0,
        expected_workspace_version=0,
        expected_fingerprint="a" * 64,
        channel="KIKI",
        decision="APPROVED",
        taxonomy_revision="v1",
        target_category="Semillas",
        target_subcategory="Mix",
        reason="Contrasté el original y la jerarquía interna de prueba.",
    )
    with pytest.raises(ValidationError):
        TaxonomyReviewRequest(**data)
    with pytest.raises(ValidationError):
        TaxonomyReviewRequest(**data, confirm=False)
    assert TaxonomyReviewRequest(**data, confirm=True).confirm is True


def test_api_requires_real_session_csrf_and_existing_feature_flag(
    database, monkeypatch
):
    from datetime import datetime, timedelta, timezone
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.routes import ecomm_api_workspace as routes
    from app.core import security
    from app.database.models import AdminSession
    from app.database.session import get_db

    engine, _ = database
    monkeypatch.setattr(
        security,
        "get_settings",
        lambda: SimpleNamespace(app_session_secret="synthetic-only-csrf-secret"),
    )
    monkeypatch.setattr(
        routes,
        "get_settings",
        lambda: SimpleNamespace(kiki_document_workspace_enabled=True),
    )
    token = "synthetic-only-session-cookie"
    hashed = security.token_hash(token)
    now = datetime.now(timezone.utc)
    with Session(engine) as db:
        db.add(
            AdminSession(
                token_hash=hashed,
                created_at=now,
                last_seen_at=now,
                expires_at=now + timedelta(hours=1),
            )
        )
        db.commit()

    def local_database():
        with Session(engine) as db:
            yield db

    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[get_db] = local_database
    path = f"/api/ecomm-app/workspace/{draft_fixture.IDENT}/taxonomy-review"
    with TestClient(app) as client:
        assert client.get(path).status_code == 401
        client.cookies.set(security.SESSION_COOKIE, token)
        state = client.get(path).json()
        data = dict(
            expected_version=state["expected_version"],
            expected_workspace_version=state["expected_workspace_version"],
            expected_fingerprint=state["evidence_fingerprint"],
            channel="KIKI",
            decision="APPROVED",
            taxonomy_revision="internal-synthetic-v1",
            target_category=state["source_pair"]["category"],
            target_subcategory=state["source_pair"]["subcategory"],
            reason="Contrasté ambas citas y la jerarquía interna de prueba.",
            confirm=True,
        )
        assert client.post(path, json=data).status_code == 403
        result = client.post(
            path, json=data, headers={"X-CSRF-Token": security.csrf_token(hashed)}
        )
        assert result.status_code == 200 and result.json()["state"] == "APPROVED"
        monkeypatch.setattr(
            routes,
            "get_settings",
            lambda: SimpleNamespace(kiki_document_workspace_enabled=False),
        )
        assert client.get(path).status_code == 403
