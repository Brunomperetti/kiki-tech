"""Recoverable dated system audits and separate human general-review receipts.

Uses the existing snapshot store for immutable reports, never as a replacement
commercial catalogue. Neither generating nor acknowledging a report approves
facts, media, taxonomy or individual fiches, or changes their review clocks.
"""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.database.models import CatalogSnapshot
from app.services.contractual_delivery_audit_service import (
    build_delivery_audit,
    export_delivery_csv,
)
from app.services.documental.storage import digest
from app.services.commercial_channel_export_service import _check_fingerprint

PREFIX = "KIKI_MONTHLY:"
MAX_BYTES = 10 * 1024 * 1024


def _now():
    return datetime.now(timezone.utc)


def _source(report_id):
    if (
        not isinstance(report_id, str)
        or len(report_id) != 17
        or report_id[6:7] != ":"
        or not report_id[:6].isdigit()
        or any(ch not in "0123456789abcdef" for ch in report_id[7:])
    ):
        raise ValueError("Identificador de informe inválido.")
    return PREFIX + report_id


def _actor(session):
    if session is None or not getattr(session, "id", None):
        raise ValueError("El informe requiere una sesión autenticada.")
    return "Operador autenticado · sesión " + str(session.id)


def _validate_text(value, label, minimum, maximum):
    if (
        not isinstance(value, str)
        or not minimum <= len(value.strip()) <= maximum
        or any(ord(ch) < 32 for ch in value)
    ):
        raise ValueError(
            f"{label}: texto requerido de {minimum} a {maximum} caracteres."
        )
    return value.strip()


def _view(record):
    value = deepcopy(record.payload[0])
    confirmation = value.get("human_acknowledgement")
    when = confirmation["at"] if confirmation else None
    next_due = datetime.fromisoformat(when) + timedelta(days=30) if when else None
    value["review_status"] = (
        "AWAITING_HUMAN_REVIEW"
        if not next_due
        else "OVERDUE"
        if _now() >= next_due
        else "GENERAL_REVIEW_WITHIN_30_DAYS"
    )
    value["next_general_review_at"] = next_due.isoformat() if next_due else None
    value["individual_fiches_approved"] = 0
    value["facts_approved"] = 0
    value["external_writes_enabled"] = False
    value["catalog_state_currently_revalidated"] = False
    value["report_scope"] = "IMMUTABLE_ARCHIVED_CAPTURE_AND_VERSIONS"
    return value


def save_monthly_report(db, session, expected_fingerprint, responsible):
    actor = _actor(session)
    responsible = _validate_text(responsible, "Responsable", 2, 120)
    summary, rows = build_delivery_audit(db)
    _check_fingerprint(expected_fingerprint, summary["preview_fingerprint"])
    month = _now().strftime("%Y%m")
    # 40 bits of the hash fit source's existing VARCHAR(30). Full fingerprint
    # is always compared below; a prefix collision blocks instead of replacing.
    report_id = month + ":" + expected_fingerprint[:10]
    source = PREFIX + report_id
    existing = db.scalar(
        select(CatalogSnapshot)
        .where(CatalogSnapshot.source == source)
        .with_for_update()
    )
    if existing:
        stored = existing.payload[0]
        if stored.get("fingerprint") != expected_fingerprint:
            raise ValueError(
                "Colisión de identificador de informe; no se reemplazó el original."
            )
        return _view(existing)
    now = _now().isoformat()
    body = {
        "report_id": report_id,
        "revision": 1,
        "fingerprint": expected_fingerprint,
        "report_kind": "SYSTEM_CATALOG_AUDIT_NOT_SOURCE_APPROVAL",
        "created_at": now,
        "created_by": actor,
        "responsible": responsible,
        "summary": summary,
        "rows": rows,
        "content_hash": digest({"summary": summary, "rows": rows}),
        "human_acknowledgement": None,
        "history": [{"action": "SYSTEM_REPORT_SAVED", "at": now, "actor": actor}],
    }
    if len(json.dumps(body, ensure_ascii=False).encode()) > MAX_BYTES:
        raise ValueError("El informe supera 10 MiB; no se guardó parcialmente.")
    record = CatalogSnapshot(source=source, payload=[body])
    db.add(record)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ValueError("Otro operador guardó el informe; recargá la lista.") from None
    return _view(record)


def monthly_report(db, report_id):
    record = db.scalar(
        select(CatalogSnapshot).where(CatalogSnapshot.source == _source(report_id))
    )
    if record is None:
        raise ValueError("Informe mensual no encontrado.")
    value = _view(record)
    if value.get("content_hash") != digest(
        {"summary": value["summary"], "rows": value["rows"]}
    ):
        raise ValueError("El informe archivado no conserva su integridad.")
    return value


def download_archived_report(db, report_id, expected_fingerprint):
    report = monthly_report(db, report_id)
    _check_fingerprint(expected_fingerprint, report["fingerprint"])
    return export_delivery_csv(report["rows"]).encode("utf-8"), report


def acknowledge_monthly_report(
    db, session, report_id, expected_revision, expected_fingerprint, reason
):
    actor = _actor(session)
    reason = _validate_text(reason, "Motivo de revisión general", 25, 600)
    record = db.scalar(
        select(CatalogSnapshot)
        .where(CatalogSnapshot.source == _source(report_id))
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if record is None:
        raise ValueError("Informe mensual no encontrado.")
    body = deepcopy(record.payload[0])
    if body["revision"] != expected_revision:
        raise ValueError("Otro operador revisó el informe; recargá su versión.")
    _check_fingerprint(expected_fingerprint, body["fingerprint"])
    current, _ = build_delivery_audit(db)
    _check_fingerprint(expected_fingerprint, current["preview_fingerprint"])
    if body.get("content_hash") != digest(
        {"summary": body["summary"], "rows": body["rows"]}
    ):
        raise ValueError("El informe archivado no conserva su integridad.")
    if body.get("human_acknowledgement"):
        raise ValueError(
            "El informe ya tiene una confirmación humana; no se reemplaza."
        )
    now = _now().isoformat()
    body["revision"] += 1
    body["human_acknowledgement"] = {
        "at": now,
        "actor": actor,
        "reason": reason,
        "responsible": body["responsible"],
        "scope": "GENERAL_REPORT_ONLY_NOT_INDIVIDUAL_SOURCE_OR_FICHE_APPROVAL",
    }
    body["history"].append(
        {
            "action": "GENERAL_REVIEW_ACKNOWLEDGED",
            "at": now,
            "actor": actor,
            "reason": reason,
        }
    )
    record.payload = [body]
    db.commit()
    return _view(record)


def list_monthly_reports(db, limit=12, page=1):
    if not 1 <= limit <= 12 or not 1 <= page <= 10000:
        raise ValueError("Límite de informes inválido.")
    # Select only compact metadata; originals and whole catalogue rows do not
    # cross the DB boundary when opening the history list.
    rows = db.execute(
        select(
            CatalogSnapshot.payload[0]["report_id"].as_string(),
            CatalogSnapshot.payload[0]["revision"].as_integer(),
            CatalogSnapshot.payload[0]["created_at"].as_string(),
            CatalogSnapshot.payload[0]["responsible"].as_string(),
            CatalogSnapshot.payload[0]["summary"]["total"].as_integer(),
            CatalogSnapshot.payload[0]["human_acknowledgement"],
        )
        .where(CatalogSnapshot.source.startswith(PREFIX))
        .order_by(CatalogSnapshot.id.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    return {
        "items": [
            {
                "report_id": r[0],
                "revision": r[1],
                "created_at": r[2],
                "responsible": r[3],
                "total": r[4],
                "human_acknowledgement": r[5],
            }
            for r in rows
        ],
        "limit": limit,
        "page": page,
        "external_writes_enabled": False,
    }
