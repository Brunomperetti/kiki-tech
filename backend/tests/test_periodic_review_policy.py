"""Periodic tasks never imply document approval or commercial mutation."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import CatalogSnapshot, EcommApiProductEdit
from app.services.documental.storage import Document, Dossier, digest
from app.services.monthly_catalog_reports import (
    review_policy,
    save_review_policy,
    preview_periodic_review,
    save_monthly_report,
    acknowledge_monthly_report,
)
from app.services.contractual_delivery_audit_service import build_delivery_audit
from test_documental_complete_draft_flow import prepare, IDENT, DOCUMENT_ID
from test_documental_channel_readiness_guard import install_fake_source

USER = SimpleNamespace(id="SYNTHETIC-MONTHLY-REVIEWER")
NOW = datetime(2026, 12, 20, tzinfo=timezone.utc)


@pytest.fixture
def database(tmp_path, monkeypatch):
    import app.services.monthly_catalog_reports as module
    import app.services.documental.research as research

    monkeypatch.setattr(module, "_now", lambda: NOW)
    monkeypatch.setattr(
        research,
        "get_settings",
        lambda: SimpleNamespace(kiki_admin_username="SYNTHETIC"),
    )
    engine, _ = prepare(tmp_path)
    with Session(engine) as db:
        install_fake_source(db)
    yield engine
    engine.dispose()


def test_persistent_policy_cas_preserves_facts_and_fiche_clock(database):
    with Session(database) as db:
        before = deepcopy(db.get(Dossier, IDENT).facts)
        policy = review_policy(db)
        assert policy["settings"]["interval_days"] == 30
        settings = {**policy["settings"], "interval_days": 20}
        saved = save_review_policy(
            db,
            USER,
            expected_version=0,
            settings=settings,
            reason="Ensayo de configuración mensual explícita sin tocar fichas.",
        )
        assert saved["version"] == 1
        assert saved["editorial_signoff_max_days"] == 30
        assert saved["background_worker_enabled"] is False
        with pytest.raises(ValueError, match="Otro operador"):
            save_review_policy(
                db,
                USER,
                expected_version=0,
                settings=settings,
                reason="No reemplazar una versión revisada por otro operador.",
            )
        db.rollback()
        assert db.get(Dossier, IDENT).facts == before
        assert db.scalar(select(EcommApiProductEdit)) is None
    with Session(database) as db:
        assert review_policy(db)["settings"] == settings
        assert len(review_policy(db)["history"]) == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"interval_days": 0},
        {"interval_days": 31},
        {"enabled": 1},
        {"soon_days": -1},
        {"evidence_max_age_days": True},
        {"api_key": "no"},
    ],
)
def test_invalid_policies_never_persist(database, changes):
    with Session(database) as db:
        with pytest.raises(ValueError):
            save_review_policy(
                db,
                USER,
                expected_version=0,
                settings={**review_policy(db)["settings"], **changes},
                reason="Configuración inválida del ensayo; no debe guardarse.",
            )
        assert review_policy(db)["version"] == 0


def test_detects_expired_changed_revoked_unknown_sources_and_incomplete_fiche(database):
    with Session(database) as db:
        before = deepcopy(db.get(Dossier, IDENT).facts)
        report = preview_periodic_review(db)
        row = next(item for item in report["items"] if item["ecomm_id"] == IDENT)
        assert {
            "UNREVIEWED_PRODUCT",
            "INCOMPLETE_FICHE",
            "EVIDENCE_EXPIRED",
            "PERIODIC_REVIEW_DUE",
        }.issubset(row["reasons"])
        assert db.get(Dossier, IDENT).facts == before
        assert not db.new and not db.dirty
        doc = db.get(Document, DOCUMENT_ID)
        doc.version += 1
        doc.body = {
            **doc.body,
            "version": doc.version,
            "source": {**doc.body["source"], "reviewed_at": None},
        }
        doc.digest = digest(doc.body)
        dossier = db.get(Dossier, IDENT)
        facts = deepcopy(dossier.facts)
        facts[0]["state"] = "REVOKED"
        dossier.facts = facts
        db.commit()
        row = preview_periodic_review(db)["items"][0]
        assert {"SOURCE_CHANGED", "EVIDENCE_REVOKED", "EVIDENCE_DATE_UNKNOWN"}.issubset(
            row["reasons"]
        )
        assert row["state"] == "HUMAN_REVIEW_REQUIRED" and row["automatic_changes"] == 0


def test_baseline_detects_new_variant_and_pending_report_does_not_reset_ack_clock(
    database,
):
    with Session(database) as db:
        summary, _ = build_delivery_audit(db)
        stored = save_monthly_report(
            db, USER, summary["preview_fingerprint"], "Operador sintético"
        )
        acknowledged = acknowledge_monthly_report(
            db,
            USER,
            stored["report_id"],
            1,
            stored["fingerprint"],
            "Revisión general SINTÉTICA; no confirma fuentes ni fichas comerciales.",
        )
        assert acknowledged["human_acknowledgement"]
        capture = db.scalar(
            select(CatalogSnapshot).where(
                CatalogSnapshot.source == "ECOMM_APP_API_STAGE"
            )
        )
        pages = deepcopy(capture.payload)
        variant = deepcopy(pages[0]["items"][0]["variants"][0])
        variant.update(id=8900099, sku="PG18-NEW-99")
        pages[0]["items"][0]["variants"].append(variant)
        pages[0]["total"] = 2
        capture.payload = pages
        db.commit()
        report = preview_periodic_review(db, limit=1, page=2)
        assert report["total_variants"] == report["total_tasks"] == 2
        assert report["reason_counts"]["NEW_PRODUCT"] == 1
        assert (
            report["next_general_review_at"] == (NOW + timedelta(days=30)).isoformat()
        )
        assert report["schedule_due"] is False
        assert report["commercial_changes"] == report["facts_approved"] == 0
        # New unacknowledged report must not erase the prior sign-off.
        summary, _ = build_delivery_audit(db)
        save_monthly_report(
            db, USER, summary["preview_fingerprint"], "Operador sintético"
        )
        assert (
            preview_periodic_review(db)["next_general_review_at"]
            == report["next_general_review_at"]
        )


def test_disabled_schedule_keeps_real_exceptions_visible(database):
    with Session(database) as db:
        policy = review_policy(db)
        save_review_policy(
            db,
            USER,
            expected_version=0,
            settings={**policy["settings"], "enabled": False},
            reason="Desactivar únicamente el recordatorio periódico de prueba.",
        )
        report = preview_periodic_review(db)
        assert report["schedule_due"] is False
        assert report["reason_counts"]["PERIODIC_REVIEW_DUE"] == 0
        assert report["reason_counts"]["INCOMPLETE_FICHE"] == 1
        assert report["reason_counts"]["EVIDENCE_EXPIRED"] == 1
        assert db.scalar(select(EcommApiProductEdit)) is None
