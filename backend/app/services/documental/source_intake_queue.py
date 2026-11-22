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

from sqlalchemy import select

from app.services.documental.storage import Document, Dossier
from app.integrations.ecomm_app.api_catalog_browser import valid_variant_id
from app.services.editorial_batches.context import sources
from .manufacturer_batch_intake import _identity, capture_selected, preflight
from .explicit_url_intake import import_explicit_url
from .sitemap_discovery import preview_candidates
from .source_fetch import allowed_hosts, target
from .source_intake_storage import SourceIntakeJob

MAX_ITEMS = 20
MAX_STEPS_PER_REQUEST = 1
CLAIM_TTL = timedelta(minutes=10)
MAX_ATTEMPTS = 3
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


def _summary(job):
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
        "id": job.id,
        "revision": job.revision,
        "state": "CANCELLED" if job.state == "CANCELLED" else progress,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
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
            "recoverable": row["state"] == "RUNNING" and _claim_expired(row, instant)
            and job.state != "CANCELLED",
            "retry_available": row["state"] == "BLOCKED"
            and row["attempts"] < MAX_ATTEMPTS
            and row.get("next_action") != "REVIEW_IDENTITY"
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
            statement = statement.with_for_update()
        job = self.db.scalar(statement.execution_options(populate_existing=True))
        if not job:
            raise ValueError("Lote de fabricantes inexistente.")
        return job

    def detail(self, ident):
        return _summary(self._get(ident))

    def listing(self):
        jobs = self.db.scalars(
            select(SourceIntakeJob)
            .order_by(SourceIntakeJob.created_at.desc())
            .limit(20)
        ).all()
        return {
            "mode": "MANUAL_RESUMABLE_SOURCE_INTAKE",
            "items": [_summary(job) for job in jobs],
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
            return _summary(old)

        host, _ = target(sitemap_url, self.hosts)
        for item in selected:
            if target(item["url"], self.hosts)[0] != host:
                raise ValueError("Las fuentes deben pertenecer al mismo fabricante.")
        captured = sources(self.db)
        snapshots = []
        for item in selected:
            row = captured.get(item["ecomm_id"])
            if not row or not row.get("sku") or row.get("is_combo") is not False:
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
        self.db.commit()
        return _summary(job)

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
        digest = sha256(
            json.dumps(manifest, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
        existing = self.db.scalar(
            select(SourceIntakeJob).where(SourceIntakeJob.request_key == request_key)
        )
        if existing:
            if (
                existing.sitemap_url != ""
                or existing.sitemap_sha256 != digest
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
            return _summary(existing)

        snapshot = sources(self.db)
        items = []
        for row in manifest:
            variant = snapshot.get(row["ecomm_id"])
            if (
                not variant or not variant.get("sku")
                or variant.get("is_combo") is not False
            ):
                raise ValueError(
                    "La variante Ecomm, su SKU o el tipo de venta no son aptos."
                )
            if _present(self.db, row["ecomm_id"], row["url"]):
                raise ValueError("La URL ya está incorporada para esa variante.")
            items.append({
                **row,
                "source_mode": "EXACT_OPERATOR_URL",
                "expected_identity": list(_identity(variant)),
                "state": "PENDING",
                "attempts": 0,
                "document_id": None,
                "error": None,
                "next_action": "INCORPORATE",
                "claim_token": None,
                "claim_until": None,
            })
        instant = now()
        job = SourceIntakeJob(
            id=str(uuid4()), request_key=request_key, created_at=instant,
            updated_at=instant, creator=self.actor, revision=1,
            state="PENDING", sitemap_url="", sitemap_sha256=digest,
            source_host=source_host, items=items,
            history=[{
                "action": "CREATED_EXACT_URL_MANIFEST",
                "at": instant.isoformat(), "by": self.actor,
                "items": len(items),
            }],
        )
        self.db.add(job)
        self.db.commit()
        return _summary(job)

    def _update(self, job, items, action):
        instant = now()
        job.items = items
        job.revision += 1
        job.updated_at = instant
        job.history = (list(job.history or []) + [
            {"action": action, "at": instant.isoformat(), "by": self.actor}
        ])[-100:]
        self.db.commit()
        return _summary(job)

    def _recover(self, items, *, instant):
        # Recovery is explicit and requires the original lease to have expired.
        # A persisted document is evidence that an interrupted step committed.
        changed = False
        for row in items:
            if row["state"] != "RUNNING":
                continue
            if not _claim_expired(row, instant):
                continue
            doc = _present(self.db, row["ecomm_id"], row["url"])
            row["state"] = "IMPORTED" if doc else "BLOCKED"
            row["document_id"] = doc
            row["error"] = None if doc else "Paso interrumpido; revisar antes de reintentar."
            row["next_action"] = "REVIEW_EVIDENCE" if doc else "RETRY"
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
        if any(x["state"] == "RUNNING" for x in rows):
            if had_recovery:
                return self._update(job, rows, "RECOVERED")
            raise ValueError("Ya existe un paso de captura ejecutándose.")
        selected = next((r for r in rows if r["state"] == "PENDING"), None)
        if not selected:
            if had_recovery:
                return self._update(job, rows, "RECOVERED")
            return _summary(job)
        snapshot = sources(self.db)
        current = snapshot.get(selected["ecomm_id"])
        if not current or tuple(selected["expected_identity"]) != _identity(current):
            selected["state"] = "BLOCKED"
            selected["error"] = "Cambió la identidad en Ecomm-App; revisar coincidencia."
            selected["next_action"] = "REVIEW_IDENTITY"
            return self._update(job, rows, "IDENTITY_CHANGED")
        token = str(uuid4())
        selected["state"] = "RUNNING"
        selected["claim_token"] = token
        selected["claim_until"] = (now() + CLAIM_TTL).isoformat()
        selected["attempts"] += 1
        selected["next_action"] = "WAIT"
        self._update(job, rows, "CLAIMED")

        try:
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
            # The exporter may have committed before the response was lost.
            existing = _present(self.db, selected["ecomm_id"], selected["url"])
            self._finish(ident, selected["ecomm_id"], token, existing,
                         str(error)[:350] if not existing else None)
            return self.detail(ident)
        self._finish(ident, selected["ecomm_id"], token, document_id, None)
        return self.detail(ident)

    def _finish(self, ident, ecomm_id, token, document_id, error):
        job = self._get(ident, locked=True)
        rows = deepcopy(job.items)
        match = next((x for x in rows if x["ecomm_id"] == ecomm_id), None)
        if not match or match["state"] != "RUNNING" or match["claim_token"] != token:
            raise ValueError("El paso ya no es dueño del lote; no se guardó resultado.")
        match["state"] = "IMPORTED" if document_id else "BLOCKED"
        match["document_id"] = document_id
        match["error"] = error
        match["next_action"] = "REVIEW_EVIDENCE" if document_id else "RETRY"
        match["claim_token"] = match["claim_until"] = None
        self._update(job, rows, "DOCUMENT_IMPORTED" if document_id else "BLOCKED")

    def retry(self, ident, revision, ecomm_id):
        job = self._get(ident, locked=True)
        if job.revision != revision or job.state == "CANCELLED":
            raise ValueError("El lote cambió o fue cancelado.")
        rows = deepcopy(job.items)
        match = next((x for x in rows if x["ecomm_id"] == ecomm_id), None)
        if not match or match["state"] != "BLOCKED" or match["attempts"] >= MAX_ATTEMPTS:
            raise ValueError("Esta variante no admite reintento automático.")
        snapshot = sources(self.db)
        current = snapshot.get(ecomm_id)
        if not current or tuple(match["expected_identity"]) != _identity(current):
            raise ValueError("Identidad Ecomm cambió; iniciá una investigación nueva.")
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
