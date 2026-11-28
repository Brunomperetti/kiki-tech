"""Authenticated periodic tasks; no supplier or commercial mutations."""
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session
from app.core.security import require_session, require_csrf
from app.core.config import get_settings
from app.services.periodic_review_runner import enabled as runner_enabled, _load as runner_state
from app.database.session import get_db
from app.api.routes.documental_workspace import enabled
from app.services.monthly_catalog_reports import review_policy, save_review_policy, preview_periodic_review

router = APIRouter(prefix="/api/ecomm-app/workspace/reports/periodic", dependencies=[Depends(enabled)])

class PolicySettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool
    interval_days: int = Field(ge=1, le=30)
    evidence_max_age_days: int = Field(ge=1, le=365)
    soon_days: int = Field(ge=0, le=30)

class PolicySave(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=0)
    settings: PolicySettings
    reason: str = Field(min_length=20, max_length=600)
    confirm: Literal[True]

@router.get("/policy")
def get_policy(db: Session = Depends(get_db), session=Depends(require_session)):
    return {**review_policy(db), "background_worker_enabled": runner_enabled(get_settings())}

@router.post("/policy")
def set_policy(body: PolicySave, db: Session = Depends(get_db), session=Depends(require_csrf)):
    try:
        result = save_review_policy(db, session, expected_version=body.expected_version, settings=body.settings.model_dump(), reason=body.reason)
        return {**result, "background_worker_enabled": runner_enabled(get_settings())}
    except ValueError as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from None

@router.get("/tasks")
def get_tasks(page: int = Query(1, ge=1, le=10000), limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db), session=Depends(require_session)):
    try:
        result = preview_periodic_review(db, page=page, limit=limit)
        result["policy"]["background_worker_enabled"] = runner_enabled(get_settings())
        return result
    except ValueError as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from None


@router.get("/automation")
def automation_status(db: Session = Depends(get_db), session=Depends(require_session)):
    try:
        _row, state = runner_state(db)
        return {"enabled": runner_enabled(get_settings()), "external_writes_enabled": False,
                "scope": "ARCHIVED_CAPTURES_ONLY_NO_WEB_OR_HUMAN_APPROVAL",
                **{key: state.get(key) for key in ("state", "last_run", "next_due_at", "history")}}
    except ValueError as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from None
