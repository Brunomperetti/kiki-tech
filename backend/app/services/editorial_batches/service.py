"""Explicit, bounded, resumable local editorial coordination. Never writes providers."""

from collections import Counter
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from time import monotonic
from sqlalchemy import select, func
from app.core.config import get_settings
from app.services.documental.storage import digest
from app.services.ecomm_api_work_queue_service import build_queue
from app.integrations.ecomm_app.api_catalog_browser import valid_variant_id
from .storage import Batch, Item
from .context import Context, AtomicSession, sources

TERMINAL = {"COMPLETED", "BLOCKED", "CONFLICT", "ERROR", "CANCELLED"}


def now():
    return datetime.now(timezone.utc)


class Batches:
    def __init__(self, db, session):
        if db.bind.dialect.name != "postgresql":
            raise ValueError(
                "La cola persistente requiere PostgreSQL y su migración revisada; no hay fallback de base."
            )
        self.db, self.session = db, session
        self.config = get_settings()
        self.actor = f"{self.config.kiki_admin_username} · sesión {session.id}"

    def get(self, ident, lock=False):
        stmt = (
            select(Batch)
            .where(Batch.id == ident)
            .execution_options(populate_existing=True)
        )
        if lock:
            stmt = stmt.with_for_update(nowait=True)
        batch = self.db.scalar(stmt)
        if not batch:
            raise ValueError("Lote no encontrado.")
        return batch

    def event(self, batch, action, detail=None):
        batch.revision += 1
        batch.updated_at = now()
        # Worker progress lives in bounded item records; avoid an ever-growing batch blob.
        batch.history = batch.history + [
            {
                "action": action,
                "at": now().isoformat(),
                "actor": self.actor,
                "detail": detail,
            }
        ]

    def counts(self, ident):
        return dict(
            self.db.execute(
                select(Item.state, func.count())
                .where(Item.batch_id == ident)
                .group_by(Item.state)
            ).all()
        )

    def dto(self, batch):
        return {
            key: getattr(batch, key)
            for key in (
                "id",
                "operation",
                "state",
                "revision",
                "created_at",
                "updated_at",
                "creator",
                "authorized_by",
                "authorized_at",
                "selection",
                "summary",
                "preview_hash",
                "total",
                "history",
            )
        } | {
            "counts": self.counts(batch.id),
            "internal_only": True,
            "external_writes_enabled": False,
        }

    def detail(self, ident, page=1, limit=25):
        batch = self.get(ident)
        items = self.db.scalars(
            select(Item)
            .where(Item.batch_id == ident)
            .order_by(Item.position)
            .offset((page - 1) * limit)
            .limit(limit)
        ).all()
        return {
            **self.dto(batch),
            "page": page,
            "limit": limit,
            "items": [
                {
                    key: getattr(i, key)
                    for key in (
                        "ecomm_id",
                        "position",
                        "state",
                        "attempts",
                        "expected",
                        "result",
                        "error",
                        "history",
                    )
                }
                for i in items
            ],
        }

    def listing(self, page=1, limit=10):
        rows = self.db.scalars(
            select(Batch)
            .order_by(Batch.created_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
        ).all()
        return {
            "items": [self.dto(x) for x in rows],
            "total": self.db.scalar(select(func.count()).select_from(Batch)),
            "page": page,
            "limit": limit,
        }

    def preview(self, body):
        request_key = body["request_key"]
        old = self.db.scalar(select(Batch).where(Batch.request_key == request_key))
        selection = body["selection"]
        if old:
            if old.selection != selection or old.operation != body["operation"]:
                raise ValueError(
                    "La clave idempotente ya corresponde a otra selección."
                )
            return self.detail(old.id)
        if selection["kind"] == "IDS":
            ids = selection["ids"]
        else:
            ids = build_queue(
                self.db,
                query=selection["query"],
                filter_name=selection["filter"],
                selection_ids_only=True,
            )["selected_ids"]
        if (
            not ids
            or len(ids) > self.config.kiki_editorial_batch_max_items
            or len(set(ids)) != len(ids)
            or not all(valid_variant_id(i) for i in ids)
        ):
            raise ValueError(
                "Selección vacía, repetida, inválida o supera el límite del lote."
            )
        source_map = sources(self.db, lock=True)
        if any(i not in source_map for i in ids):
            raise ValueError(
                "La selección contiene variantes que no pertenecen a la captura API."
            )
        batch = Batch(
            id=str(uuid4()),
            request_key=request_key,
            operation=body["operation"],
            state="PREVIEW",
            revision=0,
            created_at=now(),
            updated_at=now(),
            creator=self.actor,
            selection=selection,
            summary={},
            preview_hash="",
            total=len(ids),
            history=[],
        )
        self.db.add(batch)
        counts, fingerprints = Counter(), []
        for offset in range(0, len(ids), 25):
            chunk = ids[offset : offset + 25]
            context = Context(
                self.db, chunk, source_map, self.config.kiki_editorial_context_bytes
            )
            for index, ident in enumerate(chunk, offset):
                inspected = self.inspect(context, ident)
                for key in (
                    "sufficient_evidence",
                    "no_documentation",
                    "conflicts",
                    "stale",
                    "eligible",
                    "human_required",
                    "revoked",
                    "documents_changed",
                ):
                    counts[key] += int(inspected.get(key, False))
                fingerprints.append((ident, inspected["fingerprint"]))
                self.db.add(
                    Item(
                        id=str(uuid4()),
                        batch_id=batch.id,
                        ecomm_id=ident,
                        position=index,
                        state="PENDING",
                        attempts=0,
                        expected=inspected["expected"],
                        result={"preview": inspected},
                        error={},
                        history=[],
                    )
                )
            self.db.flush()
        batch.summary = dict(counts)
        batch.preview_hash = digest(
            {"items": fingerprints, "operation": batch.operation}
        )
        self.event(batch, "PREVIEW_CREATED")
        self.db.commit()
        return self.detail(batch.id)

    def inspect(self, context, ident):
        try:
            return context.inspect(self.db, self.session, ident)
        except ValueError as exc:
            expected = {"blocked": str(exc)}
            return {
                "expected": expected,
                "fingerprint": digest(expected),
                "conflicts": True,
                "eligible": False,
                "human_required": True,
                "reasons": [str(exc)],
            }

    def start(self, ident, body):
        batch = self.get(ident, lock=True)
        if batch.start_key == body["idempotency_key"] and batch.authorized_at:
            return self.dto(batch)
        if (
            batch.state != "PREVIEW"
            or batch.revision != body["expected_revision"]
            or batch.preview_hash != body["preview_hash"]
            or body["confirm"] is not True
        ):
            raise ValueError(
                "La previsualización cambió o falta confirmación explícita."
            )
        batch.state = "PENDING"
        batch.start_key = body["idempotency_key"]
        batch.authorized_by = self.actor
        batch.authorized_at = now()
        self.event(batch, "CONFIRMED", {"preview_hash": batch.preview_hash})
        self.db.commit()
        return self.dto(batch)

    def cancel(self, ident, revision):
        batch = self.get(ident, lock=True)
        if batch.revision != revision:
            raise ValueError("El lote cambió; recargá antes de cancelar.")
        if batch.state in {"CANCELLED", "COMPLETED"}:
            return self.dto(batch)
        rows = self.db.scalars(
            select(Item).where(
                Item.batch_id == ident, Item.state.in_(["PENDING", "RUNNING"])
            )
        ).all()
        for item in rows:
            item.state = "CANCELLED"
            item.history = item.history + [
                {"action": "CANCELLED", "at": now().isoformat(), "actor": self.actor}
            ]
        batch.state = "CANCELLED"
        batch.owner = None
        batch.lease_until = None
        self.event(batch, "CANCELLED")
        self.db.commit()
        return self.dto(batch)

    def claim(self, ident, resume=False):
        batch = self.get(ident, lock=True)
        if not batch.authorized_at or batch.state in {
            "PREVIEW",
            "CANCELLED",
            "COMPLETED",
        }:
            raise ValueError("Lote no autorizado o ya terminado.")
        if batch.owner:
            if not resume and batch.lease_until and batch.lease_until > now():
                raise ValueError(
                    "Otro paso tiene una concesión activa. Esperá o reanudá explícitamente después de una interrupción."
                )
            for item in self.db.scalars(
                select(Item).where(Item.batch_id == ident, Item.state == "RUNNING")
            ):
                item.state = (
                    "PENDING"
                    if item.attempts < self.config.kiki_editorial_max_attempts
                    else "ERROR"
                )
                if item.state == "ERROR":
                    item.error = {
                        "message": "Límite de intentos alcanzado tras interrupciones."
                    }
                item.history = item.history + [
                    {
                        "action": "INTERRUPTED",
                        "at": now().isoformat(),
                        "actor": self.actor,
                    }
                ]
        rows = self.db.scalars(
            select(Item)
            .where(Item.batch_id == ident, Item.state == "PENDING")
            .order_by(Item.position)
            .limit(self.config.kiki_editorial_step_size)
        ).all()
        if not rows:
            batch.owner = None
            batch.lease_until = None
            counts = self.counts(ident)
            batch.state = (
                "ERROR"
                if counts.get("ERROR")
                else "CONFLICT"
                if counts.get("CONFLICT")
                else "BLOCKED"
                if counts.get("BLOCKED")
                else "COMPLETED"
            )
            self.event(batch, "FINISHED", counts)
            self.db.commit()
            return None
        token = str(uuid4())
        batch.owner = token
        batch.lease_until = now() + timedelta(seconds=60)
        batch.state = "RUNNING"
        for item in rows:
            item.state = "RUNNING"
            item.attempts += 1
            item.history = item.history + [
                {
                    "action": "CLAIMED",
                    "at": now().isoformat(),
                    "actor": self.actor,
                    "attempt": item.attempts,
                }
            ]
        self.db.commit()
        return token, [row.id for row in rows]

    def process(self, ident, token, item_ids):
        batch = self.get(ident, lock=True)
        if batch.owner != token or batch.state != "RUNNING":
            raise ValueError("Concesión reemplazada: este proceso no puede escribir.")
        rows = self.db.scalars(
            select(Item).where(Item.id.in_(item_ids)).order_by(Item.position)
        ).all()
        source_map = sources(self.db, lock=True)
        context = Context(
            self.db,
            [i.ecomm_id for i in rows],
            source_map,
            self.config.kiki_editorial_context_bytes,
            lock=True,
        )
        started = monotonic()
        for index, item in enumerate(rows):
            if (
                index
                and monotonic() - started >= self.config.kiki_editorial_step_seconds
            ):
                item.state = "PENDING"
                item.attempts -= 1
                item.history = item.history + [
                    {
                        "action": "YIELDED_TIME_BUDGET",
                        "at": now().isoformat(),
                        "actor": self.actor,
                    }
                ]
                continue
            inspection = self.inspect(context, item.ecomm_id)
            previous = item.result.get("preview", {})
            if digest(inspection["expected"]) != digest(item.expected):
                item.state = "CONFLICT"
                item.error = {
                    "message": "La ficha, identidad o evidencia cambió desde la previsualización; crear un lote nuevo."
                }
            elif batch.operation == "REVIEW_TASKS":
                item.state = "COMPLETED"
                item.result = {
                    **item.result,
                    "task": {
                        "requires_human": True,
                        "review_schedule": inspection.get("review_schedule"),
                        "reasons": inspection.get("reasons", []),
                        "revoked": inspection.get("revoked", False),
                        "documents_changed": inspection.get("documents_changed", False),
                    },
                    "fields_saved": False,
                }
            elif not inspection.get("eligible"):
                item.state = "BLOCKED"
                item.error = {
                    "message": "Sin respaldo vigente para campos incompletos. Revisar documentos, identidad y aprobaciones.",
                    "reasons": inspection.get("reasons", []),
                }
            else:
                proposal = context.Proposals(
                    AtomicSession(self.db), self.session
                ).generate(
                    item.ecomm_id,
                    item.expected["workspace_version"],
                    only_missing=True,
                    batch_reference={
                        "batch_id": ident,
                        "item_id": item.id,
                        "authorized_by": batch.authorized_by,
                    },
                )
                item.state = "COMPLETED"
                item.result = {
                    **item.result,
                    "proposal_id": proposal["draft_id"],
                    "fields_without_support": inspection["fields_without_support"],
                    "fields_saved": False,
                }
            item.history = item.history + [
                {
                    "action": item.state,
                    "at": now().isoformat(),
                    "actor": self.actor,
                    "attempt": item.attempts,
                    "evidence_fingerprint": previous.get("fingerprint"),
                }
            ]
        self.db.flush()
        counts = self.counts(ident)
        batch.state = (
            "PENDING"
            if counts.get("PENDING")
            else "ERROR"
            if counts.get("ERROR")
            else "CONFLICT"
            if counts.get("CONFLICT")
            else "BLOCKED"
            if counts.get("BLOCKED")
            else "COMPLETED"
        )
        batch.owner = None
        batch.lease_until = None
        batch.updated_at = now()
        batch.revision += 1
        if batch.state != "PENDING":
            self.event(batch, "FINISHED", counts)
        # Commit proposals AND item results together. No service can commit early.
        self.db.commit()
        return self.dto(batch)

    def step(self, ident, resume=False):
        claim = self.claim(ident, resume)
        if claim is None:
            return self.dto(self.get(ident))
        token, ids = claim
        try:
            return self.process(ident, token, ids)
        except Exception:
            self.db.rollback()
            # Fail only our own fenced claim; never overwrite another worker's result.
            batch = self.get(ident, lock=True)
            if batch.owner == token:
                for item in self.db.scalars(
                    select(Item).where(Item.id.in_(ids), Item.state == "RUNNING")
                ):
                    item.state = "ERROR"
                    item.history = item.history + [
                        {
                            "action": "ROLLED_BACK",
                            "at": now().isoformat(),
                            "actor": self.actor,
                        }
                    ]
                    item.error = {
                        "message": "El paso se revirtió completamente. Revisá el lote antes de reintentar; no se guardaron fichas."
                    }
                batch.owner = None
                batch.lease_until = None
                batch.state = "ERROR"
                self.event(batch, "STEP_ROLLED_BACK")
                self.db.commit()
            raise

    def retry(self, ident, revision):
        batch = self.get(ident, lock=True)
        if (
            batch.revision != revision
            or batch.owner
            or not batch.authorized_at
            or batch.state == "CANCELLED"
        ):
            raise ValueError("El lote cambió, está ocupado o fue cancelado.")
        rows = self.db.scalars(
            select(Item).where(
                Item.batch_id == ident,
                Item.state == "ERROR",
                Item.attempts < self.config.kiki_editorial_max_attempts,
            )
        ).all()
        if not rows:
            raise ValueError(
                "No hay errores recuperables dentro del límite de intentos."
            )
        for item in rows:
            item.state = "PENDING"
            item.error = {}
            item.history = item.history + [
                {
                    "action": "RETRY_AUTHORIZED",
                    "at": now().isoformat(),
                    "actor": self.actor,
                }
            ]
        batch.state = "PENDING"
        self.event(batch, "RETRY_AUTHORIZED", {"items": len(rows)})
        self.db.commit()
        return self.dto(batch)
