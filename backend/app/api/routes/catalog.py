import logging
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session
from ...catalog.models import ReconciliationStatus
from ...core.config import get_settings
from ...database.session import get_db
from ...integrations.common.excel import ExcelImportError
from ...repositories.catalog_repository import CatalogRepository
from ...services.reconciliation_service import ReconciliationService
router=APIRouter(prefix="/api",tags=["catalog"]); logger=logging.getLogger(__name__)
@router.post("/imports/{source}",status_code=201)
async def import_catalog(source: str, file: UploadFile=File(...), db: Session=Depends(get_db)):
    source=source.upper()
    if source not in {"ECOMM_APP","MERCADOLIBRE"}: raise HTTPException(400,"Origen de importación no válido.")
    if not file.filename or not file.filename.lower().endswith(".xlsx"): raise HTTPException(400,"El archivo debe tener formato XLSX.")
    content=await file.read()
    if len(content)>get_settings().max_upload_mb*1024*1024: raise HTTPException(413,"El archivo supera el tamaño máximo permitido.")
    try:
        job=ReconciliationService(db).import_file(source,file.filename,content)
        return {"id":job.id,"records":job.records,"unknown_columns":job.diagnostics.get("ignored_columns",[]),"diagnostics":job.diagnostics,"status":job.status}
    except ExcelImportError as exc: raise HTTPException(422,str(exc)) from exc
    except Exception as exc:
        logger.exception("import_failed source=%s",source); raise HTTPException(500,"No se pudo procesar el archivo.") from exc
@router.post("/reconciliations",status_code=201)
def analyze(db: Session=Depends(get_db)):
    try: return ReconciliationService(db).analyze()
    except Exception as exc: logger.exception("reconciliation_failed"); raise HTTPException(500,"No se pudo analizar el catálogo.") from exc
@router.get("/dashboard")
def dashboard(db: Session=Depends(get_db)):
    repo=CatalogRepository(db); run=repo.latest_run()
    summary=dict(run.summary) if run else {"total_products":0,"total_listings":0}
    summary["import_diagnostics"]=[{"source":job.source,"filename":job.filename,**(job.diagnostics or {})} for job in repo.latest_jobs_by_source()]
    return summary
@router.get("/products")
def products(status: ReconciliationStatus|None=None, search: str="", review_only: bool=False, db: Session=Depends(get_db)):
    run=CatalogRepository(db).latest_run(); items=run.results if run else []
    review={"REVIEW_REQUIRED","POSSIBLE_DUPLICATE","INVALID_SKU","INVALID_EAN","INCOMPLETE_DATA"}
    if status: items=[x for x in items if x["status"]==status.value]
    if review_only: items=[x for x in items if x["status"] in review]
    term=search.casefold().strip()
    if term: items=[x for x in items if term in " ".join(str(v or "") for v in [(x.get("product") or {}).get("sku"),(x.get("product") or {}).get("ean"),(x.get("product") or {}).get("name")]).casefold()]
    return items
@router.get("/imports")
def imports(db: Session=Depends(get_db)):
    return [{
        "id": job.id, "filename": job.filename, "source": job.source,
        "started_at": job.started_at, "records": job.records,
        "processed": job.processed, "errors": job.errors, "status": job.status,
        "unknown_columns": job.diagnostics.get("ignored_columns", []),
        "diagnostics": job.diagnostics,
    } for job in CatalogRepository(db).jobs()]
