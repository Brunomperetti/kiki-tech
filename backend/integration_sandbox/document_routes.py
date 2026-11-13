from fastapi import APIRouter, Depends
from pydantic import Field
from sqlalchemy.orm import Session
from app.core.security import require_session, require_csrf
from app.database.session import get_db
from app.services.documental.contracts import (
    Incorporate as CommonIncorporate,
    Provenance,
)
from .local_documents import LocalDocuments, parse_local
from .research.routes import execute
from .hileret_brochure import ENCODED_SIZE, validate_encoding
from .hileret_reference import PILOTS

router = APIRouter(prefix="/api/test-documents", tags=["isolated-local-documents"])


class Incorporate(CommonIncorporate):
    # Only sandbox pilot routes retain the hash-checked Hileret size profile.
    content_base64: str = Field(default="", max_length=ENCODED_SIZE)


@router.post("/{ecomm_id}/import")
def incorporate(
    ecomm_id: str,
    body: Incorporate,
    db: Session = Depends(get_db),
    session=Depends(require_csrf),
):
    def operation():
        if len(body.content_base64) > 699_052 and ecomm_id not in PILOTS:
            raise ValueError(
                "El original ampliado sólo está autorizado en los dos expedientes Hileret de pruebas."
            )
        if len(body.content_base64) > 699_052:
            validate_encoding(body.content_base64)
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
