import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from ...database.session import get_db
from ...core.config import get_settings
from ...core.security import require_csrf, require_session
from ...integrations.mercadolibre.transport import MercadoLibreHTTPError
from ...services.mercadolibre_service import MercadoLibreService

router = APIRouter(prefix="/api/mercadolibre", tags=["mercadolibre"])
logger = logging.getLogger(__name__)


@router.get("/status")
def status(db: Session = Depends(get_db), _session=Depends(require_session)):
    return MercadoLibreService(db).status()


@router.post("/auth-url")
def auth_url(db: Session = Depends(get_db), _session=Depends(require_csrf)):
    try:
        return {"url": MercadoLibreService(db).auth_url()}
    except ValueError as exc:
        raise HTTPException(503, str(exc)) from exc


@router.get("/callback")
def callback(code: str, state: str, db: Session = Depends(get_db)):
    try:
        MercadoLibreService(db).connect(code, state)
        return RedirectResponse(f"{get_settings().frontend_url.rstrip('/')}/?mercadolibre=connected")
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except MercadoLibreHTTPError as exc:
        logger.warning("mercadolibre_oauth_failed status=%s", exc.status_code)
        raise HTTPException(502, "Mercado Libre rechazó la conexión OAuth.") from exc


@router.post("/sync", status_code=201)
def sync(db: Session = Depends(get_db), _session=Depends(require_csrf)):
    """Triggers reads only; it never writes to a Mercado Libre commercial resource."""
    try:
        return MercadoLibreService(db).sync()
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    except MercadoLibreHTTPError as exc:
        if exc.status_code in {401, 403}:
            raise HTTPException(
                exc.status_code, "Mercado Libre requiere reconexión."
            ) from exc
        if exc.status_code == 429:
            raise HTTPException(
                503, "Límite de Mercado Libre agotado; reintentá más tarde."
            ) from exc
        logger.warning("mercadolibre_sync_failed status=%s", exc.status_code)
        raise HTTPException(502, "No se pudo leer Mercado Libre.") from exc
