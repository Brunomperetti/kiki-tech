import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...core.security import require_session
from ...database.session import get_db
from ...services.prepublication_service import PrepublicationService

router = APIRouter(prefix="/api/prepublication", tags=["prepublication"])
logger = logging.getLogger(__name__)


@router.get("")
def prepublication_report(
    db: Session = Depends(get_db),
    _session=Depends(require_session),
):
    try:
        return PrepublicationService(db).report()
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        logger.exception("prepublication_report_failed")
        raise HTTPException(500, "No se pudo preparar la etapa de pre-publicación.") from exc
