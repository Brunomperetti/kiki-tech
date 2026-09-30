import logging
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ...catalog.models import ReconciliationStatus
from ...core.config import get_settings
from ...core.security import require_csrf, require_session
from ...database.session import get_db
from ...integrations.common.excel import ExcelImportError
from ...repositories.catalog_repository import CatalogRepository
from ...services.enrichment_review_service import EnrichmentReviewService
from ...services.enrichment_service import EnrichmentService
from ...services.publication_readiness_service import PublicationReadinessService
from ...services.reconciliation_service import ReconciliationService

router = APIRouter(prefix="/api", tags=["catalog"])
logger = logging.getLogger(__name__)


class EnrichmentDecisionRequest(BaseModel):
    product_key: str
    status: str
    note: str | None = None


@router.post("/imports/{source}", status_code=201)
async def import_catalog(
    source: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _session=Depends(require_csrf),
):
    source = source.upper()
    if source not in {"ECOMM_APP", "MERCADOLIBRE"}:
        raise HTTPException(400, "Origen de importación no válido.")
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(400, "El archivo debe tener formato XLSX.")
    content = await file.read()
    if len(content) > get_settings().max_upload_mb * 1024 * 1024:
        raise HTTPException(413, "El archivo supera el tamaño máximo permitido.")
    try:
        job = ReconciliationService(db).import_file(source, file.filename, content)
        return {
            "id": job.id,
            "records": job.records,
            "unknown_columns": job.diagnostics.get("ignored_columns", []),
            "diagnostics": job.diagnostics,
            "status": job.status,
        }
    except ExcelImportError as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        logger.exception("import_failed source=%s", source)
        raise HTTPException(500, "No se pudo procesar el archivo.") from exc


@router.post("/reconciliations", status_code=201)
def analyze(
    ml_source: str = "AUTO",
    db: Session = Depends(get_db),
    _session=Depends(require_csrf),
):
    try:
        return ReconciliationService(db).analyze(ml_source)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        logger.exception("reconciliation_failed")
        raise HTTPException(500, "No se pudo analizar el catálogo.") from exc


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), _session=Depends(require_session)):
    repo = CatalogRepository(db)
    run = repo.latest_run()
    summary = dict(run.summary) if run else {"total_products": 0, "total_listings": 0}
    summary["import_diagnostics"] = [
        {"source": job.source, "filename": job.filename, **(job.diagnostics or {})}
        for job in repo.latest_jobs_by_source()
    ]
    return summary


@router.get("/publication-readiness")
def publication_readiness(
    db: Session = Depends(get_db), _session=Depends(require_session)
):
    try:
        return PublicationReadinessService(db).report()
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        logger.exception("publication_readiness_failed")
        raise HTTPException(500, "No se pudo preparar la validación de publicación.") from exc


@router.get("/enrichment-pilot")
def enrichment_pilot(
    limit: int = 20,
    db: Session = Depends(get_db),
    _session=Depends(require_session),
):
    try:
        return EnrichmentService(db).report(limit=limit)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        logger.exception("enrichment_pilot_failed")
        raise HTTPException(500, "No se pudo preparar el piloto de enriquecimiento.") from exc


@router.get("/enrichment-review-queue")
def enrichment_review_queue(
    db: Session = Depends(get_db),
    _session=Depends(require_session),
):
    try:
        return EnrichmentReviewService(db).queue()
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        logger.exception("enrichment_review_queue_failed")
        raise HTTPException(500, "No se pudo preparar la cola de revisión.") from exc


@router.post("/enrichment-review-decisions")
def enrichment_review_decision(
    request: EnrichmentDecisionRequest,
    db: Session = Depends(get_db),
    _session=Depends(require_csrf),
):
    try:
        return EnrichmentReviewService(db).save_decision(
            request.product_key,
            request.status,
            request.note,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        logger.exception("enrichment_review_decision_failed")
        raise HTTPException(500, "No se pudo guardar la decisión de revisión.") from exc


@router.get("/products")
def products(
    status: ReconciliationStatus | None = None,
    search: str = "",
    review_only: bool = False,
    db: Session = Depends(get_db),
    _session=Depends(require_session),
):
    run = CatalogRepository(db).latest_run()
    items = run.results if run else []
    review = {
        "REVIEW_REQUIRED",
        "POSSIBLE_DUPLICATE",
        "INVALID_SKU",
        "INVALID_EAN",
        "INCOMPLETE_DATA",
    }
    if status:
        items = [x for x in items if x["status"] == status.value]
    if review_only:
        items = [x for x in items if x["status"] in review]
    term = search.casefold().strip()
    if term:
        items = [
            x
            for x in items
            if term
            in " ".join(
                str(v or "")
                for v in [
                    (x.get("product") or {}).get("sku"),
                    (x.get("product") or {}).get("ean"),
                    (x.get("product") or {}).get("name"),
                ]
            ).casefold()
        ]
    return items


@router.get("/imports")
def imports(db: Session = Depends(get_db), _session=Depends(require_session)):
    return [
        {
            "id": job.id,
            "filename": job.filename,
            "source": job.source,
            "started_at": job.started_at,
            "records": job.records,
            "processed": job.processed,
            "errors": job.errors,
            "status": job.status,
            "unknown_columns": job.diagnostics.get("ignored_columns", []),
            "diagnostics": job.diagnostics,
        }
        for job in CatalogRepository(db).jobs()
    ]
