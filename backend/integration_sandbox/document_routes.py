from typing import Literal
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session
from app.core.security import require_session, require_csrf
from app.database.session import get_db
from .local_documents import LocalDocuments, parse_local
from .research.routes import execute

router = APIRouter(prefix="/api/test-documents", tags=["isolated-local-documents"])


class Incorporate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["FILE", "URL"]
    expected_version: int = Field(ge=0)
    filename: str = Field(default="", max_length=120)
    content_type: str = Field(default="", max_length=80)
    content_base64: str = Field(default="", max_length=699_052)
    provenance_note: str = Field(min_length=10, max_length=600)
    reference_url: str = Field(default="", max_length=1000)
    declared_official: bool = False
    authorized_local_processing: Literal[True]
    document_id: str | None = Field(default=None, pattern=r"^local-[a-f0-9]{32}$")
    expected_document_version: int | None = Field(default=None, ge=1)


class Provenance(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_document_version: int = Field(ge=1)
    decision: Literal["REVIEWED", "REJECTED", "REVOKED"]
    reason: str = Field(min_length=10, max_length=600)


@router.post("/{ecomm_id}/import")
def incorporate(
    ecomm_id: str,
    body: Incorporate,
    db: Session = Depends(get_db),
    session=Depends(require_csrf),
):
    def operation():
        # Parse only after auth/authorization, before holding the database mutex.
        parsed = parse_local(body) if body.kind == "FILE" else None
        return LocalDocuments(db, session).incorporate(ecomm_id, body, parsed)

    return execute(db, operation)


@router.post("/{ecomm_id}/{document_id}/provenance")
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


@router.get("/{ecomm_id}/{document_id}/original/{version}")
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
