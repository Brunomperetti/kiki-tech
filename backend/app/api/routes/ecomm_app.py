"""Authenticated KIKI endpoints for Ecomm-App stock API pilot.

This router cannot modify remote inventory or local catalog snapshots.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ...core.config import get_settings
from ...core.security import require_csrf, require_session
from ...database.session import get_db
from sqlalchemy.orm import Session
from ...integrations.ecomm_app.catalog_stage import EcommAppStageService
from ...integrations.ecomm_app.catalog_comparison import EcommAppStageComparisonService
from ...integrations.ecomm_app.catalog_hybrid_preview import EcommHybridCatalogService
from ...integrations.ecomm_app.live_stock_check import EcommLiveStockService
from ...integrations.ecomm_app.commercial_audit import commercial_fields_audit
from ...integrations.ecomm_app.tn_brand_evidence import EcommTnBrandEvidenceService
from ...database.models import CatalogSnapshot
from ...integrations.ecomm_app.catalog_stage import STAGE_SOURCE
from sqlalchemy import select
from ...integrations.ecomm_app.public_api import (
    EcommAppApiError,
    EcommAppInventoryClient,
)

router = APIRouter(prefix="/api/ecomm-app", tags=["ecomm-app"])


class LookupRequest(BaseModel):
    skus: list[str] = Field(min_length=1, max_length=3)


class HybridPreviewRequest(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=5)


class CatalogAuditRequest(BaseModel):
    start_page: int = Field(default=1, ge=1, le=10000)


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


@router.post("/catalog-audit")
def ecomm_app_catalog_audit(body: CatalogAuditRequest, _session=Depends(require_csrf)):
    """Only reads two pages (<=100 parent products) and does not persist data."""
    try:
        return _client().catalog_audit(body.start_page)
    except (EcommAppApiError, ValueError) as exc:
        _raise_safe(exc)


@router.get("/stage/status")
def ecomm_app_stage_status(
    db: Session = Depends(get_db), _session=Depends(require_session),
):
    """Return compact progress only, without returning copied inventory rows."""
    return EcommAppStageService(db, None).status()


@router.post("/stage/next")
def ecomm_app_stage_next(
    db: Session = Depends(get_db), _session=Depends(require_csrf),
):
    """Append up to three fully validated pages to isolated KIKI staging data."""
    try:
        return EcommAppStageService(db, _client()).next_batch()
    except (EcommAppApiError, ValueError) as exc:
        _raise_safe(exc)


@router.get("/stage/compare")
def ecomm_app_stage_compare(
    db: Session = Depends(get_db), _session=Depends(require_session),
):
    """Read-only comparison with historical ECOMM_APP snapshot.

    Returns only counts and small samples, never a transformed snapshot.
    """
    try:
        return EcommAppStageComparisonService(db).report()
    except ValueError as exc:
        _raise_safe(exc)


@router.post("/stage/hybrid-preview")
def ecomm_app_hybrid_preview(
    body: HybridPreviewRequest,
    db: Session = Depends(get_db),
    _session=Depends(require_csrf),
):
    """Simulate read-only comparison by stable ID: never promote stock or price."""
    try:
        return EcommHybridCatalogService(db).preview(body.ids)
    except ValueError as exc:
        _raise_safe(exc)


@router.post("/stage/live-stock-check")
def ecomm_app_live_stock_check(
    body: HybridPreviewRequest,
    db: Session = Depends(get_db),
    _session=Depends(require_csrf),
):
    """Explicit read-only vendor lookup; does not update snapshots or channels."""
    try:
        return EcommLiveStockService(db, _client()).verify(body.ids)
    except (ValueError, EcommAppApiError) as exc:
        _raise_safe(exc)


@router.get("/stage/commercial-audit")
def ecomm_app_commercial_audit(
    db: Session = Depends(get_db),
    _session=Depends(require_session),
):
    """Read-only, bounded brand/price/cost/EAN quality audit of historical IDs."""
    stage = db.scalar(select(CatalogSnapshot).where(CatalogSnapshot.source == STAGE_SOURCE))
    legacy = db.scalar(select(CatalogSnapshot).where(CatalogSnapshot.source == "ECOMM_APP"))
    try:
        return commercial_fields_audit(
            stage.payload if stage else [],
            legacy.payload if legacy else [],
        )
    except ValueError as exc:
        _raise_safe(exc)


@router.get("/stage/tn-brand-evidence")
def ecomm_app_tn_brand_evidence(
    db: Session = Depends(get_db),
    _session=Depends(require_session),
):
    """Review suggestions, never verified manufacturer brands or writes."""
    try:
        return EcommTnBrandEvidenceService(db).report()
    except ValueError as exc:
        _raise_safe(exc)
