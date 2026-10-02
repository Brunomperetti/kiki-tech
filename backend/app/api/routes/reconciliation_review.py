import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...core.security import require_csrf, require_session
from ...database.session import get_db
from ...services.reconciliation_review_service import ReconciliationReviewService

router = APIRouter(prefix="/api/reconciliation-review", tags=["reconciliation-review"])
logger = logging.getLogger(__name__)


class ReconciliationReviewDecisionRequest(BaseModel):
    product_key: str
    decision: str
    note: str | None = None


@router.get("")
def reconciliation_review_queue(
    db: Session = Depends(get_db),
    _session=Depends(require_session),
):
    try:
        return ReconciliationReviewService(db).queue()
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        logger.exception("reconciliation_review_queue_failed")
        raise HTTPException(500, "No se pudo preparar la revisión de conciliación.") from exc


@router.post("")
def reconciliation_review_decision(
    request: ReconciliationReviewDecisionRequest,
    db: Session = Depends(get_db),
    _session=Depends(require_csrf),
):
    try:
        return ReconciliationReviewService(db).save_decision(
            request.product_key,
            request.decision,
            request.note,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        logger.exception("reconciliation_review_decision_failed")
        raise HTTPException(500, "No se pudo guardar la decisión de conciliación.") from exc
