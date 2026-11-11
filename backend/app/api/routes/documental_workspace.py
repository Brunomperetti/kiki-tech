"""Authenticated documental workspace. No provider clients or startup DDL."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.core.security import require_session, require_csrf
from app.database.session import get_db
from app.services.documental.research import Research
from app.services.documental.proposals import Proposals
from app.services.documental.local_documents import LocalDocuments, parse_local
from app.services.documental.contracts import (
    Extract,
    Review as ProposalReview,
    Generate,
    Incorporate,
    Provenance,
)
from app.services.documental.contracts import FactReview


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
