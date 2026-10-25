"""Internal KIKI editor for Ecomm-App API variants; NO vendor writes."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from ...core.security import require_csrf, require_session
from ...database.session import get_db
from ...services.ecomm_api_product_workspace_service import EcommApiProductWorkspace

router = APIRouter(prefix="/api/ecomm-app/workspace", tags=["ecomm-api-workspace"])


class EditableFields(BaseModel):
    model_config = ConfigDict(extra="forbid")
    brand: str = Field(default="", max_length=120)
    title: str = Field(default="", max_length=180)
    description: str = Field(default="", max_length=3000)
    proposed_gtin: str = Field(default="", max_length=14)
    note: str = Field(default="", max_length=1200)


class SaveProductEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=0)
    status: Literal["DRAFT", "READY_FOR_REVIEW"]
    fields: EditableFields


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
