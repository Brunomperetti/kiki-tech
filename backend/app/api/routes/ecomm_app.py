"""Authenticated KIKI endpoints for Ecomm-App stock API pilot.

This router cannot modify remote inventory or local catalog snapshots.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ...core.config import get_settings
from ...core.security import require_csrf, require_session
from ...integrations.ecomm_app.public_api import (
    EcommAppApiError,
    EcommAppInventoryClient,
)

router = APIRouter(prefix="/api/ecomm-app", tags=["ecomm-app"])


class LookupRequest(BaseModel):
    skus: list[str] = Field(min_length=1, max_length=3)


def _client() -> EcommAppInventoryClient:
    return EcommAppInventoryClient(get_settings().ecomm_app_api_token)


def _raise_safe(exc: Exception):
    if isinstance(exc, EcommAppApiError):
        raise HTTPException(
            status_code=exc.status_code,
            detail=f"{exc.code}: {exc.message}",
        ) from None
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=422, detail=str(exc)) from None
    raise HTTPException(
        status_code=502, detail="No se pudo consultar el inventario de Ecomm-App."
    ) from None


@router.get("/status")
def ecomm_app_status(_session=Depends(require_session)):
    return {
        "configured": bool(get_settings().ecomm_app_api_token.strip()),
        "mode": "READ_ONLY",
        "scope_required": "inventario:leer",
        "description": "Consulta de inventario sin modificar Ecomm-App ni KIKI.",
    }


@router.post("/preview")
def ecomm_app_preview(_session=Depends(require_csrf)):
    try:
        return _client().preview()
    except (EcommAppApiError, ValueError) as exc:
        _raise_safe(exc)


@router.post("/lookup")
def ecomm_app_lookup(body: LookupRequest, _session=Depends(require_csrf)):
    try:
        return _client().lookup(body.skus)
    except (EcommAppApiError, ValueError) as exc:
        _raise_safe(exc)
