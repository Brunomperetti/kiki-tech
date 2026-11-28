"""Authenticated official /items/validate workflow; publication is not exposed."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import require_session, require_csrf
from app.database.session import get_db
from app.services import mercadolibre_official_validation as service


def available():
    cfg = get_settings()
    if not (cfg.kiki_v2_enabled and cfg.kiki_channel_workspace_enabled and cfg.kiki_document_workspace_enabled):
        raise HTTPException(403, "Validación comercial deshabilitada")


router = APIRouter(prefix="/api/ecomm-app/workspace/channels/ml/validations", tags=["ml-official-validation"], dependencies=[Depends(available)])


class Attribute(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: Literal["BRAND", "GTIN"]
    value_name: str = Field(min_length=1, max_length=250)
    fact_id: str = Field(pattern=r"^[a-f0-9]{24}$")


class Parameters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    seller_id: str | None = Field(default=None, pattern=r"^[1-9][0-9]{0,19}$")
    category_id: str | None = Field(default=None, pattern=r"^ML[A-Z][1-9][0-9]{0,13}$")
    price: float | None = Field(default=None, gt=0, le=1000000000, allow_inf_nan=False)
    currency_id: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    available_quantity: int | None = Field(default=None, ge=1, le=1000000, strict=True)
    condition: Literal["new", "used", "not_specified"] | None = None
    buying_mode: Literal["buy_it_now", "auction", "classified"] | None = None
    listing_type_id: str | None = Field(default=None, pattern=r"^[a-z_]{1,50}$")
    attributes: list[Attribute] = Field(default_factory=list, max_length=2)


class Preview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ecomm_id: str = Field(pattern=r"^[1-9][0-9]{0,19}$")
    request_key: str = Field(pattern=r"^[a-f0-9-]{36}$")
    parameters: Parameters
    reason: str = Field(min_length=20, max_length=600)


class Execute(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1, strict=True)
    expected_preview_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    confirm: Literal[True]


def execute(db, action):
    try:
        return action()
    except PermissionError as exc:
        db.rollback()
        raise HTTPException(403, str(exc)) from None
    except ValueError as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from None


@router.get("")
def listing(ecomm_id: str, db: Session = Depends(get_db), session=Depends(require_session)):
    return {"items": service.listing(db, ecomm_id), "official_validation_enabled": get_settings().kiki_ml_official_validation_enabled, "external_writes_enabled": False}


@router.post("/preview")
def preview(body: Preview, db: Session = Depends(get_db), session=Depends(require_csrf)):
    return execute(db, lambda: service.prepare(db, session, get_settings(), **body.model_dump()))


@router.post("/{ident}/validate")
def validate(ident: int, body: Execute, db: Session = Depends(get_db), session=Depends(require_csrf)):
    return execute(db, lambda: service.validate(db, session, get_settings(), ident, **body.model_dump()))
