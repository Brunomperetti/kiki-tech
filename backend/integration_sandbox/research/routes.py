from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session
from app.core.security import require_session, require_csrf
from app.database.session import get_db
from .service import Research

router = APIRouter(prefix="/api/test-research", tags=["synthetic-research-only"])


class Extract(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=0)
    document_id: str = Field(pattern=r"^[a-z0-9-]{1,80}$")
    document_version: int = Field(ge=1)


class Review(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=0)
    expected_fact_version: int = Field(ge=1)
    decision: Literal["APPROVED", "REJECTED", "REVOKED"]
    reason: str = Field(min_length=10, max_length=600)


class Revision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    new_version: int = Field(ge=1)


def execute(db, operation):
    try:
        return operation()
    except ValueError as exc:
        # Only automatic invalidations can precede a failed optimistic precondition.
        db.commit()
        raise HTTPException(409, str(exc)) from None


@router.get("/{ecomm_id}")
def get_dossier(
    ecomm_id: str, db: Session = Depends(get_db), session=Depends(require_session)
):
    def query():
        service = Research(db, session)
        return service.serialize(service.dossier(ecomm_id))

    return execute(db, query)


@router.post("/{ecomm_id}/extract")
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


@router.post("/{ecomm_id}/facts/{fact_id}/review")
def review(
    ecomm_id: str,
    fact_id: str,
    body: Review,
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
            body.reason.strip(),
        ),
    )


@router.post("/documents/{document_id}/revision")
def revise(
    document_id: str,
    body: Revision,
    db: Session = Depends(get_db),
    session=Depends(require_csrf),
):
    return execute(
        db,
        lambda: Research(db, session).revise_document(
            document_id, body.expected_version, body.new_version
        ),
    )
