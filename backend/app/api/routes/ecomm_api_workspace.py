"""Internal KIKI editor for Ecomm-App API variants; NO vendor writes."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from ...core.security import require_csrf, require_session
from ...database.session import get_db
from ...services.ecomm_api_product_workspace_service import EcommApiProductWorkspace
from ...services.ecomm_ai_editor_service import EcommAiEditor
from ...services.ecomm_ai_proposal_inbox_service import list_ecomm_ai_proposals
from ...services.ecomm_api_brand_hints_service import EcommApiBrandHints
from ...services.ecomm_api_work_queue_service import build_queue

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
    filter: str = Query(default="all", max_length=35),
    page: int = Query(default=1, ge=1, le=100000),
    limit: int = Query(default=25, ge=1, le=50),
    db: Session = Depends(get_db),
    _session=Depends(require_session),
):
    """API-only prioritized editorial queue; no AI calls, external writes or approvals."""
    try:
        return build_queue(db, query=q, filter_name=filter, page=page, limit=limit)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None


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
            ecomm_id, body.expected_version
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
        return EcommApiProductWorkspace(db).get(ecomm_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None


@router.post("/{ecomm_id}")
def save_edit(
    ecomm_id: str,
    body: SaveProductEdit,
    db: Session = Depends(get_db),
    _session=Depends(require_csrf),
):
    try:
        return EcommApiProductWorkspace(db).save(
            ecomm_id, body.fields.model_dump(), body.status, body.expected_version
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None
