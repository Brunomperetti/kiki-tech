"""One durable catalogue workflow over the existing documentary intake queue.

Search results are references, never facts. Only explicitly authorized domains
may be downloaded by the established guarded importer. Originals and extracted
facts remain PENDING until independent human review. Deterministic proposals
reuse approved facts and existing persistence; no editor or provider writes.
"""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from uuid import UUID, uuid4

from sqlalchemy import select, text, func, cast, Text, bindparam
from sqlalchemy.exc import IntegrityError

from app.database.models import EcommApiProductEdit, KikiAiEditorialDraft
from app.integrations.ecomm_app.api_catalog_browser import valid_variant_id
from app.services.editorial_batches.context import sources, AtomicSession
from .source_fetch import target
from .source_intake_storage import SourceIntakeJob
from .source_intake_queue import SourceIntakeQueue, now, _processing
from .source_intake_pipeline import (
    PipelineError,
    identity_pin,
    check_identity,
    receipt_for_document,
)
from .storage import Document, Dossier, digest
from .explicit_url_intake import import_explicit_url
from .proposals import Proposals, MODEL

MAX_ITEMS = 20
MAX_SEARCH_REQUESTS = 20
MAX_METADATA_BYTES = 128 * 1024


def _selection(ids):
    if (
        not isinstance(ids, list)
        or not 1 <= len(ids) <= MAX_ITEMS
        or len(set(ids)) != len(ids)
        or any(not isinstance(i, str) or not valid_variant_id(i) for i in ids)
    ):
        raise ValueError("Seleccioná entre 1 y 20 variantes Ecomm API distintas.")
    return sorted(ids)


def _fresh(source, *, days=30, confirmed_at=None, observed_at=None):
    value = (
        source.get("reviewed_at")
        or source.get("declared_consulted_at")
        or source.get("registered_at")
    )
    try:
        when = datetime.fromisoformat(value) if value else confirmed_at or observed_at
        if when is None:
            return False
        if (
            confirmed_at is not None
            and source.get("review_state") == "REVIEWED"
            and confirmed_at > when
        ):
            when = confirmed_at
        if observed_at is not None and observed_at > when:
            when = observed_at
        return when.tzinfo is not None and now() - timedelta(days=days) < when <= now()
    except (TypeError, ValueError, OverflowError):
        return False


def _observed_sources(db, ids):
    """Freshness receipts for unchanged bytes, never new human approvals."""
    if db.bind.dialect.name == "postgresql":
        query = """SELECT d.ecomm_id,e->'detail'->>'document_id',e->'detail'->>'document_version',
            e->'detail'->>'document_hash',e->'detail'->>'document_sha256',e->'detail'->>'reference_url',
            MAX(e->'detail'->>'observed_at') FROM kiki_evidence_dossiers d,
            LATERAL json_array_elements(d.history) e
            WHERE e->>'action'='SOURCE_UNCHANGED_OBSERVED' AND COALESCE(e->>'actor','')<>''
            GROUP BY 1,2,3,4,5,6 LIMIT 10001"""
    else:
        query = """SELECT d.ecomm_id,json_extract(e.value,'$.detail.document_id'),
            CAST(json_extract(e.value,'$.detail.document_version') AS TEXT),
            json_extract(e.value,'$.detail.document_hash'),json_extract(e.value,'$.detail.document_sha256'),
            json_extract(e.value,'$.detail.reference_url'),MAX(json_extract(e.value,'$.detail.observed_at'))
            FROM kiki_evidence_dossiers d,json_each(d.history) e
            WHERE json_extract(e.value,'$.action')='SOURCE_UNCHANGED_OBSERVED'
                AND COALESCE(json_extract(e.value,'$.actor'),'')<>''
            GROUP BY 1,2,3,4,5,6 LIMIT 10001"""
    query = query.replace("GROUP BY", "AND d.ecomm_id IN :selected GROUP BY")
    statement = text(query).bindparams(bindparam("selected", expanding=True))
    rows = db.execute(statement, {"selected": ids}).all()
    if len(rows) > 10000:
        raise ValueError(
            "Las observaciones archivadas superan el límite de evaluación."
        )
    result = {}
    for ident, doc, version, checksum, original, url, observed in rows:
        try:
            when = datetime.fromisoformat(observed)
            if when.tzinfo is not None:
                result[(ident, doc, str(version), checksum, original, url)] = when
        except (ValueError, TypeError):
            pass
    return result


class CatalogAutomation:
    def __init__(
        self,
        db,
        session,
        searcher,
        configured_hosts,
        *,
        max_search_requests=20,
        network_enabled=False,
        daily_search_limit=20,
        readiness_check=None,
    ):
        if session is None or not getattr(session, "id", None):
            raise ValueError("La automatización requiere sesión autenticada.")
        if (
            type(max_search_requests) is not int
            or not 1 <= max_search_requests <= MAX_SEARCH_REQUESTS
        ):
            raise ValueError("Límite de búsquedas inválido: entre 1 y 20 por lote.")
        self.db, self.session, self.searcher = db, session, searcher
        self.queue = SourceIntakeQueue(db, session, configured_hosts)
        if type(daily_search_limit) is not int or not 1 <= daily_search_limit <= 200:
            raise ValueError("Límite diario de búsquedas inválido: entre 1 y 200.")
        self.daily_search_limit = daily_search_limit
        self.max_search_requests = max_search_requests
        self.network_enabled = network_enabled is True
        self.readiness_check = readiness_check

    def _before_network(self):
        if not self.network_enabled:
            raise PipelineError(
                "PROVIDERS_DISABLED",
                "Las consultas externas están desactivadas; no se consultó Internet.",
            )
        if self.readiness_check is not None:
            try:
                ready = self.readiness_check()
            except Exception:
                ready = False
            if not ready:
                raise PipelineError(
                    "READER_UNAVAILABLE",
                    "El lector aislado o la configuración de captura no están disponibles; no se consultó ningún proveedor.",
                    retryable=True,
                )

    def _job(self, ident, *, locked=False):
        job = self.queue._get(ident, locked=locked)
        if not job.items or any(
            row.get("source_mode") != "AUTOMATED_SEARCH" for row in job.items
        ):
            raise ValueError("El lote no pertenece al circuito integral.")
        return job

    def create(self, request_key, ids):
        ids = _selection(ids)
        try:
            if str(UUID(request_key)) != request_key:
                raise ValueError
        except (ValueError, TypeError, AttributeError):
            raise ValueError("La solicitud necesita una clave UUID nueva.") from None
        existing = self.db.scalar(
            select(SourceIntakeJob).where(SourceIntakeJob.request_key == request_key)
        )
        if existing:
            if [r["ecomm_id"] for r in existing.items] != ids or any(
                r.get("source_mode") != "AUTOMATED_SEARCH" for r in existing.items
            ):
                raise ValueError("La clave de solicitud pertenece a otra selección.")
            return self.detail(existing.id)
        from app.services.monthly_catalog_reports import (
            review_policy,
            _reconfirmed_dates,
        )

        evidence_days = review_policy(self.db)["settings"]["evidence_max_age_days"]
        reconfirmed = _reconfirmed_dates(self.db)
        observed = _observed_sources(self.db, ids)
        catalog = sources(self.db)
        if any(i not in catalog for i in ids):
            raise ValueError(
                "La selección no pertenece a la captura API completa actual."
            )
        rows = []
        for ident in ids:
            identity = identity_pin(catalog[ident])
            row = {
                "ecomm_id": ident,
                "url": "",
                "source_mode": "AUTOMATED_SEARCH",
                "provenance_note": "Referencia candidata obtenida por búsqueda configurada; procedencia e identidad sin aprobar.",
                "identity_schema": 2,
                "expected_identity_v2": identity,
                "identity_digest": digest(identity),
                "expected_identity": [],
                "state": "PENDING",
                "attempts": 0,
                "document_id": None,
                "error": None,
                "next_action": "SEARCH",
                "claim_token": None,
                "claim_until": None,
                "automation": {
                    "schema_version": 1,
                    "phase": "RESEARCH",
                    "search_requests": 0,
                    "search_limit": self.max_search_requests,
                    "search_daily_counts": {},
                    "search": None,
                    "proposal": None,
                    "official_verified": False,
                    "facts_approved": 0,
                    "commercial_fields_saved": 0,
                },
            }
            try:
                check_identity(row, catalog)
                size = (
                    func.octet_length(cast(Document.body, Text))
                    if self.db.bind.dialect.name == "postgresql"
                    else func.length(cast(Document.body, Text)) * 4
                )
                count, byte_count = self.db.execute(
                    select(func.count(), func.coalesce(func.sum(size), 0)).where(
                        Document.body["associated_ecomm_id"].as_string() == ident
                    )
                ).one()
                if count > 10 or byte_count > 8 * 1024 * 1024:
                    raise PipelineError(
                        "CACHED_SOURCE_LIMIT",
                        "Demasiados originales o contenido excesivo para evaluar automáticamente; revisá las fuentes de esta variante.",
                    )
                cached = self.db.scalars(
                    select(Document).where(
                        Document.body["associated_ecomm_id"].as_string() == ident
                    )
                ).all()
                usable, refreshable = [], []
                for doc in cached:
                    url = (doc.body.get("source") or {}).get("reference_url")
                    try:
                        target(url, self.queue.hosts)
                        candidate = {**row, "url": url}
                        receipt = receipt_for_document(
                            self.db, candidate, doc.id, allow_current=True
                        )
                        if _fresh(
                            (doc.body or {}).get("source") or {},
                            days=evidence_days,
                            confirmed_at=reconfirmed.get(
                                (ident, doc.id, str(doc.version), doc.digest)
                            ),
                            observed_at=observed.get(
                                (
                                    ident,
                                    doc.id,
                                    str(doc.version),
                                    doc.digest,
                                    (doc.body.get("original") or {}).get("sha256"),
                                    url,
                                )
                            ),
                        ):
                            usable.append((doc, url, receipt))
                        elif (doc.body.get("original") or {}).get(
                            "content_type"
                        ) == "text/html":
                            refreshable.append((doc, url, receipt))
                    except (ValueError, TypeError):
                        continue
                if len(usable) > 1:
                    raise PipelineError(
                        "AMBIGUOUS_CACHED_SOURCES",
                        "Existen varios originales vigentes; elegí y contrastá sus fuentes manualmente.",
                    )
                if usable:
                    doc, row["url"], receipt = usable[0]
                    row["document_id"] = doc.id
                    row["processing"] = {**_processing(row), **receipt}
                    row["automation"]["reused_original"] = True
                    row["next_action"] = "PROCESS_ARCHIVED_ORIGINAL"
                elif len(refreshable) > 1:
                    raise PipelineError(
                        "AMBIGUOUS_CACHED_SOURCES",
                        "Hay varios originales vencidos; elegí una fuente exacta antes de actualizarlos.",
                    )
                elif refreshable:
                    doc, row["url"], receipt = refreshable[0]
                    if doc.version >= 8:
                        raise PipelineError(
                            "DOCUMENT_VERSION_LIMIT",
                            "El original agotó las ocho versiones permitidas; requiere archivo y revisión manual, sin desactivar límites.",
                        )
                    row["automation"]["refresh_receipt"] = {
                        "document_id": doc.id,
                        "document_version": doc.version,
                        "document_digest": doc.digest,
                        "document_sha256": (doc.body.get("original") or {}).get(
                            "sha256"
                        ),
                    }
                    row["automation"]["phase"] = "REFRESH_REQUIRED"
                    row["next_action"] = "RECHECK_AUTHORIZED_SOURCE"

            except PipelineError as error:
                row.update(
                    state="BLOCKED",
                    error=error.public_message,
                    next_action="REVIEW_IDENTITY",
                )
                row["processing"] = {
                    **_processing(row),
                    "phase": "BLOCKED",
                    "error_code": error.code,
                    "retryable": False,
                }
            rows.append(row)
        instant = now()
        job = SourceIntakeJob(
            id=str(uuid4()),
            request_key=request_key,
            created_at=instant,
            updated_at=instant,
            creator=self.queue.actor,
            revision=1,
            state="PENDING",
            sitemap_url="",
            source_host="",
            sitemap_sha256=digest({"ids": ids, "schema": 1}),
            items=rows,
            history=[
                {
                    "action": "AUTOMATION_CREATED",
                    "at": instant.isoformat(),
                    "by": self.queue.actor,
                    "automatic_approvals": 0,
                    "search_limit": self.max_search_requests,
                }
            ],
        )
        self.db.add(job)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            existing = self.db.scalar(
                select(SourceIntakeJob).where(
                    SourceIntakeJob.request_key == request_key
                )
            )
            if existing and [r["ecomm_id"] for r in existing.items] == ids:
                return self.detail(existing.id)
            raise ValueError(
                "Otra sesión creó esta solicitud; actualizá el lote."
            ) from None
        return self.detail(job.id)

    def _resolve(self, ident, ecomm_id, token):
        self._before_network()
        # Distinct global quota lock; never held during outbound HTTP. It is
        # acquired before Control/job and released by the durable reservation.
        if self.db.bind.dialect.name == "postgresql":
            self.db.execute(text("SELECT pg_advisory_xact_lock(641532207117)"))
        job = self._job(ident, locked=True)
        rows = deepcopy(job.items)
        row = next(r for r in rows if r["ecomm_id"] == ecomm_id)
        if row["state"] != "RUNNING" or row["claim_token"] != token:
            raise ValueError("El proceso perdió la propiedad del paso.")
        metadata = row["automation"]
        if (
            sum(r["automation"]["search_requests"] for r in rows)
            >= metadata["search_limit"]
        ):
            raise PipelineError(
                "SEARCH_BUDGET_EXHAUSTED",
                "Se alcanzó el límite persistente de consultas del lote; requiere revisión.",
            )
        check_identity(row, sources(self.db))
        today = now().astimezone(timezone.utc).date().isoformat()
        if self.db.bind.dialect.name == "postgresql":
            used = self.db.scalar(
                text(
                    "SELECT COALESCE(SUM(COALESCE((entry->'automation'->'search_daily_counts'->>:day)::integer,0)),0) FROM kiki_source_intake_jobs CROSS JOIN LATERAL json_array_elements(items) entry"
                ),
                {"day": today},
            )
        else:
            used = sum(
                (item.get("automation") or {})
                .get("search_daily_counts", {})
                .get(today, 0)
                for items in self.db.scalars(select(SourceIntakeJob.items))
                for item in items
            )
        if used >= self.daily_search_limit:
            raise PipelineError(
                "GLOBAL_SEARCH_DAILY_BUDGET",
                "Se alcanzó el límite diario global de búsquedas; no se consultó el proveedor.",
            )
        counts = metadata.get("search_daily_counts") or {}
        yesterday = (
            now().astimezone(timezone.utc).date() - timedelta(days=1)
        ).isoformat()
        metadata["search_daily_counts"] = {
            key: value for key, value in counts.items() if key in {today, yesterday}
        }
        metadata["search_daily_counts"][today] = counts.get(today, 0) + 1
        metadata["search_requests"] += 1
        metadata["phase"] = "SEARCHING"
        self.queue._update(job, rows, "SEARCH_RESERVED")
        identity = deepcopy(row["expected_identity_v2"])
        identity.update(
            name=identity.get("product_name"),
            presentation=identity.get("variant_description"),
        )
        self._before_network()
        try:
            result = self.searcher.search(identity)
        except Exception:
            raise PipelineError(
                "SEARCH_UNAVAILABLE",
                "No se pudo completar la búsqueda configurada; sin resultados verificados ni reintentos automáticos.",
                retryable=True,
            ) from None
        if (
            not isinstance(result, dict)
            or not isinstance(result.get("results"), list)
            or len(result["results"]) > 10
        ):
            raise PipelineError(
                "SEARCH_RESPONSE_INVALID",
                "La respuesta de búsqueda no cumple el contrato limitado.",
            )
        candidates, authorized = [], []
        for found in result["results"]:
            if (
                not isinstance(found, dict)
                or not isinstance(found.get("url"), str)
                or len(found["url"]) > 1000
            ):
                continue
            clean = {
                "url": found["url"][:1000],
                "title": str(found.get("title") or "")[:300],
                "snippet": str(found.get("snippet") or "")[:1000],
                "source_kind": "OFFICIAL_CANDIDATE"
                if found.get("source_kind") == "OFFICIAL_CANDIDATE"
                else "SECONDARY",
                "official_verified": False,
                "evidence_approved": False,
            }
            candidates.append(clean)
            try:
                target(clean["url"], self.queue.hosts)
                if clean["source_kind"] == "OFFICIAL_CANDIDATE":
                    authorized.append(clean)
            except (ValueError, TypeError):
                pass
        authorized = list({row["url"]: row for row in authorized}.values())
        job = self._job(ident, locked=True)
        rows = deepcopy(job.items)
        row = next(r for r in rows if r["ecomm_id"] == ecomm_id)
        if row["state"] != "RUNNING" or row["claim_token"] != token:
            raise ValueError("El proceso perdió la propiedad del paso.")
        check_identity(row, sources(self.db))
        row["automation"]["search"] = {
            "queried_at": str(result.get("queried_at") or "")[:40],
            "provider": str(result.get("provider") or "CONFIGURED")[:30],
            "results": candidates,
            "official_verified": False,
            "cost_known": False,
        }
        if (
            len(json.dumps(row["automation"], ensure_ascii=False).encode())
            > MAX_METADATA_BYTES
        ):
            raise PipelineError(
                "SEARCH_RESPONSE_INVALID",
                "Las referencias exceden el límite de metadatos.",
            )
        if len(authorized) == 1:
            row["url"] = authorized[0]["url"]
            row["automation"]["phase"] = "SOURCE_SELECTED_PENDING_REVIEW"
        self.queue._update(job, rows, "SEARCH_CANDIDATES_RECORDED")
        if len(authorized) != 1:
            raise PipelineError(
                "AMBIGUOUS_SEARCH_RESULTS" if authorized else "NO_AUTHORIZED_SOURCE",
                "Hay varias fuentes candidatas; requieren selección humana."
                if authorized
                else "No se encontró una fuente candidata en dominios autorizados; revisar las referencias secundarias.",
            )
        return deepcopy(row)

    def _proposals(self, ident, expected_revision=None):
        # Match the shared editor/Context ordering: lock all commercial rows
        # before the documentary mutex. Job claims commit before this stage.
        current = self._job(ident)
        ids = sorted(row["ecomm_id"] for row in current.items)
        self.db.scalars(
            select(EcommApiProductEdit)
            .where(EcommApiProductEdit.ecomm_id.in_(ids))
            .order_by(EcommApiProductEdit.ecomm_id)
            .with_for_update()
        ).all()
        job = self._job(ident, locked=True)
        if expected_revision is not None and job.revision != expected_revision:
            raise ValueError(
                "El lote cambió; recuperá la revisión nueva antes de preparar propuestas."
            )
        if job.state == "CANCELLED" or any(
            row["state"] == "RUNNING" for row in job.items
        ):
            raise ValueError(
                "El lote está cancelado o tiene un paso activo; no se prepararon propuestas."
            )
        rows = deepcopy(job.items)
        changed = False
        for row in rows:
            metadata = row["automation"]
            if row["state"] not in {"IMPORTED", "ALREADY_PRESENT"}:
                continue
            dossier = self.db.get(Dossier, row["ecomm_id"])
            if not dossier or not any(
                f.get("state") == "APPROVED" for f in dossier.facts
            ):
                if metadata.get("phase") != "HUMAN_EVIDENCE_REVIEW":
                    metadata["phase"] = "HUMAN_EVIDENCE_REVIEW"
                    changed = True
                continue
            try:
                check_identity(row, sources(self.db))
            except PipelineError:
                metadata["phase"] = "IDENTITY_REVIEW_REQUIRED"
                metadata["proposal"] = None
                changed = True
                continue
            service = Proposals(AtomicSession(self.db), self.session)
            edit, item, facts, fingerprint = service.context(row["ecomm_id"])
            existing = self.db.scalar(
                select(KikiAiEditorialDraft)
                .where(
                    KikiAiEditorialDraft.product_key
                    == service.product_prefix + row["ecomm_id"],
                    KikiAiEditorialDraft.model == MODEL,
                    KikiAiEditorialDraft.source_hash == fingerprint,
                    KikiAiEditorialDraft.review_status.in_(
                        ("PENDING_REVIEW", "REVIEWED", "APPLIED")
                    ),
                )
                .order_by(KikiAiEditorialDraft.id.desc())
                .limit(1)
            )
            if (
                existing
                and existing.review_status == "APPLIED"
                and service.meta(existing).get("identity_hash") == item.identity_digest
            ):
                metadata["proposal"] = {"draft_id": existing.id, "reused": True}
                metadata["phase"] = "INTERNAL_DRAFT_ALREADY_SAVED"
            elif existing and not service.validity(existing, edit, item, fingerprint):
                metadata["proposal"] = {"draft_id": existing.id, "reused": True}
                metadata["phase"] = "HUMAN_FIELD_REVIEW"
            else:
                try:
                    proposal = service.generate(
                        row["ecomm_id"],
                        edit["version"],
                        only_missing=True,
                        batch_reference={
                            "batch_id": job.id,
                            "kind": "CATALOG_AUTOMATION",
                        },
                    )
                    metadata["proposal"] = {
                        "draft_id": proposal["draft_id"],
                        "reused": False,
                    }
                    metadata["phase"] = "HUMAN_FIELD_REVIEW"
                except ValueError:
                    metadata["phase"] = "HUMAN_EVIDENCE_REVIEW"
            changed = True
        if changed:
            return self.queue._update(
                job, rows, "PROPOSALS_PREPARED_FROM_APPROVED_FACTS"
            )
        self.db.rollback()
        return self.queue.detail(ident)

    def step(self, ident, revision, *, explicit_importer=import_explicit_url):
        self._job(ident)

        def guarded_importer(*args, **kwargs):
            self._before_network()
            return explicit_importer(*args, **kwargs)

        self.queue.step(
            ident,
            revision,
            explicit_importer=guarded_importer,
            source_resolver=self._resolve,
        )
        self._proposals(ident)
        return self.detail(ident)

    def select_source(self, ident, revision, ecomm_id, url, reason):
        from .automation_source_selection import select_source

        return select_source(self, ident, revision, ecomm_id, url, reason)

    def prepare_proposals(self, ident, revision):
        self._proposals(ident, expected_revision=revision)
        return self.detail(ident)

    def detail(self, ident):
        return self._decorate(self.queue._serialize(self._job(ident)))

    def _decorate(self, report):
        report["mode"] = "CATALOG_AUTOMATION_EXISTING_DOCUMENTARY_QUEUE"
        report["search_requests"] = sum(
            (r.get("automation") or {}).get("search_requests", 0)
            for r in report["items"]
        )
        report["search_request_measurement"] = (
            "RESERVED_ATTEMPTS_INCLUDING_INTERRUPTED_CALLS"
        )
        report["paid_ai_enabled"] = False
        report["automatic_fact_approvals"] = report["commercial_fields_saved"] = 0
        for row in report["items"]:
            phase = (row.get("automation") or {}).get("phase")
            if phase == "IDENTITY_REVIEW_REQUIRED":
                row["public_state"] = "BLOCKED"
            elif phase == "INTERNAL_DRAFT_ALREADY_SAVED":
                row["public_state"] = "DRAFT_SAVED"
            elif phase == "HUMAN_FIELD_REVIEW":
                row["public_state"] = "PROPOSAL_REVIEW_REQUIRED"
            elif phase == "HUMAN_EVIDENCE_REVIEW":
                row["public_state"] = "EVIDENCE_REVIEW_REQUIRED"
        return report

    def listing(self):
        from .source_intake_queue import _summary

        active = (
            "EXISTS (SELECT 1 FROM json_array_elements(items) AS entry WHERE entry->>'state'='RUNNING')"
            if self.db.bind.dialect.name == "postgresql"
            else "EXISTS (SELECT 1 FROM json_each(items) AS entry WHERE json_extract(entry.value,'$.state')='RUNNING')"
        )
        jobs = self.db.scalars(
            select(SourceIntakeJob)
            .where(
                SourceIntakeJob.items[0]["source_mode"].as_string()
                == "AUTOMATED_SEARCH"
            )
            .order_by(
                text("CASE WHEN " + active + " THEN 0 ELSE 1 END"),
                SourceIntakeJob.created_at.desc(),
            )
            .limit(20)
        ).all()
        ids = {
            row["document_id"]
            for job in jobs
            for row in job.items
            if row.get("document_id")
        }
        versions = (
            {
                row.id: (row.version, row.digest)
                for row in self.db.execute(
                    select(Document.id, Document.version, Document.digest).where(
                        Document.id.in_(ids)
                    )
                )
            }
            if ids
            else {}
        )
        return {
            "items": [self._decorate(_summary(job, versions)) for job in jobs],
            "external_writes_enabled": False,
            "paid_ai_enabled": False,
        }
