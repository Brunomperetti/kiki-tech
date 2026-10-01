import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ...core.security import require_csrf, require_session
from ...database.session import get_db
from ...services.prepublication_image_service import PrepublicationImageService
from ...services.prepublication_service import PrepublicationService

router = APIRouter(prefix="/api/prepublication", tags=["prepublication"])
logger = logging.getLogger(__name__)


class ImageReviewRequest(BaseModel):
    product_key: str
    status: str
    source_type: str | None = None
    source_name: str | None = None
    source_url: str | None = None
    image_urls: list[str] = Field(default_factory=list)
    match_basis: str | None = None
    exact_match: bool = False
    authorized_for_use: bool = False
    notes: str | None = None


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


@router.get("/images")
def image_review_queue(
    db: Session = Depends(get_db),
    _session=Depends(require_session),
):
    try:
        return PrepublicationImageService(db).queue()
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        logger.exception("prepublication_image_queue_failed")
        raise HTTPException(500, "No se pudo preparar la revisión de imágenes.") from exc


@router.post("/images")
def save_image_review(
    request: ImageReviewRequest,
    db: Session = Depends(get_db),
    _session=Depends(require_csrf),
):
    try:
        return PrepublicationImageService(db).save(
            product_key=request.product_key,
            status=request.status,
            source_type=request.source_type,
            source_name=request.source_name,
            source_url=request.source_url,
            image_urls=request.image_urls,
            match_basis=request.match_basis,
            exact_match=request.exact_match,
            authorized_for_use=request.authorized_for_use,
            notes=request.notes,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        logger.exception("prepublication_image_save_failed")
        raise HTTPException(500, "No se pudo guardar la revisión de imágenes.") from exc
