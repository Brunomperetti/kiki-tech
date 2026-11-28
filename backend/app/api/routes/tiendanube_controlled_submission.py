"""Human-confirmed Tiendanube dispatch; default OFF and no automatic executor."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import require_session, require_csrf
from app.database.session import get_db
from app.services.tiendanube_controlled_submission import (
    prepare_submission, send_submission, get_submission, list_submissions,
)


def available():
    settings = get_settings()
    if not (settings.kiki_v2_enabled and settings.kiki_channel_workspace_enabled):
        raise HTTPException(403, "Envíos controlados deshabilitados")


router = APIRouter(prefix="/api/ecomm-app/workspace/channels/tn/submissions",
                   tags=["controlled-tiendanube"], dependencies=[Depends(available)])


class Preview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_key: str = Field(pattern=r"^[a-f0-9-]{36}$")
    ecomm_id: str = Field(pattern=r"^[1-9][0-9]{0,19}$")
    review_mode: Literal["DOCUMENTED", "MANUAL"] = "DOCUMENTED"
    operation: Literal["CREATE_HIDDEN", "UPDATE_CONTENT"]
    target_product_id: str | None = Field(default=None, pattern=r"^[1-9][0-9]{0,19}$")
    target_variant_id: str | None = Field(default=None, pattern=r"^[1-9][0-9]{0,19}$")
    identity_checks: list[Literal["brand", "name", "presentation", "quantity", "pack", "barcode"]] = Field(min_length=6, max_length=6)
    reason: str = Field(min_length=20, max_length=600)


class Send(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)
    expected_preview_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    confirm: Literal[True]


def execute(db, operation):
    try:
        return operation()
    except PermissionError as exc:
        db.rollback()
        raise HTTPException(403, str(exc)) from None
    except ValueError as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from None


@router.get("")
def listing(ecomm_id: str, db: Session = Depends(get_db), session=Depends(require_session)):
    return {"items": list_submissions(db, ecomm_id), "external_writes_enabled": bool(get_settings().kiki_tiendanube_writes_enabled and get_settings().kiki_v2_writes_enabled and get_settings().kiki_tiendanube_read_enabled)}


@router.get("/{submission_id}")
def get(submission_id: int, db: Session = Depends(get_db), session=Depends(require_session)):
    return execute(db, lambda: get_submission(db, submission_id))


@router.post("/preview")
def preview(body: Preview, db: Session = Depends(get_db), session=Depends(require_csrf)):
    return execute(db, lambda: prepare_submission(db, session, get_settings(), **body.model_dump()))


@router.post("/{submission_id}/send")
def send(submission_id: int, body: Send, db: Session = Depends(get_db), session=Depends(require_csrf)):
    return execute(db, lambda: send_submission(db, session, get_settings(), submission_id, **body.model_dump()))
