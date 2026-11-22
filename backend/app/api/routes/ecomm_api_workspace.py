"""Internal KIKI editor for Ecomm-App API variants; NO vendor writes."""

from typing import Literal, Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Header
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from ...core.security import require_csrf, require_session
from ...database.session import get_db
from ...services.ecomm_api_product_workspace_service import EcommApiProductWorkspace
from ...services.ecomm_ai_editor_service import EcommAiEditor
from ...services.ecomm_ai_proposal_inbox_service import list_ecomm_ai_proposals
from ...services.ecomm_api_brand_hints_service import EcommApiBrandHints
from ...services.ecomm_api_work_queue_service import build_queue
from ...services.ecomm_api_barcode_service import api_summary, api_evidence
from ...services.research_manifest_service import build_research_manifest
from ...services.research_batch_plan_service import build_research_batch_plan
from ...services.documentary_cohort_planner_service import (
    build_documentary_cohorts,
    export_documentary_cohorts_csv,
)
from ...services.contractual_delivery_audit_service import (
    build_delivery_audit,
    export_delivery_csv,
)
from ...services.documental.taxonomy_review import TaxonomyReview
from ...core.config import get_settings

router = APIRouter(prefix="/api/ecomm-app/workspace", tags=["ecomm-api-workspace"])


class CommercialAttribute(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(max_length=90)
    value: str = Field(max_length=450)


class CommercialMedia(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["IMAGE", "VIDEO"]
    url: str = Field(max_length=1000)
    alt: str = Field(default="", max_length=180)
    source_url: str = Field(default="", max_length=1000)


class CommercialSource(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["FABRICANTE", "ETIQUETA", "DISTRIBUIDOR", "OTRO"]
    name: str = Field(max_length=180)
    url: str = Field(default="", max_length=1000)
    note: str = Field(default="", max_length=500)
    verified: bool = False


class EditableFields(BaseModel):
    model_config = ConfigDict(extra="forbid")
    brand: str = Field(default="", max_length=120)
    manufacturer: str = Field(default="", max_length=120)
    title: str = Field(default="", max_length=180)
    short_title: str = Field(default="", max_length=100)
    short_description: str = Field(default="", max_length=500)
    description: str = Field(default="", max_length=5000)
    details: str = Field(default="", max_length=5000)
    presentation: str = Field(default="", max_length=750)
    category: str = Field(default="", max_length=160)
    subcategory: str = Field(default="", max_length=160)
    seo_title: str = Field(default="", max_length=180)
    seo_description: str = Field(default="", max_length=320)
    seo_keywords: str = Field(default="", max_length=1000)
    proposed_gtin: str = Field(default="", max_length=14)
    note: str = Field(default="", max_length=1800)
    attributes: list[CommercialAttribute] = Field(default_factory=list, max_length=40)
    media: list[CommercialMedia] = Field(default_factory=list, max_length=30)
    sources: list[CommercialSource] = Field(default_factory=list, max_length=20)


class SaveProductEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=0)
    status: Literal["DRAFT", "READY_FOR_REVIEW", "READY_FOR_CHANNELS"]
    fields: EditableFields


class GenerateAiSuggestion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=0)


class TaxonomyReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=0)
    expected_workspace_version: int = Field(ge=0)
    expected_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    channel: Literal["KIKI", "ECOMM", "ML", "TN"]
    decision: Literal["APPROVED", "REVOKED"]
    taxonomy_revision: str = Field(min_length=1, max_length=100)
    target_category: str = Field(min_length=1, max_length=160)
    target_subcategory: str = Field(min_length=1, max_length=160)
    reason: str = Field(min_length=20, max_length=600)
    confirm: Literal[True]


def require_taxonomy_workspace():
    if not get_settings().kiki_document_workspace_enabled:
        raise HTTPException(403, "La clasificación documentada está deshabilitada.")


@router.get(
    "/{ecomm_id}/taxonomy-review", dependencies=[Depends(require_taxonomy_workspace)]
)
def taxonomy_review_state(
    ecomm_id: str,
    channel: Literal["KIKI", "ECOMM", "ML", "TN"] = "KIKI",
    db: Session = Depends(get_db),
    session=Depends(require_session),
):
    try:
        return TaxonomyReview(db, session).get(ecomm_id, channel)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from None


@router.post(
    "/{ecomm_id}/taxonomy-review", dependencies=[Depends(require_taxonomy_workspace)]
)
def save_taxonomy_review(
    ecomm_id: str,
    body: TaxonomyReviewRequest,
    db: Session = Depends(get_db),
    session=Depends(require_csrf),
):
    try:
        values = body.model_dump(exclude={"confirm"})
        return TaxonomyReview(db, session).review(ecomm_id, **values)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from None


@router.get("/ai-proposals")
def ai_proposals(
    q: str = Query(default="", max_length=80),
    saved: str = Query(default="all", max_length=20),
    page: int = Query(default=1, ge=1, le=100000),
    limit: int = Query(default=25, ge=1, le=50),
    db: Session = Depends(get_db),
    _session=Depends(require_session),
):
    """Recover generated Ecomm AI suggestions; does not apply or approve them."""
    try:
        return list_ecomm_ai_proposals(
            db, query=q, saved_filter=saved, page=page, limit=limit
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None


@router.get("/ai/{ecomm_id}/latest")
def latest_ai_suggestion(
    ecomm_id: str,
    db: Session = Depends(get_db),
    _session=Depends(require_session),
):
    try:
        return EcommAiEditor(db).latest(ecomm_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None


@router.post("/ai/{ecomm_id}/suggest")
def generate_ai_suggestion(
    ecomm_id: str,
    body: GenerateAiSuggestion,
    db: Session = Depends(get_db),
    _session=Depends(require_csrf),
):
    try:
        return EcommAiEditor(db).suggest(ecomm_id, body.expected_version)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from None


@router.get("/brand-hints/{ecomm_id}")
def brand_hints(
    ecomm_id: str,
    db: Session = Depends(get_db),
    _session=Depends(require_session),
):
    """No-cost secondary evidence, never an authoritative brand or API write."""
    try:
        return EcommApiBrandHints(db).get(ecomm_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None


@router.get("/queue")
def work_queue(
    q: str = Query(default="", max_length=80),
    filter: str = Query(default="all", max_length=100),
    page: int = Query(default=1, ge=1, le=100000),
    limit: int = Query(default=25, ge=1, le=50),
    sort: Literal["priority", "capture"] = "priority",
    db: Session = Depends(get_db),
    _session=Depends(require_session),
):
    """API-only prioritized editorial queue; no AI calls, external writes or approvals."""
    try:
        return build_queue(
            db, query=q, filter_name=filter, page=page, limit=limit, sort=sort
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None


@router.get("/audit/contractual")
def commercial_delivery_audit(
    db: Session = Depends(get_db),
    _session=Depends(require_session),
):
    """Read-only whole catalogue contract audit, no source fetching or AI."""
    try:
        summary, _ = build_delivery_audit(db)
        return summary
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None


@router.get("/audit/contractual.csv")
def commercial_delivery_csv(
    db: Session = Depends(get_db),
    _session=Depends(require_session),
):
    """Export all variant exceptions with safe Excel cells; no database writes."""
    try:
        summary, rows = build_delivery_audit(db)
        body = export_delivery_csv(rows)
        return Response(
            body,
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": 'attachment; filename="kiki-auditoria-comercial-mensual.csv"',
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "X-Kiki-Audit-Variants": str(summary["total"]),
                "X-Kiki-Audit-Snapshot": summary["source"],
            },
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None


@router.get("/research/documentary-cohorts")
def documentary_cohorts(
    db: Session = Depends(get_db),
    _session=Depends(require_session),
):
    """Organize manufacturer *mentions* from the current complete API capture."""
    try:
        return build_documentary_cohorts(db)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None


@router.get("/research/documentary-cohorts.csv")
def documentary_cohorts_export(
    db: Session = Depends(get_db),
    _session=Depends(require_session),
):
    """Read-only CSV; URL, verification and permission are always empty/false."""
    try:
        plan = build_documentary_cohorts(db)
        return Response(
            export_documentary_cohorts_csv(plan),
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": 'attachment; filename="kiki-lotes-documentales-no-verificados.csv"',
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "X-Kiki-Source-Fingerprint": plan["capture_fingerprint"],
                "X-Kiki-Cohort-Plan-Fingerprint": plan["plan_fingerprint"],
                "X-Kiki-Documentary-Cohorts": str(plan["cohort_count"]),
            },
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None


@router.get("/research/plan")
def research_batch_plan(
    limit: int = Query(default=10, ge=1, le=20),
    offset: int = Query(default=0, ge=0, le=10000),
    db: Session = Depends(get_db),
    _session=Depends(require_session),
):
    """Read-only research scheduling for the complete API catalog, no network."""
    try:
        return build_research_batch_plan(db, limit=limit, offset=offset)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None


@router.get("/research/manifest.csv")
def research_manifest(
    db: Session = Depends(get_db),
    _session=Depends(require_session),
):
    """Export strictly eligible Ecomm research candidates, never approved facts."""
    try:
        body, count = build_research_manifest(db)
        return Response(
            body,
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": 'attachment; filename="kiki-investigacion-gtin-unico.csv"',
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "X-Kiki-Research-Candidates": str(count),
            },
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None


@router.get("/api-barcode/summary")
def api_barcode_summary(
    db: Session = Depends(get_db),
    _session=Depends(require_session),
):
    """Complete Ecomm-App API capture only; no historic Excel or CSV."""
    try:
        return api_summary(db)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None


@router.get("/api-barcode/{ecomm_id}")
def api_barcode_evidence(
    ecomm_id: str,
    db: Session = Depends(get_db),
    _session=Depends(require_session),
):
    try:
        return api_evidence(db, ecomm_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None


@router.get("/gtin-export/summary")
@router.get("/gtin-export/{ecomm_id}")
@router.get("/ean-evidence/summary")
@router.get("/ean-evidence/{ecomm_id}")
def retired_ecomm_spreadsheet_routes(_session=Depends(require_session)):
    """Retired Ecomm spreadsheet evidence; historical rows remain untouched."""
    raise HTTPException(
        410,
        "Ecomm-App se consulta exclusivamente por API. La evidencia histórica "
        "de Excel está archivada y no participa en la operación.",
    )


@router.post("/gtin-export")
def retired_ecomm_spreadsheet_upload(_session=Depends(require_csrf)):
    """Never accept further Ecomm spreadsheet data."""
    raise HTTPException(
        410, "La importación de Excel Ecomm-App está deshabilitada; usá la API."
    )


@router.get("/taxonomy")
def internal_taxonomy(
    db: Session = Depends(get_db),
    _session=Depends(require_session),
):
    """Saved category and subcategory names, to avoid inconsistent re-entry."""
    try:
        return EcommApiProductWorkspace(db).taxonomy()
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None


@router.get("/master-export")
def internal_master_export(
    status: str = Query(default="", max_length=32),
    db: Session = Depends(get_db),
    _session=Depends(require_session),
):
    """Authenticated full JSON export for continuity and future ML/TN adapters."""
    try:
        return EcommApiProductWorkspace(db).export_master(status)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None


@router.get("/saved")
def list_saved(
    q: str = Query(default="", max_length=80),
    status: str = Query(default="", max_length=32),
    page: int = Query(default=1, ge=1, le=100000),
    limit: int = Query(default=25, ge=1, le=50),
    db: Session = Depends(get_db),
    _session=Depends(require_session),
):
    try:
        return EcommApiProductWorkspace(db).list_saved(q, status, page, limit)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None


@router.post("/{ecomm_id}/confirm-review")
def confirm_monthly_review(
    ecomm_id: str,
    body: GenerateAiSuggestion,
    db: Session = Depends(get_db),
    _session=Depends(require_csrf),
):
    """Audit a verified monthly refresh without modifying source or channel."""
    try:
        return EcommApiProductWorkspace(db).confirm_monthly_review(
            ecomm_id, body.expected_version, session=_session
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None


@router.get("/{ecomm_id}")
def get_edit(
    ecomm_id: str,
    db: Session = Depends(get_db),
    _session=Depends(require_session),
):
    try:
        return EcommApiProductWorkspace(db).get(ecomm_id, session=_session)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None


@router.post("/{ecomm_id}")
def save_edit(
    ecomm_id: str,
    body: SaveProductEdit,
    proposal_id: Annotated[int | None, Header(alias="X-Kiki-Proposal-Id", ge=1)] = None,
    proposal_revision: Annotated[
        int | None, Header(alias="X-Kiki-Proposal-Revision", ge=1)
    ] = None,
    db: Session = Depends(get_db),
    _session=Depends(require_csrf),
):
    try:
        if proposal_id is not None or proposal_revision is not None:
            from .documental_workspace import enabled
            from ...services.documental.proposals import Proposals

            enabled()
            if proposal_id is None or proposal_revision is None:
                raise ValueError(
                    "Identificación y revisión de propuesta requeridas conjuntamente."
                )
            return Proposals(db, _session).apply(
                ecomm_id, proposal_id, proposal_revision, body
            )
        return EcommApiProductWorkspace(db).save(
            ecomm_id,
            body.fields.model_dump(),
            body.status,
            body.expected_version,
            session=_session,
        )
    except ValueError as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from None
