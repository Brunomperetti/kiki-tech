"""Recoverable dated system audits and separate human general-review receipts.

Uses the existing snapshot store for immutable reports, never as a replacement
commercial catalogue. Neither generating nor acknowledging a report approves
facts, media, taxonomy or individual fiches, or changes their review clocks.
"""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json

from sqlalchemy import select, text
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
    return _save_monthly_report(db, expected_fingerprint, responsible, actor)


def save_system_monthly_report(db, expected_fingerprint):
    """Diagnostic receipt only: no invented user, sign-off or approval."""
    return _save_monthly_report(
        db, expected_fingerprint,
        "Sistema · diagnóstico sin revisión humana",
        "SYSTEM_AUTOMATION · diagnóstico de capturas archivadas",
    )


def _save_monthly_report(db, expected_fingerprint, responsible, actor):
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


# Scheduling is independent from the immutable reports and the established
# 30-day individual sign-off. A longer audit interval cannot extend approval.
POLICY_SOURCE = "KIKI_REVIEW_POLICY"
DEFAULT_REVIEW_POLICY = {
    "enabled": True, "interval_days": 30, "evidence_max_age_days": 30,
    "soon_days": 7,
}
TASK_LABELS = {
    "NEW_PRODUCT": "Producto incorporado después del último informe",
    "UNREVIEWED_PRODUCT": "Producto sin revisión general registrada",
    "INCOMPLETE_FICHE": "Completar la ficha comercial",
    "SOURCE_CHANGED": "Revisar hechos cuyo documento cambió",
    "EVIDENCE_REVOKED": "Revisar evidencia revocada o rechazada",
    "EVIDENCE_EXPIRED": "Revalidar la antigüedad de la evidencia",
    "EVIDENCE_DATE_UNKNOWN": "Comprobar fecha de revisión de la fuente",
    "EDITORIAL_REVIEW_DUE": "Revisar la ficha según su aprobación editorial",
    "PERIODIC_REVIEW_DUE": "Realizar revisión general programada",
}


def review_policy(db):
    record = db.scalar(select(CatalogSnapshot).where(CatalogSnapshot.source == POLICY_SOURCE))
    if record is None:
        return {"version": 0, "settings": deepcopy(DEFAULT_REVIEW_POLICY), "history": [],
                "fingerprint": digest(DEFAULT_REVIEW_POLICY), "external_writes_enabled": False,
                "editorial_signoff_max_days": 30, "background_worker_enabled": False}
    body = deepcopy(record.payload[0])
    if body.get("fingerprint") != digest({"version": body["version"], "settings": body["settings"]}):
        raise ValueError("La política de revisión no conserva su integridad.")
    return {**body, "external_writes_enabled": False, "editorial_signoff_max_days": 30,
            "background_worker_enabled": False}


def save_review_policy(db, session, *, expected_version, settings, reason):
    from app.services.documental.storage import Control

    actor = _actor(session)
    reason = _validate_text(reason, "Motivo", 20, 600)
    if (type(expected_version) is not int or expected_version < 0
            or not isinstance(settings, dict) or set(settings) != set(DEFAULT_REVIEW_POLICY)
            or type(settings["enabled"]) is not bool
            or any(type(settings[key]) is not int for key in ("interval_days", "evidence_max_age_days", "soon_days"))
            or not 1 <= settings["interval_days"] <= 30
            or not 1 <= settings["evidence_max_age_days"] <= 365
            or not 0 <= settings["soon_days"] <= 30):
        raise ValueError("Política inválida: revisión cada 1 a 30 días, vigencia documental de 1 a 365 días y aviso de 0 a 30 días.")
    if db.scalar(select(Control).where(Control.id == 1).with_for_update()) is None:
        raise ValueError("Falta el control documental; no se guardó la programación.")
    record = db.scalar(select(CatalogSnapshot).where(CatalogSnapshot.source == POLICY_SOURCE)
                       .with_for_update().execution_options(populate_existing=True))
    current = review_policy(db)
    if current["version"] != expected_version:
        raise ValueError("Otro operador cambió la programación; recargá su versión.")
    body = {"version": expected_version + 1, "settings": deepcopy(settings)}
    body["fingerprint"] = digest(body)
    body["history"] = [*current["history"], {"at": _now().isoformat(), "actor": actor,
        "reason": reason, "settings": deepcopy(settings), "version": body["version"]}]
    if len(json.dumps(body, ensure_ascii=False).encode()) > MAX_BYTES:
        raise ValueError("El historial de programación supera el límite; no se guardó parcialmente.")
    if record is None:
        record = CatalogSnapshot(source=POLICY_SOURCE, payload=[body])
        db.add(record)
    else:
        record.payload = [body]
    db.commit()
    return review_policy(db)


def _instant(value):
    if not isinstance(value, str):
        return None
    try:
        result = datetime.fromisoformat(value)
        return result.astimezone(timezone.utc) if result.tzinfo is not None else None
    except (ValueError, OverflowError):
        return None


def _reconfirmed_dates(db):
    """Project only exact, current-original reconfirmation receipts, not originals."""
    if db.get_bind().dialect.name == "postgresql":
        query = """
            SELECT d.ecomm_id, e.value->'detail'->>'document_id',
                   e.value->'detail'->>'document_version',
                   e.value->'detail'->>'document_hash', MAX(e.value->>'at')
            FROM kiki_evidence_dossiers d,
                 LATERAL json_array_elements(d.history) e(value)
            WHERE e.value->>'action' = 'PROVENANCE_RECONFIRMED'
              AND e.value->'detail'->>'decision' = 'REVIEWED'
              AND COALESCE(e.value->>'actor', '') <> ''
            GROUP BY d.ecomm_id, e.value->'detail'->>'document_id',
                     e.value->'detail'->>'document_version',
                     e.value->'detail'->>'document_hash'
            LIMIT 10001
        """
    elif db.get_bind().dialect.name == "sqlite":
        query = """
            SELECT d.ecomm_id, json_extract(e.value, '$.detail.document_id'),
                   CAST(json_extract(e.value, '$.detail.document_version') AS TEXT),
                   json_extract(e.value, '$.detail.document_hash'),
                   MAX(json_extract(e.value, '$.at'))
            FROM kiki_evidence_dossiers d, json_each(d.history) e
            WHERE json_extract(e.value, '$.action') = 'PROVENANCE_RECONFIRMED'
              AND json_extract(e.value, '$.detail.decision') = 'REVIEWED'
              AND COALESCE(json_extract(e.value, '$.actor'), '') <> ''
            GROUP BY d.ecomm_id, json_extract(e.value, '$.detail.document_id'),
                     json_extract(e.value, '$.detail.document_version'),
                     json_extract(e.value, '$.detail.document_hash')
            LIMIT 10001
        """
    else:
        return {}
    rows = db.execute(text(query)).all()
    if len(rows) > 10000:
        raise ValueError("Las reconfirmaciones superan el límite del informe periódico.")
    return {(ident, doc, str(version), checksum): _instant(when)
            for ident, doc, version, checksum, when in rows}


def preview_periodic_review(db, *, page=1, limit=20, _collect_all=False):
    """Actionable current tasks, not approvals or silent commercial mutations.

    Uses the complete captured API catalogue and existing bulk audit. Source
    changes mean archived document-version changes, never an unperformed web
    check. The same bounded task index is reused by the opt-in existing worker.
    """
    from collections import Counter, defaultdict
    from app.services.documental.storage import Document, Dossier

    if type(page) is not int or type(limit) is not int or not 1 <= page <= 10000 or not 1 <= limit <= 100:
        raise ValueError("Paginación de revisión inválida.")
    policy = review_policy(db)
    settings = policy["settings"]
    summary, rows = build_delivery_audit(db)
    latest = db.scalar(select(CatalogSnapshot.payload[0]).where(CatalogSnapshot.source.startswith(PREFIX))
                       .order_by(CatalogSnapshot.id.desc()).limit(1))
    baseline_ids = {row["ecomm_id"] for row in (latest or {}).get("rows", [])}
    # Saving a fresh, unacknowledged audit must not erase an earlier general
    # sign-off or postpone its deadline. Read compact receipt metadata only.
    last_ack_at = db.scalar(select(CatalogSnapshot.payload[0]["human_acknowledgement"]["at"].as_string())
        .where(CatalogSnapshot.source.startswith(PREFIX),
               CatalogSnapshot.payload[0]["human_acknowledgement"]["at"].as_string().is_not(None))
        .order_by(CatalogSnapshot.payload[0]["human_acknowledgement"]["at"].as_string().desc()).limit(1))
    last_review = _instant(last_ack_at)
    next_review = last_review + timedelta(days=settings["interval_days"]) if last_review else None
    now = _now()
    due = bool(settings["enabled"] and (next_review is None or now >= next_review))
    soon = bool(settings["enabled"] and next_review and now < next_review <= now + timedelta(days=settings["soon_days"]))
    documents, per_variant = {}, defaultdict(list)
    reconfirmed = _reconfirmed_dates(db)
    # Compact SQL projection: original bytes, all quoted text and permissions
    # never cross the DB boundary for this catalogue-level task index.
    for ident, version, checksum, variant, reviewed, consulted, review_state in db.execute(select(
        Document.id, Document.version, Document.digest,
        Document.body["associated_ecomm_id"].as_string(),
        Document.body["source"]["reviewed_at"].as_string(),
        Document.body["source"]["declared_consulted_at"].as_string(),
        Document.body["source"]["review_state"].as_string(),
    )):
        when = _instant(reviewed) or _instant(consulted)
        reconfirmation = reconfirmed.get((variant, ident, str(version), checksum))
        if review_state == "REVIEWED" and reconfirmation is not None:
            when = max(when, reconfirmation) if when is not None else reconfirmation
        documents[ident] = (version, checksum, variant)
        if variant:
            per_variant[variant].append(when)
    signals = defaultdict(set)
    for ident, facts in db.execute(select(Dossier.ecomm_id, Dossier.facts)):
        for fact in facts or []:
            if not isinstance(fact, dict):
                continue
            state = fact.get("state")
            current = documents.get(fact.get("document_id"))
            if state in {"REVOKED", "REJECTED"}:
                signals[ident].add("EVIDENCE_REVOKED")
            elif state == "STALE" or (state == "APPROVED" and (
                current is None or current != (fact.get("document_version"), fact.get("document_hash"), ident)
            )):
                signals[ident].add("SOURCE_CHANGED")
    tasks, counts = [], Counter()
    for row in rows:
        ident = row["ecomm_id"]
        reasons = set(signals[ident])
        if not latest:
            reasons.add("UNREVIEWED_PRODUCT")
        elif ident not in baseline_ids:
            reasons.add("NEW_PRODUCT")
        if not row["fields_complete"]:
            reasons.add("INCOMPLETE_FICHE")
        if row["monthly_review_due"]:
            reasons.add("EDITORIAL_REVIEW_DUE")
        if due:
            reasons.add("PERIODIC_REVIEW_DUE")
        dates = per_variant.get(ident, [])
        if any(when is None for when in dates):
            reasons.add("EVIDENCE_DATE_UNKNOWN")
        if any(when is not None and now >= when + timedelta(days=settings["evidence_max_age_days"]) for when in dates):
            reasons.add("EVIDENCE_EXPIRED")
        if not reasons:
            continue
        ordered = [key for key in TASK_LABELS if key in reasons]
        counts.update(ordered)
        tasks.append({"task_id": digest({"ecomm_id": ident, "reasons": ordered,
            "audit": summary["preview_fingerprint"], "policy": policy["fingerprint"]})[:24],
            "ecomm_id": ident, "sku": row["sku"], "name": row["name"],
            "presentation": row["presentation"], "state": "HUMAN_REVIEW_REQUIRED",
            "reasons": ordered, "actions": [TASK_LABELS[key] for key in ordered],
            "editorial_review_reason": row["review_reason"], "automatic_changes": 0})
    return {"schema_version": "kiki-periodic-review-v1", "policy": policy,
        "total_variants": len(rows), "total_tasks": len(tasks), "page": page, "limit": limit,
        "items": tasks if _collect_all else tasks[(page-1)*limit:page*limit],
        "audit_fingerprint": summary["preview_fingerprint"],
        "reason_counts": {key: counts[key] for key in TASK_LABELS},
        "last_general_review_at": last_review.isoformat() if last_review else None,
        "next_general_review_at": next_review.isoformat() if next_review else None,
        "schedule_due": due, "schedule_soon": soon,
        "baseline_report_id": (latest or {}).get("report_id"),
        "fingerprint": digest({"audit": summary["preview_fingerprint"], "policy": policy["fingerprint"],
                               "baseline": (latest or {}).get("report_id"), "tasks": tasks}),
        "execution": "ON_REQUEST_REVIEW_TASKS_NO_BACKGROUND_WORKER",
        "source_changes_scope": "ARCHIVED_DOCUMENT_VERSIONS_NOT_LIVE_WEB",
        "external_writes_enabled": False, "commercial_changes": 0, "facts_approved": 0}
