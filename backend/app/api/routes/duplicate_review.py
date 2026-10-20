import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ...core.security import require_csrf, require_session
from ...database.session import get_db
from ...services.duplicate_review_service import DuplicateReviewService

router = APIRouter(prefix="/api/duplicate-review", tags=["duplicate-review"])
logger = logging.getLogger(__name__)


class DuplicateReviewDecisionRequest(BaseModel):
    group_key: str
    decision: str
    note: str | None = None


class DuplicateReviewVariantsBatchRequest(BaseModel):
    group_keys: list[str] = Field(min_length=1, max_length=20)
    reconciliation_run_id: int
    note: str = Field(min_length=15, max_length=1000)
    confirmed: bool = False


@router.post("/variants-batch")
def duplicate_review_variants_batch(
    request: DuplicateReviewVariantsBatchRequest,
    db: Session = Depends(get_db),
    _session=Depends(require_csrf),
):
    if request.confirmed is not True:
        raise HTTPException(400, "Confirmá explícitamente que revisaste todos los grupos.")
    try:
        return DuplicateReviewService(db).save_variants_batch(
            request.group_keys, request.reconciliation_run_id, request.note
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        db.rollback()
        logger.exception("duplicate_review_variants_batch_failed")
        raise HTTPException(500, "No se pudo guardar el lote completo de variantes.") from exc



@router.get("")
def duplicate_review_queue(
    db: Session = Depends(get_db),
    _session=Depends(require_session),
):
    try:
        return DuplicateReviewService(db).queue()
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        logger.exception("duplicate_review_queue_failed")
        raise HTTPException(500, "No se pudo preparar la revisión de duplicados.") from exc


@router.post("")
def duplicate_review_decision(
    request: DuplicateReviewDecisionRequest,
    db: Session = Depends(get_db),
    _session=Depends(require_csrf),
):
    try:
        return DuplicateReviewService(db).save_decision(
            request.group_key,
            request.decision,
            request.note,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        logger.exception("duplicate_review_decision_failed")
        raise HTTPException(500, "No se pudo guardar la decisión de duplicado.") from exc
