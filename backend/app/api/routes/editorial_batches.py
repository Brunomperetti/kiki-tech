"""Additive, default-off internal batch routes. Existing session and CSRF only."""

from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.core.security import require_session, require_csrf
from app.database.session import get_db
from app.services.editorial_batches.service import Batches


def enabled():
    config = get_settings()
    if (
        not config.kiki_editorial_batches_enabled
        or not config.kiki_document_workspace_enabled
    ):
        raise HTTPException(
            403,
            "Lotes editoriales deshabilitados; requieren revisión de configuración y migración.",
        )


router = APIRouter(
    prefix="/api/ecomm-app/editorial-batches",
    tags=["editorial-batches"],
    dependencies=[Depends(enabled)],
)


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Selection(Strict):
    kind: Literal["IDS", "FILTER"]
    ids: list[str] = Field(default_factory=list, max_length=10000)
    query: str = Field(default="", max_length=80)
    filter: str = Field(default="all", max_length=100)


class Preview(Strict):
    request_key: UUID
    operation: Literal["GENERATE_PROPOSALS", "REVIEW_TASKS"]
    selection: Selection


class Start(Strict):
    confirm: Literal[True]
    expected_revision: int = Field(ge=1)
    preview_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    idempotency_key: UUID


class Revision(Strict):
    expected_revision: int = Field(ge=1)


class Step(Strict):
    resume_interrupted: bool = False


def execute(db, fn):
    try:
        return fn()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from None
    except (DBAPIError, IntegrityError):
        db.rollback()
        raise HTTPException(
            409,
            "Lote ocupado o solicitud concurrente. Recargá su estado antes de continuar.",
        ) from None


@router.get("")
def listing(
    page: int = Query(1, ge=1, le=10000),
    limit: int = Query(10, ge=1, le=25),
    db: Session = Depends(get_db),
    session=Depends(require_session),
):
    return execute(db, lambda: Batches(db, session).listing(page, limit))


@router.post("/preview")
def preview(
    body: Preview, db: Session = Depends(get_db), session=Depends(require_csrf)
):
    return execute(
        db, lambda: Batches(db, session).preview(body.model_dump(mode="json"))
    )


@router.get("/{batch_id}")
def detail(
    batch_id: UUID,
    page: int = Query(1, ge=1, le=10000),
    limit: int = Query(25, ge=1, le=50),
    db: Session = Depends(get_db),
    session=Depends(require_session),
):
    return execute(db, lambda: Batches(db, session).detail(str(batch_id), page, limit))


@router.post("/{batch_id}/start")
def start(
    batch_id: UUID,
    body: Start,
    db: Session = Depends(get_db),
    session=Depends(require_csrf),
):
    return execute(
        db,
        lambda: Batches(db, session).start(str(batch_id), body.model_dump(mode="json")),
    )


@router.post("/{batch_id}/step")
def step(
    batch_id: UUID,
    body: Step,
    db: Session = Depends(get_db),
    session=Depends(require_csrf),
):
    if get_settings().kiki_editorial_executor_enabled:
        raise HTTPException(
            409, "La ejecución pertenece al backend. Consultá el progreso del lote."
        )
    return execute(
        db, lambda: Batches(db, session).step(str(batch_id), body.resume_interrupted)
    )


@router.post("/{batch_id}/cancel")
def cancel(
    batch_id: UUID,
    body: Revision,
    db: Session = Depends(get_db),
    session=Depends(require_csrf),
):
    return execute(
        db, lambda: Batches(db, session).cancel(str(batch_id), body.expected_revision)
    )


@router.post("/{batch_id}/retry")
def retry(
    batch_id: UUID,
    body: Revision,
    db: Session = Depends(get_db),
    session=Depends(require_csrf),
):
    return execute(
        db, lambda: Batches(db, session).retry(str(batch_id), body.expected_revision)
    )
