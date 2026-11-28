"""Offline diagnostics use the saved catalogue; never grant commercial approval."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.database.models import CatalogSnapshot, EcommApiProductEdit
from app.services.documental.storage import Dossier, Document
import app.services.monthly_catalog_reports as monthly
import app.services.periodic_review_runner as runner
from test_documental_complete_draft_flow import prepare, IDENT
from test_documental_channel_readiness_guard import install_fake_source

NOW = datetime(2026, 12, 20, 12, tzinfo=timezone.utc)
CONFIG = SimpleNamespace(kiki_monthly_review_enabled=True, kiki_v2_enabled=True,
                         kiki_editorial_executor_enabled=True)


@pytest.fixture
def database(tmp_path, monkeypatch):
    import app.services.documental.research as research

    monkeypatch.setattr(monthly, "_now", lambda: NOW)
    monkeypatch.setattr(research, "get_settings", lambda: SimpleNamespace(kiki_admin_username="SYNTHETIC"))
    engine, _ = prepare(tmp_path)
    with Session(engine) as db:
        install_fake_source(db)
    yield engine
    engine.dispose()


def test_disabled_flags_never_even_open_a_database():
    def forbidden():
        raise AssertionError("Disabled runner opened database")

    for key in ("kiki_monthly_review_enabled", "kiki_v2_enabled", "kiki_editorial_executor_enabled"):
        config = SimpleNamespace(**{**vars(CONFIG), key: False})
        assert runner.PeriodicReviewRunner(forbidden, config=config).tick()["state"] == "DISABLED"


def test_requires_postgresql_and_is_hourly_throttled(database):
    clock = [10.0]
    service = runner.PeriodicReviewRunner(sessionmaker(database), config=CONFIG,
                                          monotonic=lambda: clock[0])
    assert service.tick()["state"] == "BLOCKED_REQUIRES_POSTGRESQL"
    clock[0] += 3599
    assert service.tick()["state"] == "THROTTLED"
    clock[0] += 1
    assert service.tick()["state"] == "BLOCKED_REQUIRES_POSTGRESQL"


def test_disabled_policy_never_creates_a_ledger_or_report(database):
    with Session(database) as db:
        policy = monthly.review_policy(db)
        monthly.save_review_policy(db, SimpleNamespace(id="SYNTHETIC"), expected_version=0,
            settings={**policy["settings"], "enabled": False},
            reason="Desactivar únicamente diagnósticos del ensayo local.")
        assert runner._run_locked(db, NOW)["state"] == "POLICY_DISABLED"
        assert not db.scalar(select(CatalogSnapshot).where(CatalogSnapshot.source == runner.SOURCE))


def test_system_cycle_persists_tasks_but_never_facts_fiches_or_ack(database):
    with Session(database) as db:
        facts = deepcopy(db.get(Dossier, IDENT).facts)
        doc = db.scalar(select(Document))
        document = (doc.version, doc.digest, deepcopy(doc.body), deepcopy(doc.history))
        result = runner._run_locked(db, NOW)
        assert result["state"] == "COMPLETED_DIAGNOSTIC"
        assert result["human_review_required"] is True
        receipt = monthly.monthly_report(db, result["report_id"])
        assert receipt["created_by"].startswith("SYSTEM_AUTOMATION")
        assert receipt["responsible"] == "Sistema · diagnóstico sin revisión humana"
        assert receipt["human_acknowledgement"] is None
        assert receipt["individual_fiches_approved"] == receipt["facts_approved"] == 0
        _, ledger = runner._load(db)
        assert len(ledger["tasks"]) == result["total_tasks"]
        assert ledger["tasks"][0]["ecomm_id"] == IDENT
        assert ledger["tasks"][0]["state"] == "HUMAN_REVIEW_REQUIRED"
        assert ledger["commercial_changes"] == ledger["facts_approved"] == 0
        assert ledger["human_acknowledgements_created"] == 0
        assert ledger["next_due_at"] == (NOW + timedelta(days=30)).isoformat()
        assert db.get(Dossier, IDENT).facts == facts
        assert (doc.version, doc.digest, doc.body, doc.history) == document
        assert db.scalar(select(EcommApiProductEdit)) is None
    # A new runner/process cannot repeat a completed cycle before its due date.
    with Session(database) as db:
        assert runner._run_locked(db, NOW + timedelta(hours=2))["state"] == "NOT_DUE"
        assert len(monthly.list_monthly_reports(db)["items"]) == 1


def test_crash_after_report_commit_resumes_checkpoint_without_generating_again(database, monkeypatch):
    original = runner._complete

    def interrupted(*args):
        raise RuntimeError("Simulated interruption after report commit")

    monkeypatch.setattr(runner, "_complete", interrupted)
    with Session(database) as db:
        with pytest.raises(RuntimeError, match="Simulated interruption"):
            runner._run_locked(db, NOW)
        _, before = runner._load(db)
        assert before["state"] == "ERROR_REQUIRES_RETRY"
        assert len(monthly.list_monthly_reports(db)["items"]) == 1
    monkeypatch.setattr(runner, "_complete", original)

    def forbidden(*args, **kwargs):
        raise AssertionError("Recovery regenerated a saved diagnostic")

    monkeypatch.setattr(runner, "save_system_monthly_report", forbidden)
    monkeypatch.setattr(runner, "preview_periodic_review", forbidden)
    with Session(database) as db:
        recovered = runner._run_locked(db, NOW + timedelta(hours=1))
        assert recovered["cycle_id"] == before["intent"]["cycle_id"]
        assert recovered["state"] == "COMPLETED_DIAGNOSTIC"
        assert len(monthly.list_monthly_reports(db)["items"]) == 1
        assert monthly.monthly_report(db, recovered["report_id"])["human_acknowledgement"] is None


def test_failure_is_generic_and_retry_is_persistent_hourly(database, monkeypatch):
    def failed(*args):
        raise ValueError("sensitive-string-never-store")

    monkeypatch.setattr(runner, "save_system_monthly_report", failed)
    with Session(database) as db:
        with pytest.raises(ValueError, match="sensitive-string"):
            runner._run_locked(db, NOW)
    with Session(database) as db:
        _, ledger = runner._load(db)
        assert "sensitive-string" not in str(ledger)
        assert runner._run_locked(db, NOW + timedelta(minutes=59))["state"] == "THROTTLED"
        assert monthly.list_monthly_reports(db)["items"] == []


def test_policy_interval_change_applies_without_extending_editorial_signoff(database):
    with Session(database) as db:
        runner._run_locked(db, NOW)
        policy = monthly.review_policy(db)
        monthly.save_review_policy(db, SimpleNamespace(id="SYNTHETIC"), expected_version=0,
            settings={**policy["settings"], "interval_days": 10},
            reason="Acortar la revisión diagnóstica sin aprobar ninguna ficha.")
        state = runner._run_locked(db, NOW + timedelta(days=2))
        assert state["next_due_at"] == (NOW + timedelta(days=10)).isoformat()
        assert monthly.review_policy(db)["editorial_signoff_max_days"] == 30


def test_ledger_integrity_and_task_limit_fail_closed(database, monkeypatch):
    original = runner.preview_periodic_review

    def invalid(*args, **kwargs):
        result = original(*args, **kwargs)
        return {**result, "total_tasks": 2}

    monkeypatch.setattr(runner, "preview_periodic_review", invalid)
    with Session(database) as db:
        with pytest.raises(ValueError, match="no es completo"):
            runner._run_locked(db, NOW)
        assert db.scalar(select(CatalogSnapshot).where(CatalogSnapshot.source == runner.SOURCE)) is None
    monkeypatch.setattr(runner, "preview_periodic_review", original)
    with Session(database) as db:
        runner._run_locked(db, NOW)
        row = db.scalar(select(CatalogSnapshot).where(CatalogSnapshot.source == runner.SOURCE))
        payload = deepcopy(row.payload)
        payload[0]["next_due_at"] = (NOW - timedelta(days=1)).isoformat()
        row.payload = payload
        db.commit()
    with Session(database) as db:
        with pytest.raises(ValueError, match="integridad"):
            runner._run_locked(db, NOW + timedelta(hours=1))


def test_exact_original_reconfirmation_updates_evidence_age_only(database):
    with Session(database) as db:
        initial = monthly.preview_periodic_review(db)
        assert "EVIDENCE_EXPIRED" in initial["items"][0]["reasons"]
        dossier = db.get(Dossier, IDENT)
        doc = db.scalar(select(Document))
        original = (doc.version, doc.digest, deepcopy(doc.body))
        facts = deepcopy(dossier.facts)
        event = {"action": "PROVENANCE_RECONFIRMED", "at": NOW.isoformat(),
                 "actor": "SYNTHETIC-HUMAN-REVIEWER", "detail": {
                     "document_id": doc.id, "document_version": doc.version,
                     "document_hash": doc.digest, "decision": "REVIEWED"}}
        dossier.history = [*dossier.history, event]
        dossier.version += 1
        db.commit()
        current = monthly.preview_periodic_review(db)
        assert "EVIDENCE_EXPIRED" not in current["items"][0]["reasons"]
        assert current["last_general_review_at"] is None
        assert current["items"][0]["state"] == "HUMAN_REVIEW_REQUIRED"
        assert current["items"][0]["editorial_review_reason"] == initial["items"][0]["editorial_review_reason"]
        assert dossier.facts == facts
        assert (doc.version, doc.digest, doc.body) == original
        # An event for a different hash/version cannot extend this original.
        dossier.history = [{**event, "detail": {**event["detail"], "document_hash": "0" * 64}}]
        dossier.version += 1
        db.commit()
        assert "EVIDENCE_EXPIRED" in monthly.preview_periodic_review(db)["items"][0]["reasons"]


def test_diagnostic_failure_cannot_stop_existing_editorial_work(monkeypatch, caplog):
    from app.services.editorial_batches.executor import Executor

    def failed(self):
        raise RuntimeError("sensitive-details-never-log")

    monkeypatch.setattr(runner.PeriodicReviewRunner, "tick", failed)
    events = []
    worker = Executor(lambda: None)
    monkeypatch.setattr(worker, "tick", lambda: events.append("EDITORIAL_TICK") or False)

    class Stop:
        stopped = False

        def is_set(self):
            return self.stopped

        def wait(self, delay):
            self.stopped = True

    worker.run(Stop())
    assert events == ["EDITORIAL_TICK"]
    assert "sensitive-details" not in caplog.text
