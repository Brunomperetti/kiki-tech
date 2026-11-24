"""Operator-controlled, durable and resumable manufacturer intake queue.

A single item is claimed per manual step. Network calls happen outside the
row lock, while item ownership and an expiry are persisted in PostgreSQL.
The existing guarded documentary importer rechecks the source sitemap,
the current Ecomm identity, the exact URL and document CAS. Never publishes.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.services.documental.storage import Document, Dossier, Control, digest
from app.integrations.ecomm_app.api_catalog_browser import valid_variant_id
from app.services.editorial_batches.context import sources
from .manufacturer_batch_intake import _identity, _eligible_unit, capture_selected, preflight
from .explicit_url_intake import import_explicit_url, _existing_documents, _reject_repeated
from .source_intake_pipeline import (
    PIPELINE_SCHEMA, PipelineError, identity_pin, check_identity, document_for_item,
    receipt_for_document, extract_candidates, safe_failure, repin_reviewed_metadata,
)
from .sitemap_discovery import preview_candidates
from .source_fetch import allowed_hosts, target
from .source_intake_storage import SourceIntakeJob

MAX_ITEMS = 20
MAX_STEPS_PER_REQUEST = 1
CLAIM_TTL = timedelta(minutes=10)
MAX_ATTEMPTS = 3
MAX_HISTORY_EVENTS = 512
DONE = frozenset({"IMPORTED", "ALREADY_PRESENT", "CANCELLED"})
VALID = frozenset({"PENDING", "RUNNING", "BLOCKED", *DONE})


def now():
    return datetime.now(timezone.utc)


def _present(db, ident, url):
    return db.scalar(
        select(Document.id)
        .where(Document.body["associated_ecomm_id"].as_string() == ident)
        .where(Document.body["source"]["reference_url"].as_string() == url)
        .limit(1)
    )


def _claim_expired(row, instant):
    """A missing or invalid lease cannot authorize preemption of a worker."""
    try:
        deadline = datetime.fromisoformat(row.get("claim_until") or "")
    except (TypeError, ValueError):
        return False
    return deadline.tzinfo is not None and instant >= deadline


def _processing(item):
    return {
        "schema_version": 1, "phase": "PENDING", "candidate_count": 0,
        "candidate_ids": [], "document_id": None, "document_sha256": None,
        "document_digest": None, "document_version": None,
        "identity_digest": item.get("identity_digest"), "dossier_version": None,
        "error_code": None, "retryable": False, "download_attempts": 0,
        "http_requests_reported": 0 if item.get("identity_schema") == 2 else None,
        "request_measurement_pending": False, "source_bytes": None,
        "started_at": None, "finished_at": None, "elapsed_ms": None,
        **deepcopy(item.get("processing") or {}),
    }


def _public_state(item):
    phase = (item.get("processing") or {}).get("phase")
    if phase == "FAILED":
        return "FAILED"
    if phase == "BLOCKED" or item["state"] in {"BLOCKED", "CANCELLED"}:
        return "BLOCKED"
    return "REVIEW_REQUIRED" if item["state"] in {"IMPORTED", "ALREADY_PRESENT"} else "RESEARCH"


def _summary(job, document_versions=None):
    instant = now()
    counts = {state: 0 for state in sorted(VALID)}
    for item in job.items:
        counts[item["state"]] += 1
    if all(item["state"] in DONE for item in job.items):
        progress = "COMPLETED"
    elif counts["BLOCKED"]:
        progress = "NEEDS_REVIEW"
    elif counts["RUNNING"]:
        progress = "RUNNING"
    else:
        progress = "PENDING"
    return {
        "mode": "MANUAL_RESUMABLE_SOURCE_INTAKE",
        "pipeline_schema_version": PIPELINE_SCHEMA,
        "id": job.id,
        "revision": job.revision,
        "state": "CANCELLED" if job.state == "CANCELLED" else progress,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
        "history_events_dropped": (job.history[0].get("events_dropped", 0)
                                   if job.history and job.history[0].get("action") == "HISTORY_TRUNCATED" else 0),
        "total": len(job.items),
        "counts": counts,
        "coverage": {
            "total_variants": len(job.items),
            "documents_recorded": counts["IMPORTED"] + counts["ALREADY_PRESENT"],
            "without_recorded_document": counts["PENDING"] + counts["RUNNING"] + counts["BLOCKED"],
            "cancelled": counts["CANCELLED"],
            "completed_steps": sum(counts[state] for state in DONE),
            "facts_approved_by_operation": 0,
            "commercial_fields_saved": 0,
        },
        "recoverable_items": sum(
            row["state"] == "RUNNING" and _claim_expired(row, instant)
            for row in job.items
        ) if job.state != "CANCELLED" else 0,
        "max_attempts": MAX_ATTEMPTS,
        "items": [{
            key: row.get(key)
            for key in ("ecomm_id", "url", "state", "attempts",
                        "document_id", "error", "next_action", "claim_until")
        } | {
            "processing": _processing(row),
            "public_state": _public_state(row),
            "complete_available": bool(row.get("document_id"))
            and row.get("identity_schema") == 2
            and ((row.get("processing") or {}).get("phase") != "EXTRACTED"
                 or (document_versions is not None and document_versions.get(row.get("document_id")) != (
                     (row.get("processing") or {}).get("document_version"),
                     (row.get("processing") or {}).get("document_digest"))))
            and row["state"] != "RUNNING" and job.state != "CANCELLED",
            "recoverable": row["state"] == "RUNNING" and _claim_expired(row, instant)
            and job.state != "CANCELLED",
            "retry_available": row["state"] == "BLOCKED"
            and row["attempts"] < MAX_ATTEMPTS
            and row.get("next_action") != "REVIEW_IDENTITY"
            and bool((row.get("processing") or {}).get("retryable", True))
            and job.state != "CANCELLED",
        } for row in job.items],
        "sitemap_url": job.sitemap_url,
        "sitemap_sha256": job.sitemap_sha256,
        "selection_mode": (
            "EXACT_OPERATOR_URL"
            if job.items and job.items[0].get("source_mode") == "EXACT_OPERATOR_URL"
            else "REVIEWED_SITEMAP"
        ),
        "source_host": job.source_host,
        "external_writes_enabled": False,
        "ai_requests": 0,
        "claims_approved": 0,
        "manual_steps_only": True,
        "max_concurrent_steps": 1,
    }


class SourceIntakeQueue:
    def __init__(self, db, session, configured_hosts):
        self.db = db
        self.actor = f"sesión {session.id}"
        self.session = session
        self.hosts = allowed_hosts(configured_hosts)

    def _get(self, ident, *, locked=False):
        statement = select(SourceIntakeJob).where(SourceIntakeJob.id == ident)
        if locked:
            # Existing singleton serializes claims across *all* jobs, while a
            # persisted RUNNING lease protects the interval outside the lock.
            if self.db.scalar(select(Control.id).where(Control.id == 1).with_for_update()) is None:
                raise ValueError("Falta el control transaccional documental.")
            statement = statement.with_for_update()
        job = self.db.scalar(statement.execution_options(populate_existing=True))
        if not job:
            raise ValueError("Lote de fabricantes inexistente.")
        return job

    def detail(self, ident):
        return self._serialize(self._get(ident))

    def _serialize(self, job):
        ids = [row["document_id"] for row in job.items if row.get("document_id")]
        versions = {row.id: (row.version, row.digest) for row in self.db.execute(select(Document.id, Document.version, Document.digest).where(Document.id.in_(ids)))} if ids else {}
        return _summary(job, versions)

    def listing(self):
        # An interrupted global lease must remain discoverable even after
        # operators prepare more than twenty later manifests. Otherwise the
        # concurrency guard would block all work behind an invisible job.
        running = (
            "EXISTS (SELECT 1 FROM json_array_elements(items) AS entry WHERE entry->>'state'='RUNNING')"
            if self.db.get_bind().dialect.name == "postgresql"
            else "EXISTS (SELECT 1 FROM json_each(items) AS entry WHERE json_extract(entry.value,'$.state')='RUNNING')"
        )
        jobs = self.db.scalars(
            select(SourceIntakeJob)
            .order_by(text("CASE WHEN " + running + " THEN 0 ELSE 1 END"), SourceIntakeJob.created_at.desc())
            .limit(20)
        ).all()
        ids = {row["document_id"] for job in jobs for row in job.items if row.get("document_id")}
        versions = {row.id: (row.version, row.digest) for row in self.db.execute(select(Document.id, Document.version, Document.digest).where(Document.id.in_(ids)))} if ids else {}
        return {
            "mode": "MANUAL_RESUMABLE_SOURCE_INTAKE",
            "items": [_summary(job, versions) for job in jobs],
            "external_writes_enabled": False,
        }

    def create(self, request_key, sitemap_url, sitemap_sha256, selected,
               *, previewer=preview_candidates):
        if len(selected) < 1 or len(selected) > MAX_ITEMS:
            raise ValueError("Seleccioná entre 1 y 20 coincidencias.")
        if len({row["ecomm_id"] for row in selected}) != len(selected):
            raise ValueError("Ecomm ID repetido en un lote.")
        old = self.db.scalar(
            select(SourceIntakeJob).where(SourceIntakeJob.request_key == request_key)
        )
        if old:
            if (
                old.sitemap_url != sitemap_url or
                old.sitemap_sha256 != sitemap_sha256 or
                [(x["ecomm_id"], x["url"]) for x in old.items] !=
                [(x["ecomm_id"], x["url"]) for x in selected]
            ):
                raise ValueError("La clave de solicitud ya fue utilizada para otro lote.")
            return self._serialize(old)

        host, _ = target(sitemap_url, self.hosts)
        for item in selected:
            if target(item["url"], self.hosts)[0] != host:
                raise ValueError("Las fuentes deben pertenecer al mismo fabricante.")
        captured = sources(self.db)
        snapshots = []
        for item in selected:
            row = captured.get(item["ecomm_id"])
            if not _eligible_unit(row):
                raise ValueError("Producto, SKU o tipo de venta no apto para este lote.")
            snapshots.append(_identity(row))
            if _present(self.db, item["ecomm_id"], item["url"]):
                raise ValueError("La fuente ya está incorporada para una variante.")

        preview = previewer(
            self.db, [x["ecomm_id"] for x in selected], sitemap_url,
            ",".join(sorted(self.hosts))
        )
        preflight(preview, selected, sitemap_sha256)
        items = [{
            "ecomm_id": item["ecomm_id"],
            "url": item["url"],
            "state": "PENDING",
            "attempts": 0,
            "expected_identity": list(identity),
            "identity_schema": 2,
            "expected_identity_v2": identity_pin(captured[item["ecomm_id"]]),
            "identity_digest": digest(identity_pin(captured[item["ecomm_id"]])),
            "document_id": None,
            "error": None,
            "next_action": "INCORPORATE",
            "claim_token": None,
            "claim_until": None,
        } for item, identity in zip(selected, snapshots)]
        instant = now()
        job = SourceIntakeJob(
            id=str(uuid4()),
            request_key=request_key,
            created_at=instant,
            updated_at=instant,
            creator=self.actor,
            revision=1,
            state="PENDING",
            sitemap_url=sitemap_url,
            sitemap_sha256=sitemap_sha256,
            source_host=host,
            items=items,
            history=[{"action": "CREATED", "at": instant.isoformat(),
                      "by": self.actor, "items": len(items)}],
        )
        self.db.add(job)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            winner = self.db.scalar(select(SourceIntakeJob).where(SourceIntakeJob.request_key == request_key))
            if winner and winner.sitemap_url == sitemap_url and winner.sitemap_sha256 == sitemap_sha256 and [(x["ecomm_id"], x["url"]) for x in winner.items] == [(x["ecomm_id"], x["url"]) for x in selected]:
                return self._serialize(winner)
            raise ValueError("La solicitud fue creada por otra sesión; actualizá el lote sin repetir la operación.") from None
        return self._serialize(job)

    def create_explicit(self, request_key, selected):
        """Persist up to twenty human-reviewed exact URLs, without network.

        This is a staging manifest, never an approval of manufacturer
        identity or content. Requires the same 20-item queue table.
        """
        if not 1 <= len(selected) <= MAX_ITEMS:
            raise ValueError("Seleccioná entre 1 y 20 URLs exactas.")
        if (
            len({row.get("ecomm_id") for row in selected}) != len(selected)
            or not all(
                isinstance(row.get("ecomm_id"), str)
                and valid_variant_id(row["ecomm_id"])
                and isinstance(row.get("url"), str)
                and isinstance(row.get("provenance_note"), str)
                and 10 <= len(row["provenance_note"].strip()) <= 600
                for row in selected
            )
        ):
            raise ValueError("Ecomm ID, URL o motivo repetido/inválido.")
        source_host = None
        manifest = []
        for row in selected:
            host, _ = target(row["url"], self.hosts)
            if source_host is None:
                source_host = host
            if host != source_host:
                raise ValueError(
                    "Prepará un lote por dominio de fabricante; no mezcles sitios."
                )
            manifest.append({
                "ecomm_id": row["ecomm_id"],
                "url": row["url"],
                "provenance_note": row["provenance_note"].strip(),
            })
        manifest_digest = sha256(
            json.dumps(manifest, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
        existing = self.db.scalar(
            select(SourceIntakeJob).where(SourceIntakeJob.request_key == request_key)
        )
        if existing:
            if (
                existing.sitemap_url != ""
                or existing.sitemap_sha256 != manifest_digest
                or existing.source_host != source_host
                or [
                    (x["ecomm_id"], x["url"], x.get("provenance_note"))
                    for x in existing.items
                ] != [
                    (x["ecomm_id"], x["url"], x["provenance_note"])
                    for x in manifest
                ]
            ):
                raise ValueError("La clave de solicitud pertenece a otro lote.")
            return self._serialize(existing)

        snapshot = sources(self.db)
        items = []
        for row in manifest:
            variant = snapshot.get(row["ecomm_id"])
            if not _eligible_unit(variant):
                raise ValueError(
                    "La variante Ecomm, su SKU o el tipo de venta no son aptos."
                )
            entry = {
                **row,
                "source_mode": "EXACT_OPERATOR_URL",
                "expected_identity": list(_identity(variant)),
                "identity_schema": 2,
                "expected_identity_v2": identity_pin(variant),
                "identity_digest": digest(identity_pin(variant)),
                "state": "PENDING",
                "attempts": 0,
                "document_id": None,
                "error": None,
                "next_action": "INCORPORATE",
                "claim_token": None,
                "claim_until": None,
            }
            archived = document_for_item(self.db, entry)
            if archived:
                entry["document_id"] = archived.id
                entry["processing"] = {**_processing(entry), **receipt_for_document(self.db, entry, archived.id, allow_current=True)}
            items.append(entry)
        instant = now()
        job = SourceIntakeJob(
            id=str(uuid4()), request_key=request_key, created_at=instant,
            updated_at=instant, creator=self.actor, revision=1,
            state="PENDING", sitemap_url="", sitemap_sha256=manifest_digest,
            source_host=source_host, items=items,
            history=[{
                "action": "CREATED_EXACT_URL_MANIFEST",
                "at": instant.isoformat(), "by": self.actor,
                "items": len(items),
            }],
        )
        self.db.add(job)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            winner = self.db.scalar(select(SourceIntakeJob).where(SourceIntakeJob.request_key == request_key))
            if winner and winner.sitemap_url == "" and winner.sitemap_sha256 == manifest_digest and winner.source_host == source_host and [(x["ecomm_id"], x["url"], x.get("provenance_note")) for x in winner.items] == [(x["ecomm_id"], x["url"], x["provenance_note"]) for x in manifest]:
                return self._serialize(winner)
            raise ValueError("La solicitud fue creada por otra sesión; actualizá el lote sin repetir la operación.") from None
        return self._serialize(job)

    def _update(self, job, items, action):
        instant = now()
        job.items = items
        job.revision += 1
        job.updated_at = instant
        events = list(job.history or [])
        dropped = 0
        if events and events[0].get("action") == "HISTORY_TRUNCATED":
            dropped = events.pop(0).get("events_dropped", 0)
        events.append({"action": action, "at": instant.isoformat(), "by": self.actor})
        # All normal <=20-variant/3-attempt runs fit without truncation. Bound
        # repeated manual maintenance too, and explicitly retain any loss.
        if len(events) > MAX_HISTORY_EVENTS or (dropped and len(events) >= MAX_HISTORY_EVENTS):
            dropped += len(events) - (MAX_HISTORY_EVENTS - 1)
            events = events[-(MAX_HISTORY_EVENTS - 1):]
        job.history = ([{"action": "HISTORY_TRUNCATED", "at": instant.isoformat(), "by": self.actor, "events_dropped": dropped}] if dropped else []) + events
        self.db.commit()
        return self._serialize(job)

    def _recover(self, items, *, instant):
        changed = False
        for row in items:
            if row["state"] != "RUNNING" or not _claim_expired(row, instant):
                continue
            try:
                check_identity(row, sources(self.db))
                doc = document_for_item(self.db, row)
                if doc:
                    row["document_id"] = doc.id
                    with self.db.begin_nested():
                        row["processing"] = extract_candidates(self.db, self.session, row)
                    row["state"], row["error"], row["next_action"] = "IMPORTED", None, "REVIEW_EVIDENCE"
                else:
                    raise PipelineError("INTERRUPTED_WITHOUT_DOCUMENT", "Paso interrumpido sin original archivado; reintento manual requerido.", retryable=True)
            except Exception as error:
                failure = safe_failure(error)
                row["state"] = "IMPORTED" if row.get("document_id") else "BLOCKED"
                row["error"] = failure.public_message
                row["next_action"] = "RETRY" if failure.retryable else "REVIEW_EVIDENCE"
                row["processing"] = {**_processing(row), "phase": "FAILED" if failure.retryable or failure.code == "PIPELINE_FAILED" else "BLOCKED", "error_code": failure.code, "retryable": failure.retryable}
            row["processing"]["finished_at"] = instant.isoformat()
            row["claim_token"] = row["claim_until"] = None
            changed = True
        return changed

    def recover(self, ident, revision):
        """Resolve expired leases using local receipts; never fetch or retry.

        A second explicit operator action is required to retry a failed item
        or process any pending variant. A former worker loses ownership after
        recovery, so its delayed response cannot overwrite this decision.
        """
        job = self._get(ident, locked=True)
        if job.revision != revision or job.state == "CANCELLED":
            raise ValueError("El lote cambió o fue cancelado.")
        rows = deepcopy(job.items)
        if not self._recover(rows, instant=now()):
            raise ValueError("No hay pasos interrumpidos con plazo vencido para recuperar.")
        return self._update(job, rows, "RECOVERED_OFFLINE")

    def step(
        self, ident, revision, *, importer=capture_selected,
        explicit_importer=import_explicit_url,
    ):
        job = self._get(ident, locked=True)
        if job.revision != revision:
            raise ValueError("El lote cambió: actualizá su estado antes de continuar.")
        if job.state == "CANCELLED":
            raise ValueError("El lote fue cancelado.")
        rows = deepcopy(job.items)
        had_recovery = self._recover(rows, instant=now())
        if had_recovery:
            # Recovery only completes local work. Never unexpectedly start a
            # different provider request in the same recovery operation.
            return self._update(job, rows, "RECOVERED")
        if any(x["state"] == "RUNNING" for x in rows):
            raise ValueError("Ya existe un paso de captura ejecutándose.")
        selected = next((r for r in rows if r["state"] == "PENDING"), None)
        if not selected:
            return self._serialize(job)
        # The singleton row is locked until CLAIMED commits. A second worker
        # then sees this persisted lease, including across different jobs.
        expression = (
            "EXISTS (SELECT 1 FROM json_array_elements(items) AS entry WHERE entry->>'state'='RUNNING')"
            if self.db.get_bind().dialect.name == "postgresql"
            else "EXISTS (SELECT 1 FROM json_each(items) AS entry WHERE json_extract(entry.value,'$.state')='RUNNING')"
        )
        active = self.db.scalar(text("SELECT id FROM kiki_source_intake_jobs WHERE state != 'CANCELLED' AND " + expression + " LIMIT 1"))
        if active:
            raise ValueError("Ya existe un paso documental activo; recuperá o esperá su resultado antes de iniciar otro lote.")
        try:
            check_identity(selected, sources(self.db))
            if selected["attempts"] >= MAX_ATTEMPTS:
                raise PipelineError("ATTEMPT_LIMIT", "La fuente agotó los tres intentos permitidos; requiere revisión.")
        except PipelineError as failure:
            selected["state"], selected["error"], selected["next_action"] = "BLOCKED", failure.public_message, "REVIEW_IDENTITY"
            selected["processing"] = {**_processing(selected), "phase": "BLOCKED", "error_code": failure.code, "retryable": False}
            return self._update(job, rows, "IDENTITY_CHANGED")
        token = str(uuid4())
        selected["state"] = "RUNNING"
        selected["claim_token"] = token
        selected["claim_until"] = (now() + CLAIM_TTL).isoformat()
        selected["attempts"] += 1
        selected["next_action"] = "WAIT"
        selected["processing"] = {**_processing(selected), "started_at": now().isoformat(), "finished_at": None, "phase": "PENDING", "error_code": None, "retryable": False}
        self._update(job, rows, "CLAIMED")

        try:
            archived = document_for_item(self.db, selected)
            if archived:
                self._finish(ident, selected["ecomm_id"], token, archived.id, None)
                return self.detail(ident)
            _reject_repeated(_existing_documents(self.db, selected["ecomm_id"]), selected["url"], today=now().date())
            # Persist reservation before invoking the existing guarded importer.
            self._reserve_download(ident, selected["ecomm_id"], token)
            if selected.get("source_mode") == "EXACT_OPERATOR_URL":
                expected = self.db.scalar(
                    select(Dossier.version).where(
                        Dossier.ecomm_id == selected["ecomm_id"]
                    )
                )
                result = explicit_importer(
                    self.db, self.session,
                    ecomm_id=selected["ecomm_id"],
                    expected_version=expected if expected is not None else 0,
                    reference_url=selected["url"],
                    provenance_note=selected["provenance_note"],
                    configured_hosts=",".join(sorted(self.hosts)),
                )
                document_id = result["incorporated_document_id"]
                document = self.db.get(Document, document_id)
                if (
                    not document
                    or document.body.get("associated_ecomm_id")
                    != selected["ecomm_id"]
                    or document.body.get("source", {}).get("review_state")
                    != "PENDING"
                    or document.body.get("source", {}).get("reference_url")
                    != selected["url"]
                ):
                    raise ValueError(
                        "No se confirmó un original pendiente para esta variante."
                    )
            else:
                result = importer(
                    self.db, self.session,
                    sitemap_url=job.sitemap_url,
                    sitemap_sha256=job.sitemap_sha256,
                    items=[{"ecomm_id": selected["ecomm_id"],
                            "url": selected["url"]}],
                    configured_hosts=",".join(sorted(self.hosts)),
                )
                docs = result.get("documents") or []
                if (
                    len(docs) != 1 or
                    docs[0]["ecomm_id"] != selected["ecomm_id"]
                    or docs[0].get("review_state") != "PENDING"
                    or result.get("facts_approved") != 0
                ):
                    raise ValueError(
                        "La incorporación no confirmó una fuente pendiente."
                    )
                document_id = docs[0]["document_id"]
        except Exception as error:
            self.db.rollback()
            failure = safe_failure(error)
            try:
                existing = document_for_item(self.db, selected)
            except PipelineError:
                existing = None
            self._finish(ident, selected["ecomm_id"], token, existing.id if existing else None, failure)
            return self.detail(ident)
        self._finish(ident, selected["ecomm_id"], token, document_id, None)
        return self.detail(ident)

    def _reserve_download(self, ident, ecomm_id, token):
        job = self._get(ident, locked=True)
        rows = deepcopy(job.items)
        selected = next(x for x in rows if x["ecomm_id"] == ecomm_id)
        if selected["state"] != "RUNNING" or selected["claim_token"] != token:
            raise ValueError("El paso ya no es dueño del lote.")
        selected["processing"] = _processing(selected)
        selected["processing"]["download_attempts"] += 1
        selected["processing"]["request_measurement_pending"] = True
        self._update(job, rows, "DOWNLOAD_RESERVED")

    def _finish(self, ident, ecomm_id, token, document_id, error):
        job = self._get(ident, locked=True)
        rows = deepcopy(job.items)
        match = next((x for x in rows if x["ecomm_id"] == ecomm_id), None)
        if not match or match["state"] != "RUNNING" or match["claim_token"] != token:
            raise ValueError("El paso ya no es dueño del lote; no se guardó resultado.")
        if document_id:
            archived = self.db.get(Document, document_id)
            if not archived or archived.body.get("associated_ecomm_id") != ecomm_id or archived.body.get("source", {}).get("reference_url") != match["url"]:
                document_id = None
                error = PipelineError("DOCUMENT_IDENTITY_MISMATCH", "La incorporación no acreditó un original asociado a esta variante y URL.")
        match["document_id"] = document_id
        if document_id:
            try:
                # Pin the immutable original receipt before extraction. A lost
                # response after this commit is completed by offline recovery.
                match["processing"] = receipt_for_document(self.db, match, document_id)
                self._update(job, rows, "ORIGINAL_PINNED")
                job = self._get(ident, locked=True)
                rows = deepcopy(job.items)
                match = next(x for x in rows if x["ecomm_id"] == ecomm_id)
                if match["state"] != "RUNNING" or match["claim_token"] != token:
                    raise PipelineError("LEASE_CHANGED", "Otro proceso tomó el paso; no se modificó el resultado.")
                match["processing"] = extract_candidates(self.db, self.session, match)
                error = None
            except Exception as failure:
                self.db.rollback()
                job = self._get(ident, locked=True)
                rows = deepcopy(job.items)
                match = next(x for x in rows if x["ecomm_id"] == ecomm_id)
                if match["state"] != "RUNNING" or match["claim_token"] != token:
                    raise ValueError("El paso ya no es dueño del lote; no se guardó resultado.") from None
                error = safe_failure(failure)
        if error:
            error = safe_failure(error)
            usage = _processing(match)
            if usage.get("request_measurement_pending"):
                reported = getattr(error, "request_count", None)
                previous = usage.get("http_requests_reported")
                usage["http_requests_reported"] = previous + reported if type(previous) is int and type(reported) is int else None
                usage["request_measurement_pending"] = False
            match["processing"] = {**usage, "phase": "FAILED" if error.retryable or error.code == "PIPELINE_FAILED" else "BLOCKED", "error_code": error.code, "retryable": error.retryable}
        match["state"] = "IMPORTED" if document_id else "BLOCKED"
        match["document_id"] = document_id
        match["error"] = error.public_message if error else None
        match["next_action"] = "REVIEW_EVIDENCE" if document_id or not (error and error.retryable) else "RETRY"
        processing = _processing(match)
        processing["finished_at"] = now().isoformat()
        if processing["started_at"]:
            processing["elapsed_ms"] = max(0, round((now() - datetime.fromisoformat(processing["started_at"])).total_seconds() * 1000))
        match["processing"] = processing
        match["claim_token"] = match["claim_until"] = None
        self._update(job, rows, "DOCUMENT_PROCESSED" if document_id else "BLOCKED")

    def complete_archived(self, ident, revision, ecomm_id, *, expected_document_version=None, expected_document_digest=None):
        """Only local extraction of the exact pinned original; never a GET."""
        job = self._get(ident, locked=True)
        if job.revision != revision or job.state == "CANCELLED":
            raise ValueError("El lote cambió o fue cancelado.")
        rows = deepcopy(job.items)
        match = next((x for x in rows if x["ecomm_id"] == ecomm_id), None)
        if not match or not match.get("document_id") or (match["state"] == "RUNNING" and not _claim_expired(match, now())):
            raise ValueError("No hay un original local disponible o el paso sigue activo.")
        try:
            with self.db.begin_nested():
                if expected_document_version is not None or expected_document_digest is not None:
                    renewed = repin_reviewed_metadata(self.db, match, expected_document_version, expected_document_digest)
                    match.update(renewed)
                match["processing"] = extract_candidates(self.db, self.session, match)
                match["error"] = None
        except PipelineError as error:
            if error.code == "DOCUMENT_VERSION_CONFLICT":
                raise
            match["processing"] = {**_processing(match), "phase": "BLOCKED", "error_code": error.code, "retryable": False}
            match["error"] = error.public_message
        match["state"] = "IMPORTED"
        match["claim_token"] = match["claim_until"] = None
        match["next_action"] = "REVIEW_EVIDENCE"
        return self._update(job, rows, "LOCAL_PROCESSING_COMPLETED")

    def retry(self, ident, revision, ecomm_id):
        job = self._get(ident, locked=True)
        if job.revision != revision or job.state == "CANCELLED":
            raise ValueError("El lote cambió o fue cancelado.")
        rows = deepcopy(job.items)
        match = next((x for x in rows if x["ecomm_id"] == ecomm_id), None)
        if not match or match["state"] != "BLOCKED" or match["attempts"] >= MAX_ATTEMPTS:
            raise ValueError("Esta variante no admite reintento automático.")
        try:
            check_identity(match, sources(self.db))
        except PipelineError:
            raise ValueError("Identidad Ecomm cambió; iniciá una investigación nueva.") from None
        if not (match.get("processing") or {}).get("retryable", False):
            raise ValueError("La excepción requiere revisión humana; no admite reintento de descarga.")
        doc = _present(self.db, ecomm_id, match["url"])
        if doc:
            match["state"] = "ALREADY_PRESENT"
            match["document_id"] = doc
            match["next_action"] = "REVIEW_EVIDENCE"
        else:
            match["state"] = "PENDING"
            match["next_action"] = "INCORPORATE"
        match["error"] = None
        return self._update(job, rows, "RETRY_REQUESTED")

    def cancel(self, ident, revision):
        job = self._get(ident, locked=True)
        if job.revision != revision:
            raise ValueError("El lote cambió.")
        rows = deepcopy(job.items)
        if any(row["state"] == "RUNNING" for row in rows):
            raise ValueError("Hay un paso en curso; cancelá al terminarlo.")
        for row in rows:
            if row["state"] == "PENDING":
                row["state"] = "CANCELLED"
                row["next_action"] = None
        job.state = "CANCELLED"
        return self._update(job, rows, "CANCELLED")
