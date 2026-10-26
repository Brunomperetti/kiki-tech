"""Authenticated KIKI endpoints for Ecomm-App stock API pilot.

This router cannot modify remote inventory or local catalog snapshots.
"""
from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from secrets import compare_digest
from datetime import datetime, timezone

from ...core.config import get_settings
from ...core.security import require_csrf, require_session
from ...database.session import get_db
from sqlalchemy.orm import Session
from ...integrations.ecomm_app.api_catalog_browser import api_catalog_rows
from ...integrations.ecomm_app.api_ml_reconciliation_preview import api_ml_reconciliation_preview
from ...integrations.ecomm_app.catalog_stage import EcommAppStageService, REFRESH_SOURCE
from ...services.ecomm_api_refresh_job_service import (
    job_status, start_job, reset_stage, require_active, note_step, fail_job,
    run_manual_refresh,
)
from ...integrations.ecomm_app.catalog_comparison import EcommAppStageComparisonService
from ...integrations.ecomm_app.catalog_hybrid_preview import EcommHybridCatalogService
from ...integrations.ecomm_app.live_stock_check import EcommLiveStockService
from ...integrations.ecomm_app.commercial_audit import commercial_fields_audit
from ...integrations.ecomm_app.tn_brand_evidence import EcommTnBrandEvidenceService
from ...integrations.ecomm_app.ml_brand_evidence import EcommMlBrandEvidenceService
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


def require_refresh_token(authorization: str = Header(default="")):
    """Separate machine credential for scheduled jobs, never a user session."""
    token = get_settings().kiki_refresh_token.strip()
    if not token:
        raise HTTPException(503, "La actualización programada aún no está configurada.")
    supplied = authorization.removeprefix("Bearer ").strip()
    if not supplied or not compare_digest(supplied, token):
        raise HTTPException(403, "Credencial de sincronización inválida.")


@router.get("/stage/auto/status")
def ecomm_app_auto_status(
    db: Session = Depends(get_db),
    _session=Depends(require_session),
):
    current = EcommAppStageService(db, None).status()
    refresh = EcommAppStageService(db, None, REFRESH_SOURCE).status()
    job = job_status(db)
    is_running = bool(job and job["status"] == "RUNNING")
    return {
        "mode": "SCHEDULED_AND_MANUAL_API_ONLY",
        "configured": bool(get_settings().kiki_refresh_token.strip()),
        "last_successful_capture_at": current["last_page_at"],
        "last_successful_pages": current["pages_saved"],
        "last_successful_variants": current["quality"]["variants"],
        "last_successful_complete": current["complete"],
        "refresh_in_progress": is_running,
        "refresh_job": job,
        "refresh_pages_saved": refresh["pages_saved"],
        "refresh_pages_expected": refresh["expected_pages"],
        "refresh_last_page_at": refresh["last_page_at"],
        "external_writes_enabled": False,
        "warning": (
            "La API Ecomm-App se captura por lotes; no es inventario en tiempo real. "
            "Los borradores y propuestas comerciales permanecen separados."
        ),
    }


@router.post("/stage/auto/start")
def ecomm_app_auto_start(
    db: Session = Depends(get_db),
    _token=Depends(require_refresh_token),
):
    """Cron and UI share one database-backed lock; no concurrent refresh."""
    owner = start_job(db, "SCHEDULED")
    try:
        reset_stage(db, owner)
    except Exception:
        db.rollback()
        fail_job(db, owner, "No fue posible iniciar la captura programada.")
        raise
    return {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "status": "STARTED",
        "source": REFRESH_SOURCE,
        "current_catalog_unchanged": True,
    }


@router.post("/stage/auto/step")
def ecomm_app_auto_step(
    db: Session = Depends(get_db),
    _token=Depends(require_refresh_token),
):
    """Fetch at most three pages; promote all atomically only once completed."""
    owner = require_active(db, origin="SCHEDULED")
    db.rollback()  # release job lock before external API calls
    snapshot = db.scalar(select(CatalogSnapshot).where(
        CatalogSnapshot.source == REFRESH_SOURCE
    ))
    if snapshot is None:
        db.rollback()
        fail_job(db, owner, "Falta la captura temporal de Ecomm-App.")
        raise HTTPException(409, "Primero iniciá la captura programada.")
    try:
        result = EcommAppStageService(db, _client(), REFRESH_SOURCE).next_batch()
        note_step(db, owner, result)
    except (EcommAppApiError, ValueError) as exc:
        db.rollback()
        fail_job(db, owner, "La captura programada no se completó; se conservó la anterior.")
        _raise_safe(exc)
    return {
        "complete": result["complete"],
        "pages_saved": result["pages_saved"],
        "expected_pages": result["expected_pages"],
        "variants": result["quality"]["variants"],
        "last_page_at": result["last_page_at"],
        "promoted": result["complete"],
        "external_writes_enabled": False,
    }


@router.post("/stage/manual/start")
def ecomm_app_manual_refresh_start(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _session=Depends(require_csrf),
):
    """Authenticated operator starts a safe API refresh without GitHub access.

    Runs in the backend, so the browser can close while the work continues.
    Concurrent manual or scheduled captures are rejected.
    """
    if not get_settings().ecomm_app_api_token.strip():
        raise HTTPException(503, "Falta configurar la lectura de Ecomm-App API.")
    owner = start_job(db, "MANUAL")
    background_tasks.add_task(run_manual_refresh, owner)
    return {
        "status": "RUNNING",
        "message": "Iniciamos la actualización del catálogo. Podés salir y volver.",
        "external_writes_enabled": False,
    }


@router.get("/stage/status")
def ecomm_app_stage_status(
    db: Session = Depends(get_db), _session=Depends(require_session),
):
    """Return compact progress only, without returning copied inventory rows."""
    return EcommAppStageService(db, None).status()


@router.get("/stage/catalog")
def ecomm_app_stage_catalog(
    q: str = Query(default="", max_length=80),
    page: int = Query(default=1, ge=1, le=100000),
    limit: int = Query(default=25, ge=1, le=50),
    db: Session = Depends(get_db),
    _session=Depends(require_session),
):
    """Browse ONLY the completed API capture, never historical XLSX data."""
    stage = db.scalar(select(CatalogSnapshot).where(CatalogSnapshot.source == STAGE_SOURCE))
    try:
        return api_catalog_rows(stage.payload if stage else [], query=q, page=page, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None


@router.get("/stage/ml-reconciliation-preview")
def ecomm_app_ml_reconciliation_preview(
    db: Session = Depends(get_db),
    _session=Depends(require_session),
):
    """Compare completed Ecomm API capture with ML API snapshot without side effects.

    Absolutely no fallback to legacy ECOMM_APP or MERCADOLIBRE Excel.
    """
    stage = db.scalar(select(CatalogSnapshot).where(CatalogSnapshot.source == STAGE_SOURCE))
    ml = db.scalar(select(CatalogSnapshot).where(
        CatalogSnapshot.source == "MERCADOLIBRE_API"
    ))
    try:
        report = api_ml_reconciliation_preview(
            stage.payload if stage else [], ml.payload if ml else [],
        )
        report["ecomm_last_capture_at"] = (
            stage.payload[-1].get("captured_at") if stage and stage.payload else None
        )
        report["ml_snapshot_updated_at"] = (
            ml.updated_at.isoformat() if ml else None
        )
        return report
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None


@router.get("/stage/ml-cases")
def ecomm_app_ml_cases(
    status: str = Query(default="", max_length=60),
    q: str = Query(default="", max_length=80),
    page: int = Query(default=1, ge=1, le=100000),
    limit: int = Query(default=20, ge=1, le=50),
    db: Session = Depends(get_db),
    _session=Depends(require_session),
):
    """Search case evidence in the two existing API captures only. No writes."""
    stage = db.scalar(select(CatalogSnapshot).where(CatalogSnapshot.source == STAGE_SOURCE))
    ml = db.scalar(select(CatalogSnapshot).where(
        CatalogSnapshot.source == "MERCADOLIBRE_API"
    ))
    try:
        result = api_ml_reconciliation_preview(
            stage.payload if stage else [],
            ml.payload if ml else [],
            cases_page=page,
            cases_limit=limit,
            cases_status=status,
            cases_query=q,
        )
        return {
            "mode": result["mode"],
            "ecomm_source": result["ecomm_source"],
            "mercadolibre_source": result["mercadolibre_source"],
            "external_writes_enabled": False,
            "historical_decisions_applied": False,
            "ecomm_last_capture_at": (
                stage.payload[-1].get("captured_at")
                if stage and stage.payload else None
            ),
            "ml_snapshot_updated_at": (
                ml.updated_at.isoformat() if ml else None
            ),
            "summary": result["summary"],
            "cases": result["cases"],
            "warning": result["warning"],
        }
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None


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


@router.get("/stage/ml-brand-evidence")
def ecomm_app_ml_brand_evidence(
    db: Session = Depends(get_db),
    _session=Depends(require_session),
):
    """Review-only existing EDIMA/ML brand fields with unique Ecomm identity."""
    try:
        return EcommMlBrandEvidenceService(db).report()
    except ValueError as exc:
        _raise_safe(exc)
