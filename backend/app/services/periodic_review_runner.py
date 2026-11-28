"""Opt-in diagnostic ticks inside the existing editorial executor.

Only archived captures/documents are inspected. A PostgreSQL session advisory
mutex survives the existing report service's commits; no provider, editor,
fact, sign-off or user-session write is performed. The existing snapshot
store retains the bounded task generation and restart checkpoint.
"""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import time

from sqlalchemy import LargeBinary, Text, cast, func, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database.models import CatalogSnapshot
from app.services.documental.storage import digest
from app.services.monthly_catalog_reports import (
    MAX_BYTES,
    monthly_report,
    preview_periodic_review,
    review_policy,
    save_system_monthly_report,
)

SOURCE = "KIKI_REVIEW_RUNNER"
LOCK_KEY = 682112941720061
MIN_TICK_SECONDS = 3600
MAX_TASKS = 10000
MAX_HISTORY = 12


def _now():
    return datetime.now(timezone.utc)


def _instant(value):
    if not isinstance(value, str):
        return None
    try:
        when = datetime.fromisoformat(value)
        return when.astimezone(timezone.utc) if when.tzinfo else None
    except (ValueError, OverflowError):
        return None


def enabled(config):
    # Monthly diagnostics cannot start a second worker or enable batch writes.
    return bool(
        getattr(config, "kiki_monthly_review_enabled", False)
        and getattr(config, "kiki_v2_enabled", False)
        and getattr(config, "kiki_editorial_executor_enabled", False)
    )


def _load(db):
    size = (
        func.octet_length(cast(CatalogSnapshot.payload, Text))
        if db.get_bind().dialect.name == "postgresql"
        else func.length(cast(cast(CatalogSnapshot.payload, Text), LargeBinary))
    )
    metadata = db.execute(select(CatalogSnapshot.id, size).where(
        CatalogSnapshot.source == SOURCE
    )).first()
    if metadata is None:
        return None, {"schema_version": "kiki-periodic-runner-v1", "history": []}
    if metadata[1] is None or metadata[1] > MAX_BYTES:
        raise ValueError("El registro periódico supera el límite de lectura.")
    row = db.get(CatalogSnapshot, metadata[0])
    if len(json.dumps(row.payload, ensure_ascii=False).encode()) > MAX_BYTES:
        raise ValueError("El registro periódico supera el límite de lectura.")
    value = deepcopy(row.payload[0])
    checksum = value.pop("integrity", None)
    if checksum != digest(value) or value.get("schema_version") != "kiki-periodic-runner-v1":
        raise ValueError("El registro periódico no conserva su integridad.")
    return row, value


def _store(db, row, value):
    value = deepcopy(value)
    value["integrity"] = digest(value)
    if len(json.dumps([value], ensure_ascii=False).encode()) > MAX_BYTES:
        raise ValueError("Las tareas periódicas superan 10 MiB; no se guardaron parcialmente.")
    if row is None:
        row = CatalogSnapshot(source=SOURCE, payload=[value])
        db.add(row)
    else:
        row.payload = [value]
    db.commit()
    return row


def _complete(db, row, state, report, now):
    state = deepcopy(state)
    intent = state["intent"]
    finished = {
        "cycle_id": intent["cycle_id"], "report_id": report["report_id"],
        "fingerprint": intent["audit_fingerprint"],
        "policy_fingerprint": intent["policy_fingerprint"],
        "started_at": intent["started_at"], "completed_at": now.isoformat(),
        "total_tasks": len(intent["tasks"]), "state": "COMPLETED_DIAGNOSTIC",
        "human_review_required": True,
    }
    state.update(
        state="COMPLETED_DIAGNOSTIC", last_run=finished,
        tasks=intent["tasks"], task_reason_counts=intent["reason_counts"],
        next_due_at=(now + timedelta(days=intent["interval_days"])).isoformat(),
        intent=None, error=None,
        history=[*state.get("history", []), finished][-MAX_HISTORY:],
        external_writes_enabled=False, commercial_changes=0, facts_approved=0,
        human_acknowledgements_created=0,
        source_changes_scope="ARCHIVED_DOCUMENT_VERSIONS_NOT_LIVE_WEB",
    )
    _store(db, row, state)
    return {"state": "COMPLETED_DIAGNOSTIC", **finished}


def _run_locked(db, now):
    """Caller must hold the PostgreSQL session mutex for every commit here."""
    policy = review_policy(db)
    if not policy["settings"]["enabled"]:
        return {"state": "POLICY_DISABLED"}
    row, state = _load(db)
    if state.get("last_run"):
        last_completed = _instant(state["last_run"].get("completed_at"))
        if last_completed is None:
            raise ValueError("El ciclo periódico no conserva su fecha.")
        state["next_due_at"] = (last_completed + timedelta(
            days=policy["settings"]["interval_days"]
        )).isoformat()
    next_attempt = _instant(state.get("next_attempt_at"))
    if next_attempt and now < next_attempt:
        return {"state": "THROTTLED", "next_attempt_at": next_attempt.isoformat()}
    next_due = _instant(state.get("next_due_at"))
    if next_due and now < next_due:
        return {"state": "NOT_DUE", "next_due_at": next_due.isoformat()}
    state["next_attempt_at"] = (now + timedelta(seconds=MIN_TICK_SECONDS)).isoformat()
    # A crash after the existing report commit must not regenerate the same
    # work. Complete its archived checkpoint first, even if today's capture
    # changed. This result is explicitly historical and not human sign-off.
    intent = state.get("intent")
    if intent:
        saved = db.scalar(select(CatalogSnapshot).where(
            CatalogSnapshot.source == "KIKI_MONTHLY:" + intent["report_id"]
        ))
        if saved is not None:
            report = monthly_report(db, intent["report_id"])
            if report["fingerprint"] != intent["audit_fingerprint"]:
                raise ValueError("El informe del ciclo no corresponde a su checkpoint.")
            return _complete(db, row, state, report, now)
    # One complete in-memory task index, bounded by the reused audit limit.
    task_index = preview_periodic_review(db, _collect_all=True)
    tasks = task_index["items"]
    if len(tasks) > MAX_TASKS or len(tasks) != task_index["total_tasks"]:
        raise ValueError("El índice periódico no es completo o supera 10.000 tareas.")
    if task_index["policy"]["fingerprint"] != policy["fingerprint"]:
        raise ValueError("La programación cambió durante la revisión; no se ejecutó.")
    fingerprint = task_index["audit_fingerprint"]
    cycle_id = (intent or {}).get("cycle_id") or digest({
        "due_at": state.get("next_due_at"),
        "previous_cycle": state.get("last_run", {}).get("cycle_id"),
        "initial_policy": policy["fingerprint"],
    })
    state.update(state="RUNNING_DIAGNOSTIC", intent={
        "cycle_id": cycle_id, "started_at": now.isoformat(),
        "audit_fingerprint": fingerprint,
        "task_fingerprint": task_index["fingerprint"],
        "policy_fingerprint": policy["fingerprint"],
        "interval_days": policy["settings"]["interval_days"],
        "report_id": now.strftime("%Y%m") + ":" + fingerprint[:10],
        "tasks": tasks, "reason_counts": task_index["reason_counts"],
    }, created_by="SYSTEM_AUTOMATION",
        responsible="Sistema · diagnóstico sin revisión humana",
        external_writes_enabled=False, commercial_changes=0, facts_approved=0,
        human_acknowledgements_created=0)
    row = _store(db, row, state)
    try:
        if review_policy(db)["fingerprint"] != policy["fingerprint"]:
            raise ValueError("La programación cambió antes de guardar el informe.")
        report = save_system_monthly_report(db, fingerprint)
        return _complete(db, row, state, report, now)
    except Exception:
        db.rollback()
        # Do not persist exception text: connection strings/provider payloads
        # are never part of scheduler logs or receipts.
        state.update(state="ERROR_REQUIRES_RETRY", error="DIAGNOSTIC_NOT_COMPLETED")
        _store(db, row, state)
        raise


class PeriodicReviewRunner:
    def __init__(self, factory, *, config=None, clock=None, monotonic=None):
        self.factory = factory
        self.config = config if config is not None else get_settings()
        self.clock = clock or _now
        self.monotonic = monotonic or time.monotonic
        self._next_tick = 0.0

    def tick(self):
        if not enabled(self.config):
            return {"state": "DISABLED"}
        current = self.monotonic()
        if current < self._next_tick:
            return {"state": "THROTTLED"}
        self._next_tick = current + MIN_TICK_SECONDS
        with self.factory() as probe:
            engine = probe.get_bind()
        if engine.dialect.name != "postgresql":
            return {"state": "BLOCKED_REQUIRES_POSTGRESQL"}
        # Use one dedicated physical connection through all report commits.
        # Session-level lock is released explicitly and never returned pooled.
        with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
            locked = connection.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": LOCK_KEY})
            connection.commit()
            if not locked:
                return {"state": "BUSY"}
            try:
                with Session(bind=connection, expire_on_commit=False) as db:
                    return _run_locked(db, self.clock())
            finally:
                connection.rollback()
                connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": LOCK_KEY})
                connection.commit()
