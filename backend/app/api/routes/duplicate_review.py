import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
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
