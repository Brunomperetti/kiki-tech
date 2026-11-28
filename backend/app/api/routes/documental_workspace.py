"""Authenticated documental workspace. No provider clients or startup DDL."""

from datetime import datetime, timezone
import base64
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.core.security import require_session, require_csrf
from app.database.session import get_db
from app.services.documental.research import Research
from app.services.documental.proposals import Proposals
from app.services.documental.contracts import CommercialReviewPreview, CommercialReviewApply
from app.services.documental.commercial_review import CommercialReview
from app.services.documental.commercial_plan import commercial_plan
from app.services.documental.reextract_reviewed_batch import extract_reviewed_selection
from app.services.documental.source_links import suggest_reviewed_sources
from app.services.documental.local_documents import LocalDocuments, parse_local, reader_available
from app.services.documental.source_fetch import fetch_html
from app.services.documental.explicit_url_intake import import_explicit_url
from app.services.documental.sitemap_discovery import preview_candidates
from app.services.documental.manufacturer_batch_intake import capture_selected
from app.services.documental.source_intake_queue import SourceIntakeQueue
from app.services.documental.source_intake_storage import SourceIntakeJob
from app.services.documental.source_intake_report import (
    build_intake_report, export_intake_exceptions,
)
from app.api.routes.commercial_exports import csv_response
from sqlalchemy import inspect
from uuid import UUID
from app.services.documental.contracts import (
    Extract,
    Review as ProposalReview,
    Generate,
    Incorporate,
    Provenance,
)
from app.services.documental.contracts import FactReview, BatchFactReview
from app.services.documental.contracts import DocumentIdentityReview, ManufacturerFetch, MediaRightsReview
from app.services.documental.media_rights import review_media_rights


def enabled():
    if not get_settings().kiki_document_workspace_enabled:
        raise HTTPException(
            403,
            "Espacio documental deshabilitado; requiere revisión de configuración y migración.",
        )


router = APIRouter(
    prefix="/api/ecomm-app/workspace",
    tags=["documental-workspace"],
    dependencies=[Depends(enabled)],
)


def execute(db, operation):
    try:
        return operation()
    except ValueError as exc:
        # The shared service can persist automatic evidence invalidations before CAS fails.
        db.commit()
        raise HTTPException(409, str(exc)) from None


class ReviewExistingDocumentsRequest(BaseModel):
    """Manual operation. Does not approve any individual facts or publish."""

    model_config = ConfigDict(extra="forbid")
    ecomm_ids: list[str] = Field(min_length=1, max_length=20)
    confirm: Literal[True]


@router.post("/sources/reextract-reviewed")
def reextract_reviewed_originals(
    body: ReviewExistingDocumentsRequest,
    db: Session = Depends(get_db),
    session=Depends(require_csrf),
):
    """Extract pending claims only from one reviewed original per API variant."""
    try:
        return extract_reviewed_selection(db, session, body.ecomm_ids)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from None
    except Exception:
        db.rollback()
        raise


@router.get("/{ecomm_id}/evidence")
def evidence(
    ecomm_id: str, db: Session = Depends(get_db), session=Depends(require_session)
):
    def operation():
        service = Research(db, session)
        return service.serialize(service.dossier(ecomm_id))

    return execute(db, operation)


@router.get("/{ecomm_id}/sources/suggestions")
def suggest_sources(
    ecomm_id: str, db: Session = Depends(get_db), session=Depends(require_session)
):
    """No publication, approval, source upload or commercial write."""
    return execute(
        db,
        lambda: suggest_reviewed_sources(Research(db, session), ecomm_id),
    )


@router.post("/{ecomm_id}/evidence/extract")
def extract(
    ecomm_id: str,
    body: Extract,
    db: Session = Depends(get_db),
    session=Depends(require_csrf),
):
    return execute(
        db,
        lambda: Research(db, session).extract(
            ecomm_id, body.expected_version, body.document_id, body.document_version
        ),
    )


@router.post("/{ecomm_id}/evidence/facts/{fact_id}/review")
def review_fact(
    ecomm_id: str,
    fact_id: str,
    body: FactReview,
    db: Session = Depends(get_db),
    session=Depends(require_csrf),
):
    return execute(
        db,
        lambda: Research(db, session).review(
            ecomm_id,
            body.expected_version,
            fact_id,
            body.expected_fact_version,
            body.decision,
            body.reason,
        ),
    )


@router.post("/{ecomm_id}/evidence/facts/review-batch")
def review_facts_batch(
    ecomm_id: str,
    body: BatchFactReview,
    db: Session = Depends(get_db),
    session=Depends(require_csrf),
):
    """Single explicit human decision for checked facts, no automatic approval."""
    try:
        return Research(db, session).review_batch(
            ecomm_id,
            body.expected_version,
            body.document_id,
            body.document_version,
            body.facts,
        )
    except ValueError as exc:
        # A failed batch must not commit even an incidental pending ORM change.
        db.rollback()
        raise HTTPException(409, str(exc)) from None


@router.post("/{ecomm_id}/documents/{document_id}/identity-review")
def review_identity(
    ecomm_id: str,
    document_id: str,
    body: DocumentIdentityReview,
    db: Session = Depends(get_db),
    session=Depends(require_csrf),
):
    """A reviewed source may have a different commercial name, never a different SKU."""
    return execute(
        db,
        lambda: Research(db, session).review_document_identity(
            ecomm_id, body.expected_version, document_id,
            body.document_version, body.decision, body.reason,
        ),
    )


@router.post("/{ecomm_id}/documents/{document_id}/media-rights")
def review_asset_permissions(
    ecomm_id: str,
    document_id: str,
    body: MediaRightsReview,
    db: Session = Depends(get_db),
    session=Depends(require_csrf),
):
    """Review an explicit original written grant for a specific asset URL."""
    def operation():
        service = Proposals(db, session)
        service.lock_edit(ecomm_id)
        return review_media_rights(
            service.research,
            ecomm_id, body.expected_version, document_id, body.document_version,
            body.media_url, body.media_kind, body.source_url, body.decision,
            body.licence_basis, body.location, body.quote, body.reason,
            alt_text=body.alt_text, presentation=body.presentation,
            valid_until=body.valid_until,
            expected_workspace_version=body.expected_workspace_version,
        )

    return execute(db, operation)


@router.post("/{ecomm_id}/documents/fetch-manufacturer")
def fetch_manufacturer(
    ecomm_id: str,
    body: ManufacturerFetch,
    db: Session = Depends(get_db),
    session=Depends(require_csrf),
):
    """One allowlisted public HTML source, no bulk or provider writes."""
    config = get_settings()
    if (
        not config.kiki_document_source_fetch_enabled
        or not config.kiki_document_source_fetch_hosts.strip()
        or ecomm_id != config.kiki_document_source_fetch_pilot_id
    ):
        raise HTTPException(
            403, "Consulta automática deshabilitada o fuera de la variante piloto."
        )

    def operation():
        try:
            # Fail before making an external request if the isolated reader,
            # source identity or optimistic version is unavailable.
            if (
                not config.kiki_document_parser_kernel_required
                or not reader_available()
            ):
                raise ValueError(
                    "Lector documental aislado obligatorio antes de consultar al fabricante."
                )
            research = Research(db, session)
            item = research.dossier(ecomm_id)
            research.expect(item, body.expected_version)
            today = datetime.now(timezone.utc).date()
            for event in item.history or []:
                if (
                    event.get("action") == "DOCUMENT_INCORPORATED"
                    and (event.get("detail") or {}).get("source_fetched")
                ):
                    try:
                        date = datetime.fromisoformat(event["at"]).date()
                    except (KeyError, TypeError, ValueError):
                        raise ValueError("Historial de consultas inválido; contacto externo bloqueado.") from None
                    if date == today:
                        raise ValueError(
                            "El piloto admite una consulta automática diaria por variante."
                        )
            original, receipt = fetch_html(
                body.reference_url, config.kiki_document_source_fetch_hosts
            )
            imported = Incorporate(
                kind="FILE",
                web_snapshot=True,
                expected_version=body.expected_version,
                filename="fabricante-" + receipt["sha256"][:16] + ".html",
                content_type="text/html",
                content_base64=base64.b64encode(original).decode("ascii"),
                provenance_note=body.provenance_note,
                reference_url=body.reference_url,
                declared_official=False,
                declared_consulted_at=datetime.now(timezone.utc),
                authorized_local_processing=True,
            )
            parsed = parse_local(imported)
            db.expire_all()  # Re-read versions before the mutation after slow I/O.
            return LocalDocuments(db, session).incorporate(
                ecomm_id, imported, parsed, source_retrieval=receipt
            )

        except Exception:
            # A denied robots.txt or failed parse must not commit even an
            # empty research dossier. execute() may commit safe invalidations.
            db.rollback()
            raise

    return execute(db, operation)



@router.post("/{ecomm_id}/documents/fetch-reviewed-url")
def fetch_exact_reviewed_manufacturer_url(
    ecomm_id: str,
    body: ManufacturerFetch,
    db: Session = Depends(get_db),
    session=Depends(require_csrf),
):
    """One manually chosen URL: HTTPS, robots, no redirects, PENDING original.

    Does NOT require an XML sitemap, but cannot bypass manufacturer policy,
    identity checks, dossier optimistic lock or source approval.
    """
    config = get_settings()
    if (
        not config.kiki_document_explicit_url_intake_enabled
        or not config.kiki_document_parser_kernel_required
        or not config.kiki_document_source_fetch_hosts.strip()
        or not reader_available()
    ):
        raise HTTPException(
            403, "Captura por URL exacta deshabilitada o lector no disponible."
        )
    try:
        return import_explicit_url(
            db, session,
            ecomm_id=ecomm_id,
            expected_version=body.expected_version,
            reference_url=body.reference_url,
            provenance_note=body.provenance_note,
            configured_hosts=config.kiki_document_source_fetch_hosts,
        )
    except ValueError as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from None
    except Exception:
        db.rollback()
        raise


@router.post("/{ecomm_id}/documents/import")
def incorporate(
    ecomm_id: str,
    body: Incorporate,
    db: Session = Depends(get_db),
    session=Depends(require_csrf),
):
    def operation():
        # Validate catalogue identity before spending parser resources; no backend/provider fallback.
        service = LocalDocuments(db, session)
        service.research.dossier(ecomm_id)
        parsed = parse_local(body) if body.kind == "FILE" else None
        return service.incorporate(ecomm_id, body, parsed)

    return execute(db, operation)


class ReparseSavedHtmlRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=0)
    document_version: int = Field(ge=1)
    confirm: Literal[True]


@router.post("/{ecomm_id}/documents/{document_id}/reparse-saved-html")
def reparse_saved_html(
    ecomm_id: str,
    document_id: str,
    body: ReparseSavedHtmlRequest,
    db: Session = Depends(get_db),
    session=Depends(require_csrf),
):
    return execute(
        db, lambda: LocalDocuments(db, session).reparse_saved_html(
            ecomm_id, document_id, body.expected_version, body.document_version,
        ),
    )


@router.post("/{ecomm_id}/documents/{document_id}/provenance")
def provenance(
    ecomm_id: str,
    document_id: str,
    body: Provenance,
    db: Session = Depends(get_db),
    session=Depends(require_csrf),
):
    return execute(
        db, lambda: LocalDocuments(db, session).provenance(ecomm_id, document_id, body)
    )


@router.get("/{ecomm_id}/documents/{document_id}/original/{version}")
def original(
    ecomm_id: str,
    document_id: str,
    version: int,
    db: Session = Depends(get_db),
    session=Depends(require_session),
):
    return execute(
        db, lambda: LocalDocuments(db, session).original(ecomm_id, document_id, version)
    )


@router.get("/{ecomm_id}/proposals")
def proposals(
    ecomm_id: str,
    draft_id: int | None = Query(None, ge=1),
    db: Session = Depends(get_db),
    session=Depends(require_session),
):
    def operation():
        service = Proposals(db, session)
        if draft_id is None:
            return service.latest(ecomm_id)
        edit, item, facts, fingerprint = service.context(ecomm_id)
        return service.serialize(
            service.get_record(ecomm_id, draft_id), edit, item, facts, fingerprint
        )

    return execute(db, operation)


@router.post("/{ecomm_id}/proposals/generate")
def generate(
    ecomm_id: str,
    body: Generate,
    db: Session = Depends(get_db),
    session=Depends(require_csrf),
):
    return execute(
        db, lambda: Proposals(db, session).generate(ecomm_id, body.expected_version)
    )


@router.post("/{ecomm_id}/proposals/generate-ai")
def generate_with_ai(
    ecomm_id: str,
    body: Generate,
    db: Session = Depends(get_db),
    session=Depends(require_csrf),
):
    """Operator-initiated paid request, with the 10/day shared quota and cited facts."""
    return execute(
        db, lambda: Proposals(db, session).generate_ai(ecomm_id, body.expected_version)
    )


@router.post("/{ecomm_id}/proposals/{draft_id}/review")
def review_proposal(
    ecomm_id: str,
    draft_id: int,
    body: ProposalReview,
    db: Session = Depends(get_db),
    session=Depends(require_csrf),
):
    return execute(
        db,
        lambda: Proposals(db, session).review(
            ecomm_id,
            draft_id,
            body.expected_revision,
            {k: v.model_dump() for k, v in body.decisions.items()},
        ),
    )


@router.get("/{ecomm_id}/proposals/generation-context")
def generation_context(
    ecomm_id: str, db: Session = Depends(get_db), session=Depends(require_session)
):
    from app.services.documental.generation_contract import (
        generation_context as context,
    )

    return execute(db, lambda: context(db, session, ecomm_id))


class SitemapCandidatesRequest(BaseModel):
    """Explicit operator request, no provider writes and no unattended crawl."""

    model_config = ConfigDict(extra="forbid")
    sitemap_url: str = Field(min_length=15, max_length=1000)
    ecomm_ids: list[str] = Field(min_length=1, max_length=20)


@router.post("/sources/sitemap-preview")
def preview_manufacturer_sitemap(
    body: SitemapCandidatesRequest,
    db: Session = Depends(get_db),
    session=Depends(require_csrf),
):
    """Look up up to 20 variants in one authorized manufacturer XML index.

    Candidates are not evidence or product identity confirmations. This
    endpoint never imports documents, calls AI or changes provider data.
    """
    config = get_settings()
    if (
        not config.kiki_document_sitemap_discovery_enabled
        or not config.kiki_document_source_fetch_hosts.strip()
    ):
        raise HTTPException(403, "Descubrimiento de fabricante deshabilitado.")
    try:
        return preview_candidates(
            db, body.ecomm_ids, body.sitemap_url,
            config.kiki_document_source_fetch_hosts,
        )
    except ValueError as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from None


class ManufacturerBatchItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ecomm_id: str = Field(pattern=r"^[1-9][0-9]{0,19}$")
    url: str = Field(min_length=16, max_length=1000)


class ManufacturerBatchRequest(BaseModel):
    """Operator confirmed 1-2 exact URLs from a previously reviewed sitemap."""

    model_config = ConfigDict(extra="forbid")
    sitemap_url: str = Field(min_length=16, max_length=1000)
    sitemap_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    items: list[ManufacturerBatchItem] = Field(min_length=1, max_length=2)
    authorized_local_processing: Literal[True]
    confirm: Literal[True]


@router.post("/sources/batch-import")
def import_manufacturer_batch(
    body: ManufacturerBatchRequest,
    db: Session = Depends(get_db),
    session=Depends(require_csrf),
):
    """Opt-in explicit same-host acquisition; archives only PENDING originals.

    Does not validate official source, approve medical/commercial facts, call
    OpenAI or write to Ecomm-App / Mercado Libre / Tiendanube.
    """
    config = get_settings()
    if not (
        config.kiki_document_parser_kernel_required
        and config.kiki_document_batch_source_import_enabled
        and config.kiki_document_sitemap_discovery_enabled
        and config.kiki_document_source_fetch_hosts.strip()
        and reader_available()
    ):
        raise HTTPException(403, "Captura por lotes deshabilitada o lector aislado no disponible.")
    try:
        return capture_selected(
            db, session,
            sitemap_url=body.sitemap_url,
            sitemap_sha256=body.sitemap_sha256,
            items=[item.model_dump() for item in body.items],
            configured_hosts=config.kiki_document_source_fetch_hosts,
        )
    except ValueError as exc:
        # A preview collision, HTML parsing failure or CAS conflict must
        # not commit even an empty research dossier or partially stored files.
        db.rollback()
        raise HTTPException(409, str(exc)) from None
    except Exception:
        db.rollback()
        raise


def _resumable_intake_state_ready(db):
    """Local queue inspection/recovery never requires a downloader or network."""
    settings = get_settings()
    if not settings.kiki_document_resumable_intake_enabled:
        raise HTTPException(403, "Investigación reanudable deshabilitada.")
    if not inspect(db.get_bind()).has_table(SourceIntakeJob.__tablename__):
        raise HTTPException(503, "Falta aplicar la migración de cola documental.")
    return settings


def _resumable_intake_ready(db):
    """No implicit migration or network if the operator flag or schema is absent."""
    settings = get_settings()
    if not (
        settings.kiki_document_resumable_intake_enabled
        and (
            (settings.kiki_document_batch_source_import_enabled
             and settings.kiki_document_sitemap_discovery_enabled)
            or settings.kiki_document_explicit_url_intake_enabled
        )
        and settings.kiki_document_parser_kernel_required
        and settings.kiki_document_source_fetch_hosts.strip()
        and reader_available()
    ):
        raise HTTPException(403, "Investigación reanudable deshabilitada.")
    if not inspect(db.get_bind()).has_table(SourceIntakeJob.__tablename__):
        raise HTTPException(503, "Falta aplicar la migración de cola documental.")
    return settings


class SourceIntakeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_key: UUID
    sitemap_url: str = Field(min_length=16, max_length=1000)
    sitemap_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    items: list[ManufacturerBatchItem] = Field(min_length=1, max_length=20)
    authorized_local_processing: Literal[True]
    confirm: Literal[True]


class ExactURLManifestItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ecomm_id: str = Field(pattern=r"^[1-9][0-9]{0,19}$")
    url: str = Field(min_length=16, max_length=1000)
    provenance_note: str = Field(min_length=10, max_length=600)


class ExactURLManifestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_key: UUID
    items: list[ExactURLManifestItem] = Field(min_length=1, max_length=20)
    authorized_local_processing: Literal[True]
    identity_reviewed_by_operator: Literal[True]
    confirm: Literal[True]


class IntakeRevision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)
    confirm: Literal[True]


class IntakeRetry(IntakeRevision):
    ecomm_id: str = Field(pattern=r"^[1-9][0-9]{0,19}$")


class IntakeComplete(IntakeRetry):
    expected_document_version: int | None = Field(default=None, ge=1)
    expected_document_digest: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")


@router.get("/sources/intake-jobs")
def source_intake_jobs(
    db: Session = Depends(get_db),
    session=Depends(require_session),
):
    _resumable_intake_state_ready(db)
    return SourceIntakeQueue(db, session, "").listing()


@router.get("/sources/intake-jobs/{job_id}")
def source_intake_detail(
    job_id: UUID,
    db: Session = Depends(get_db),
    session=Depends(require_session),
):
    _resumable_intake_state_ready(db)
    try:
        return SourceIntakeQueue(db, session, "").detail(str(job_id))
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from None


@router.post("/sources/intake-jobs")
def source_intake_create(
    body: SourceIntakeRequest,
    db: Session = Depends(get_db),
    session=Depends(require_csrf),
):
    settings = _resumable_intake_ready(db)
    if not (
        settings.kiki_document_batch_source_import_enabled
        and settings.kiki_document_sitemap_discovery_enabled
    ):
        raise HTTPException(403, "Importación por sitemap desactivada.")
    try:
        return SourceIntakeQueue(
            db, session, settings.kiki_document_source_fetch_hosts,
        ).create(
            str(body.request_key), body.sitemap_url, body.sitemap_sha256,
            [row.model_dump() for row in body.items],
        )
    except ValueError as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from None
    except Exception:
        db.rollback()
        raise


@router.get("/sources/intake-jobs/{job_id}/report")
def source_intake_report(
    job_id: UUID,
    db: Session = Depends(get_db),
    session=Depends(require_session),
):
    """Recompute local evidence/version state; no download or field writes."""
    _resumable_intake_state_ready(db)
    try:
        return build_intake_report(db, session, str(job_id))
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None
    finally:
        db.rollback()


@router.get("/sources/intake-jobs/{job_id}/exceptions.csv")
def source_intake_exceptions(
    job_id: UUID,
    expected_revision: int = Query(ge=1),
    expected_fingerprint: str = Query(pattern=r"^[a-f0-9]{64}$"),
    db: Session = Depends(get_db),
    session=Depends(require_session),
):
    _resumable_intake_state_ready(db)
    try:
        report = build_intake_report(db, session, str(job_id))
        content = export_intake_exceptions(report, expected_revision, expected_fingerprint)
        return csv_response(
            content, "kiki-lote-documental-excepciones.csv", report["total"],
            report["fingerprint"],
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None
    finally:
        db.rollback()


@router.post("/sources/intake-jobs/exact-urls")
def source_intake_create_exact_urls(
    body: ExactURLManifestRequest,
    db: Session = Depends(get_db),
    session=Depends(require_csrf),
):
    """Stage a manual manifest without contacting a manufacturer."""
    settings = _resumable_intake_ready(db)
    if not settings.kiki_document_explicit_url_intake_enabled:
        raise HTTPException(403, "Investigación por URL exacta desactivada.")
    try:
        return SourceIntakeQueue(
            db, session, settings.kiki_document_source_fetch_hosts,
        ).create_explicit(
            str(body.request_key), [row.model_dump() for row in body.items],
        )
    except ValueError as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from None
    except Exception:
        db.rollback()
        raise


@router.post("/sources/intake-jobs/{job_id}/step")
def source_intake_step(
    job_id: UUID,
    body: IntakeRevision,
    db: Session = Depends(get_db),
    session=Depends(require_csrf),
):
    settings = _resumable_intake_ready(db)
    try:
        queue = SourceIntakeQueue(
            db, session, settings.kiki_document_source_fetch_hosts,
        )
        current = queue.detail(str(job_id))
        if current["selection_mode"] == "EXACT_OPERATOR_URL":
            if not settings.kiki_document_explicit_url_intake_enabled:
                raise HTTPException(403, "Captura por URL exacta desactivada.")
        elif not (
            settings.kiki_document_batch_source_import_enabled
            and settings.kiki_document_sitemap_discovery_enabled
        ):
            raise HTTPException(403, "Captura por sitemap desactivada.")
        return queue.step(str(job_id), body.expected_revision)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from None


@router.post("/sources/intake-jobs/{job_id}/retry")
def source_intake_retry(
    job_id: UUID,
    body: IntakeRetry,
    db: Session = Depends(get_db),
    session=Depends(require_csrf),
):
    settings = _resumable_intake_ready(db)
    try:
        return SourceIntakeQueue(
            db, session, settings.kiki_document_source_fetch_hosts,
        ).retry(str(job_id), body.expected_revision, body.ecomm_id)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from None


@router.post("/sources/intake-jobs/{job_id}/recover")
def source_intake_recover(
    job_id: UUID,
    body: IntakeRevision,
    db: Session = Depends(get_db),
    session=Depends(require_csrf),
):
    """Recover only expired local leases, even if the downloader is unavailable.

    This endpoint cannot fetch a page, create a document or retry a source.
    Keep the workspace/queue opt-ins and schema gate; do not require network
    or parser availability for restoring persisted coordination state.
    """
    _resumable_intake_state_ready(db)
    try:
        return SourceIntakeQueue(db, session, "").recover(
            str(job_id), body.expected_revision,
        )
    except ValueError as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from None


@router.post("/sources/intake-jobs/{job_id}/cancel")
def source_intake_cancel(
    job_id: UUID,
    body: IntakeRevision,
    db: Session = Depends(get_db),
    session=Depends(require_csrf),
):
    _resumable_intake_state_ready(db)
    try:
        return SourceIntakeQueue(db, session, "").cancel(
            str(job_id), body.expected_revision,
        )
    except ValueError as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from None


@router.post("/sources/intake-jobs/{job_id}/complete")
def source_intake_complete_archived(
    job_id: UUID,
    body: IntakeComplete,
    db: Session = Depends(get_db),
    session=Depends(require_csrf),
):
    """Recover extraction from the pinned original with the downloader disabled."""
    _resumable_intake_state_ready(db)
    try:
        return SourceIntakeQueue(db, session, "").complete_archived(
            str(job_id), body.expected_revision, body.ecomm_id,
            expected_document_version=body.expected_document_version,
            expected_document_digest=body.expected_document_digest,
        )
    except ValueError as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from None


class CommercialPlanRequest(BaseModel):
    """Read-only preview; no draft, media, category or provider mutations."""

    model_config = ConfigDict(extra="forbid")
    ecomm_ids: list[str] = Field(min_length=1, max_length=20)


@router.post("/commercial-plan/preview")
def preview_commercial_plan(
    body: CommercialPlanRequest,
    db: Session = Depends(get_db),
    session=Depends(require_csrf),
):
    """Determine per-variant next actions from current, approved evidence.

    No new document, AI draft, field approval or channel publication is saved.
    """
    try:
        result = commercial_plan(db, session, body.ecomm_ids)
        db.rollback()  # release document lock without persisting any inspection
        return result
    except ValueError as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from None
    except Exception:
        db.rollback()
        raise


@router.post("/commercial-review/preview")
def preview_editorial_selection(
    body: CommercialReviewPreview,
    db: Session = Depends(get_db),
    session=Depends(require_csrf),
):
    try:
        result = CommercialReview(db, session).preview(body.ecomm_ids)
        db.rollback()
        return result
    except ValueError as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from None
    except Exception:
        db.rollback()
        raise


@router.post("/commercial-review/apply")
def save_editorial_selection(
    body: CommercialReviewApply,
    db: Session = Depends(get_db),
    session=Depends(require_csrf),
):
    try:
        result = CommercialReview(db, session).apply(
            body.expected_fingerprint,
            [item.model_dump() for item in body.items],
            body.ecomm_ids,
        )
        db.commit()
        return result
    except ValueError as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from None
    except Exception:
        db.rollback()
        raise


@router.get("/{ecomm_id}/commercial-coverage")
def commercial_field_coverage(
    ecomm_id: str, db: Session = Depends(get_db), session=Depends(require_session),
):
    from app.services.documental.completion import saved_field_coverage

    def operation():
        service = Proposals(db, session)
        edit, item, _facts, _fingerprint = service.context(ecomm_id)
        return saved_field_coverage(
            service.research, item, edit["fields"],
            taxonomy=service.taxonomy_context(edit, item, _facts),
        )

    return execute(db, operation)


@router.get("/{ecomm_id}/media-review")
def media_review_registry(
    ecomm_id: str, db: Session = Depends(get_db), session=Depends(require_session),
):
    from app.services.documental.media_rights import media_review_registry as registry

    def operation():
        service = Proposals(db, session)
        edit, _item, _facts, _fingerprint = service.context(ecomm_id)
        return registry(service.research, ecomm_id, edit["fields"])

    return execute(db, operation)


class TaxonomyPair(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=80)
    category: str = Field(min_length=1, max_length=160)
    subcategory: str = Field(min_length=1, max_length=160)
    state: Literal["ACTIVE", "RETIRED"]


class TaxonomyChannelPair(TaxonomyPair):
    pair_id: str = Field(min_length=1, max_length=80)
    channel: Literal["ECOMM", "ML", "TN"]


class SaveTaxonomyCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=0)
    revision: str = Field(min_length=1, max_length=100)
    entries: list[TaxonomyPair] = Field(max_length=1000)
    mappings: list[TaxonomyChannelPair] = Field(max_length=1000)
    reason: str = Field(min_length=20, max_length=600)
    confirm: Literal[True]


class PreviewTaxonomyBatch(CommercialReviewPreview):
    channel: Literal["KIKI", "ECOMM", "ML", "TN"] = "KIKI"


class TaxonomyBatchDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ecomm_id: str = Field(min_length=1, max_length=120)
    decision: Literal["APPROVED", "REVOKED", "SKIP"]
    reason: str = Field(min_length=20, max_length=600)
    expected_version: int | None = Field(default=None, ge=0)
    expected_workspace_version: int | None = Field(default=None, ge=0)
    expected_fingerprint: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    taxonomy_revision: str | None = Field(default=None, min_length=1, max_length=100)
    target_category: str | None = Field(default=None, min_length=1, max_length=160)
    target_subcategory: str | None = Field(default=None, min_length=1, max_length=160)
    catalog_version: int | None = Field(default=None, ge=1)
    catalog_pair_id: str | None = Field(default=None, min_length=1, max_length=80)
    channel_mapping_id: str | None = Field(default=None, min_length=1, max_length=80)


class ReviewTaxonomyBatch(PreviewTaxonomyBatch):
    expected_selection_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    decisions: list[TaxonomyBatchDecision] = Field(min_length=1, max_length=20)
    confirm: Literal[True]


def taxonomy_operation(db, operation, *, write=False):
    try:
        result = operation()
        if write:
            db.commit()
        else:
            db.rollback()
        return result
    except ValueError as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from None
    except Exception:
        db.rollback()
        raise


@router.get("/taxonomy/catalog")
def taxonomy_catalog_state(db: Session = Depends(get_db), session=Depends(require_session)):
    from app.services.documental.taxonomy_catalog import TaxonomyCatalog

    return taxonomy_operation(db, lambda: TaxonomyCatalog(db, session).get())


@router.post("/taxonomy/catalog")
def taxonomy_catalog_save(
    body: SaveTaxonomyCatalog, db: Session = Depends(get_db), session=Depends(require_csrf),
):
    from app.services.documental.taxonomy_catalog import TaxonomyCatalog

    return taxonomy_operation(db, lambda: TaxonomyCatalog(db, session).save(
        expected_version=body.expected_version, revision=body.revision,
        entries=[row.model_dump() for row in body.entries],
        mappings=[row.model_dump() for row in body.mappings], reason=body.reason,
    ), write=True)


@router.post("/taxonomy/review-preview")
def taxonomy_batch_preview(
    body: PreviewTaxonomyBatch, db: Session = Depends(get_db), session=Depends(require_csrf),
):
    from app.services.documental.taxonomy_review import TaxonomyReview

    return taxonomy_operation(db, lambda: TaxonomyReview(db, session).preview_batch(body.ecomm_ids, body.channel))


@router.post("/taxonomy/review-batch")
def taxonomy_batch_review(
    body: ReviewTaxonomyBatch, db: Session = Depends(get_db), session=Depends(require_csrf),
):
    from app.services.documental.taxonomy_review import TaxonomyReview

    return taxonomy_operation(db, lambda: TaxonomyReview(db, session).review_batch(
        ids=body.ecomm_ids, channel=body.channel,
        expected_selection_fingerprint=body.expected_selection_fingerprint,
        decisions=[row.model_dump(exclude_none=True) for row in body.decisions],
    ), write=True)
