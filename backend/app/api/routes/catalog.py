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
from ...services.catalog_continuity_service import CatalogContinuityService
from ...services.enrichment_external_research_service import EnrichmentExternalResearchService
from ...services.enrichment_review_service import EnrichmentReviewService
from ...services.enrichment_service import EnrichmentService
from ...services.gtin_candidate_service import GtinCandidateService
from ...services.tiendanube_csv_service import TiendanubeCsvService
from ...services.tiendanube_image_audit_service import TiendanubeImageAuditService
from ...services.tiendanube_assisted_match_service import TiendanubeAssistedMatchService
from ...services.gtin_batch_pilot_service import GtinBatchPilotService
from ...services.external_gtin_candidate_service import ExternalGtinCandidateService
from ...services.inventory_linkage_service import InventoryLinkageService
from ...services.publication_readiness_service import PublicationReadinessService
from ...services.reconciliation_service import ReconciliationService

router = APIRouter(prefix="/api", tags=["catalog"])
logger = logging.getLogger(__name__)


class InventoryLinkageDecisionRequest(BaseModel):
    external_id: str
    decision: str
    ecomm_id: str
    note: str | None = None


class InventoryLinkageManualAssignmentRequest(BaseModel):
    external_id: str
    ecomm_id: str
    note: str | None = None


class InventoryLinkagePendingEcommRequest(BaseModel):
    external_id: str
    note: str | None = None


class InventoryLinkageEcommActionRequest(BaseModel):
    external_id: str
    action: str
    note: str | None = None


class CatalogContinuityDecisionRequest(BaseModel):
    conflict_key: str
    decision: str
    note: str | None = None


class EnrichmentDecisionRequest(BaseModel):
    product_key: str
    status: str
    note: str | None = None


class InternalDecisionRevokeRequest(BaseModel):
    product_key: str
    reason: str


class BrandNotApplicableRequest(BaseModel):
    product_keys: list[str]
    reason: str


class GtinBatchPilotRequest(BaseModel):
    product_keys: list[str]


class EnrichmentBrandBulkRequest(BaseModel):
    product_keys: list[str]


class EnrichmentExternalResearchBulkGtinRequest(BaseModel):
    product_keys: list[str]
    source_name: str
    source_url: str
    confidence: str
    notes: str


class EnrichmentExternalResearchRequest(BaseModel):
    product_key: str
    status: str
    proposed_brand: str | None = None
    proposed_ean: str | None = None
    source_name: str | None = None
    source_url: str | None = None
    confidence: str | None = None
    notes: str | None = None


@router.post("/tiendanube/import-csv", status_code=201)
async def import_tiendanube_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _session=Depends(require_csrf),
):
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(400, "Seleccioná un archivo CSV de Tiendanube.")
    content = await file.read(get_settings().max_upload_mb * 1024 * 1024 + 1)
    if len(content) > get_settings().max_upload_mb * 1024 * 1024:
        raise HTTPException(413, "El archivo supera el tamaño permitido.")
    try:
        return TiendanubeCsvService(db).import_csv(file.filename, content)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/tiendanube/assisted-matches")
def tiendanube_assisted_matches(db: Session = Depends(get_db), _session=Depends(require_session)):
    return TiendanubeAssistedMatchService(db).report()


@router.post("/tiendanube/images/import-csv", status_code=201)
async def import_tiendanube_image_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _session=Depends(require_csrf),
):
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(400, "Seleccioná un CSV de imágenes.")
    content = await file.read(get_settings().max_upload_mb * 1024 * 1024 + 1)
    if len(content) > get_settings().max_upload_mb * 1024 * 1024:
        raise HTTPException(413, "El archivo supera el límite permitido.")
    try:
        return TiendanubeImageAuditService(db).import_csv(content)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/tiendanube/images/audit")
def tiendanube_image_audit(db: Session = Depends(get_db), _session=Depends(require_session)):
    return TiendanubeImageAuditService(db).report()


@router.get("/tiendanube/reconciliation")
def tiendanube_reconciliation(
    db: Session = Depends(get_db),
    _session=Depends(require_session),
):
    return TiendanubeCsvService(db).report()


@router.post("/imports/{source}", status_code=201)
async def import_catalog(
    source: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _session=Depends(require_csrf),
):
    source = source.upper()
    if source not in {
        "ECOMM_APP",
        "MERCADOLIBRE",
        "EDIMA_LINKAGE",
        "OFFLINE_LINKAGE_EVIDENCE",
    }:
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


@router.get("/inventory-linkage")
def inventory_linkage(
    db: Session = Depends(get_db), _session=Depends(require_session)
):
    try:
        return InventoryLinkageService(db).report()
    except Exception as exc:
        logger.exception("inventory_linkage_failed")
        raise HTTPException(500, "No se pudo analizar la vinculación de inventario.") from exc


@router.get("/inventory-linkage/candidates")
def inventory_linkage_candidates(
    external_id: str,
    search: str = "",
    limit: int = 8,
    db: Session = Depends(get_db),
    _session=Depends(require_session),
):
    try:
        return InventoryLinkageService(db).search_candidates(
            external_id=external_id,
            search=search,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        logger.exception("inventory_linkage_candidates_failed")
        raise HTTPException(500, "No se pudieron buscar candidatos Ecomm.") from exc


@router.post("/inventory-linkage/ecomm-action")
def inventory_linkage_ecomm_action(
    request: InventoryLinkageEcommActionRequest,
    db: Session = Depends(get_db),
    _session=Depends(require_csrf),
):
    try:
        return InventoryLinkageService(db).save_pending_ecomm_action(
            external_id=request.external_id,
            action=request.action,
            note=request.note,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        logger.exception("inventory_linkage_ecomm_action_failed")
        raise HTTPException(500, "No se pudo guardar la acción de catálogo Ecomm.") from exc


@router.post("/inventory-linkage/pending-ecomm")
def inventory_linkage_pending_ecomm(
    request: InventoryLinkagePendingEcommRequest,
    db: Session = Depends(get_db),
    _session=Depends(require_csrf),
):
    try:
        return InventoryLinkageService(db).mark_pending_ecomm_catalog(
            external_id=request.external_id,
            note=request.note,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        logger.exception("inventory_linkage_pending_ecomm_failed")
        raise HTTPException(500, "No se pudo guardar el pendiente de catálogo Ecomm.") from exc


@router.post("/inventory-linkage/manual-assignment")
def inventory_linkage_manual_assignment(
    request: InventoryLinkageManualAssignmentRequest,
    db: Session = Depends(get_db),
    _session=Depends(require_csrf),
):
    try:
        return InventoryLinkageService(db).save_manual_assignment(
            external_id=request.external_id,
            ecomm_id=request.ecomm_id,
            note=request.note,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        logger.exception("inventory_linkage_manual_assignment_failed")
        raise HTTPException(500, "No se pudo guardar la asignación manual.") from exc


@router.post("/inventory-linkage/decision")
def inventory_linkage_decision(
    request: InventoryLinkageDecisionRequest,
    db: Session = Depends(get_db),
    _session=Depends(require_csrf),
):
    try:
        return InventoryLinkageService(db).save_decision(
            external_id=request.external_id,
            decision_value=request.decision,
            ecomm_id=request.ecomm_id,
            note=request.note,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        logger.exception("inventory_linkage_decision_failed")
        raise HTTPException(500, "No se pudo guardar la decisión de vinculación.") from exc


@router.get("/catalog-continuity")
def catalog_continuity(
    db: Session = Depends(get_db),
    _session=Depends(require_session),
):
    try:
        return CatalogContinuityService(db).report()
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        logger.exception("catalog_continuity_failed")
        raise HTTPException(500, "No se pudo comparar Ecomm con los datos validados de KIKI.") from exc


@router.post("/catalog-continuity/decision")
def catalog_continuity_decision(
    request: CatalogContinuityDecisionRequest,
    db: Session = Depends(get_db),
    _session=Depends(require_csrf),
):
    try:
        return CatalogContinuityService(db).save_decision(
            conflict_key=request.conflict_key,
            decision_value=request.decision,
            note=request.note,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        logger.exception("catalog_continuity_decision_failed")
        raise HTTPException(500, "No se pudo guardar la decisión entre KIKI y Ecomm.") from exc


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



@router.post("/enrichment-review-decisions/bulk-brand")
def enrichment_bulk_brand_approval(
    request: EnrichmentBrandBulkRequest,
    db: Session = Depends(get_db),
    _session=Depends(require_csrf),
):
    try:
        return EnrichmentReviewService(db).bulk_approve_brand_proposals(request.product_keys)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        logger.exception("enrichment_bulk_brand_approval_failed")
        raise HTTPException(500, "No se pudieron aprobar las propuestas de marca.") from exc


@router.post("/enrichment-review-decisions/brand-not-applicable")
def brand_not_applicable(
    request: BrandNotApplicableRequest,
    db: Session = Depends(get_db),
    _session=Depends(require_csrf),
):
    try:
        return EnrichmentReviewService(db).bulk_mark_brand_not_applicable(
            request.product_keys, request.reason
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        logger.exception("brand_not_applicable_failed")
        raise HTTPException(500, "No se pudo guardar la excepción de marca.") from exc


@router.get("/enrichment-decisions/history")
def internal_decision_history(db: Session = Depends(get_db), _session=Depends(require_session)):
    return EnrichmentReviewService(db).decision_history()


@router.post("/enrichment-decisions/revoke")
def revoke_internal_decision(
    request: InternalDecisionRevokeRequest,
    db: Session = Depends(get_db),
    _session=Depends(require_csrf),
):
    try:
        return EnrichmentReviewService(db).revoke_internal_decision(request.product_key, request.reason)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/gtin-candidates/{product_key:path}")
def get_gtin_candidates(product_key: str, db: Session = Depends(get_db), _session=Depends(require_session)):
    try:
        return GtinCandidateService(db).candidates(product_key)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        logger.exception("gtin_candidate_lookup_failed")
        raise HTTPException(500, "No se pudieron obtener sugerencias GTIN.") from exc


@router.get("/external-gtin-candidates/{product_key:path}")
def get_external_gtin_candidates(product_key: str, db: Session = Depends(get_db), _session=Depends(require_session)):
    try:
        return ExternalGtinCandidateService(db).lookup(product_key)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        logger.exception("external_gtin_candidate_lookup_failed")
        raise HTTPException(500, "No se pudo consultar la fuente externa.") from exc


@router.post("/gtin-batch-pilot")
def gtin_batch_pilot(request: GtinBatchPilotRequest, db: Session = Depends(get_db), _session=Depends(require_csrf)):
    try:
        return GtinBatchPilotService(db).run(request.product_keys)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        logger.exception("gtin_batch_pilot_failed")
        raise HTTPException(500, "No se pudo ejecutar el piloto de EAN.") from exc


@router.get("/enrichment-external-research")
def enrichment_external_research_queue(
    db: Session = Depends(get_db),
    _session=Depends(require_session),
):
    try:
        return EnrichmentExternalResearchService(db).queue()
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        logger.exception("enrichment_external_research_queue_failed")
        raise HTTPException(500, "No se pudo preparar la investigación externa.") from exc


@router.post("/enrichment-external-research")
def enrichment_external_research_save(
    request: EnrichmentExternalResearchRequest,
    db: Session = Depends(get_db),
    _session=Depends(require_csrf),
):
    try:
        return EnrichmentExternalResearchService(db).save(
            product_key=request.product_key,
            status=request.status,
            proposed_brand=request.proposed_brand,
            proposed_ean=request.proposed_ean,
            source_name=request.source_name,
            source_url=request.source_url,
            confidence=request.confidence,
            notes=request.notes,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        logger.exception("enrichment_external_research_save_failed")
        raise HTTPException(500, "No se pudo guardar la investigación externa.") from exc


@router.post("/enrichment-external-research/bulk-gtin-not-applicable")
def enrichment_external_research_bulk_gtin_not_applicable(
    request: EnrichmentExternalResearchBulkGtinRequest,
    db: Session = Depends(get_db),
    _session=Depends(require_csrf),
):
    try:
        return EnrichmentExternalResearchService(db).bulk_mark_gtin_not_applicable(
            product_keys=request.product_keys,
            source_name=request.source_name,
            source_url=request.source_url,
            confidence=request.confidence,
            notes=request.notes,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        logger.exception("enrichment_external_research_bulk_gtin_failed")
        raise HTTPException(
            500,
            "No se pudo aplicar la excepción GTIN al lote seleccionado.",
        ) from exc


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
