import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ...core.security import require_csrf, require_session
from ...database.session import get_db
from ...integrations.mercadolibre.transport import MercadoLibreHTTPError
from ...services.prepublication_image_service import PrepublicationImageService
from ...services.prepublication_metadata_service import PrepublicationMetadataService
from ...services.prepublication_service import PrepublicationService

router = APIRouter(prefix="/api/prepublication", tags=["prepublication"])
logger = logging.getLogger(__name__)


class MetadataAnalyzeRequest(BaseModel):
    product_key: str


class MetadataBatchAnalyzeRequest(BaseModel):
    limit: int = Field(default=10, ge=1, le=20)


class MetadataConditionalValidateRequest(BaseModel):
    product_key: str


class MetadataReviewRequest(BaseModel):
    product_key: str
    status: str
    category_id: str | None = None
    notes: str | None = None


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


@router.get("/metadata")
def metadata_review_queue(
    db: Session = Depends(get_db),
    _session=Depends(require_session),
):
    try:
        return PrepublicationMetadataService(db).queue()
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        logger.exception("prepublication_metadata_queue_failed")
        raise HTTPException(500, "No se pudo preparar categoría y atributos.") from exc


@router.post("/metadata/analyze")
def analyze_metadata(
    request: MetadataAnalyzeRequest,
    db: Session = Depends(get_db),
    _session=Depends(require_csrf),
):
    try:
        return PrepublicationMetadataService(db).analyze(request.product_key)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except MercadoLibreHTTPError as exc:
        if exc.status_code in {401, 403}:
            raise HTTPException(exc.status_code, "Mercado Libre requiere reconexión.") from exc
        if exc.status_code == 429:
            raise HTTPException(503, "Límite de Mercado Libre agotado; reintentá más tarde.") from exc
        logger.warning("prepublication_metadata_ml_failed status=%s", exc.status_code)
        raise HTTPException(502, "Mercado Libre no pudo analizar la categoría.") from exc
    except Exception as exc:
        logger.exception("prepublication_metadata_analyze_failed")
        raise HTTPException(500, "No se pudo analizar categoría y atributos.") from exc


@router.post("/metadata/validate-conditional")
def validate_conditional_metadata(
    request: MetadataConditionalValidateRequest,
    db: Session = Depends(get_db),
    _session=Depends(require_csrf),
):
    try:
        return PrepublicationMetadataService(db).validate_conditional(
            request.product_key
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except MercadoLibreHTTPError as exc:
        if exc.status_code in {401, 403}:
            raise HTTPException(exc.status_code, "Mercado Libre requiere reconexión.") from exc
        if exc.status_code == 429:
            raise HTTPException(503, "Límite de Mercado Libre agotado; reintentá más tarde.") from exc
        logger.warning(
            "prepublication_conditional_ml_failed status=%s detail=%s",
            exc.status_code,
            str(exc),
        )
        detail = str(exc).strip() or "Mercado Libre rechazó la validación."
        raise HTTPException(
            502,
            f"Mercado Libre rechazó la validación (HTTP {exc.status_code}): {detail}",
        ) from exc
    except Exception as exc:
        logger.exception("prepublication_conditional_validation_failed")
        raise HTTPException(
            500, "No se pudieron validar los atributos condicionales."
        ) from exc


@router.post("/metadata/analyze-pending")
def analyze_pending_metadata(
    request: MetadataBatchAnalyzeRequest,
    db: Session = Depends(get_db),
    _session=Depends(require_csrf),
):
    try:
        return PrepublicationMetadataService(db).analyze_pending(request.limit)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        logger.exception("prepublication_metadata_batch_failed")
        raise HTTPException(500, "No se pudo analizar el lote de categorías.") from exc


@router.post("/metadata")
def save_metadata_review(
    request: MetadataReviewRequest,
    db: Session = Depends(get_db),
    _session=Depends(require_csrf),
):
    try:
        return PrepublicationMetadataService(db).save(
            product_key=request.product_key,
            status=request.status,
            category_id=request.category_id,
            notes=request.notes,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except MercadoLibreHTTPError as exc:
        if exc.status_code in {401, 403}:
            raise HTTPException(exc.status_code, "Mercado Libre requiere reconexión.") from exc
        if exc.status_code == 429:
            raise HTTPException(503, "Límite de Mercado Libre agotado; reintentá más tarde.") from exc
        raise HTTPException(502, "Mercado Libre no pudo leer los atributos.") from exc
    except Exception as exc:
        logger.exception("prepublication_metadata_save_failed")
        raise HTTPException(500, "No se pudo guardar la revisión de categoría.") from exc
