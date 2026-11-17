"""Authenticated documental workspace. No provider clients or startup DDL."""

from datetime import datetime, timezone
import base64
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.core.security import require_session, require_csrf
from app.database.session import get_db
from app.services.documental.research import Research
from app.services.documental.proposals import Proposals
from app.services.documental.source_links import suggest_reviewed_sources
from app.services.documental.local_documents import LocalDocuments, parse_local, reader_available
from app.services.documental.source_fetch import fetch_html
from app.services.documental.sitemap_discovery import preview_candidates
from app.services.documental.contracts import (
    Extract,
    Review as ProposalReview,
    Generate,
    Incorporate,
    Provenance,
)
from app.services.documental.contracts import FactReview
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
    return execute(
        db,
        lambda: review_media_rights(
            Research(db, session),
            ecomm_id, body.expected_version, document_id, body.document_version,
            body.media_url, body.media_kind, body.source_url, body.decision,
            body.licence_basis, body.location, body.quote, body.reason,
        ),
    )


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
