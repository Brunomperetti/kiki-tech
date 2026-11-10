from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal
from sqlalchemy.orm import Session
from app.core.security import require_csrf
from app.database.session import get_db
from .research.routes import execute
from .assisted_research import AssistedResearch

router = APIRouter(prefix="/api/test-discovery", tags=["simulated-discovery-only"])


class Start(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=0)
    expected_workspace_version: int = Field(ge=0)


class Candidate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=0)
    run_id: str = Field(pattern=r"^[a-f0-9]{24}$")
    expected_candidate_version: int = Field(ge=1)


class Decision(Candidate):
    decision: Literal["SELECTED", "REJECTED"]
    reason: str = Field(min_length=10, max_length=600)


@router.post("/{ident}/start")
def start(
    ident: str,
    body: Start,
    db: Session = Depends(get_db),
    session=Depends(require_csrf),
):
    return execute(
        db,
        lambda: AssistedResearch(db, session).start(
            ident, body.expected_version, body.expected_workspace_version
        ),
    )


@router.post("/{ident}/candidates/{candidate_id}/decision")
def decision(
    ident: str,
    candidate_id: str,
    body: Decision,
    db: Session = Depends(get_db),
    session=Depends(require_csrf),
):
    return execute(
        db, lambda: AssistedResearch(db, session).decision(ident, body, candidate_id)
    )


@router.post("/{ident}/candidates/{candidate_id}/acquire")
def acquire(
    ident: str,
    candidate_id: str,
    body: Candidate,
    db: Session = Depends(get_db),
    session=Depends(require_csrf),
):
    return execute(
        db, lambda: AssistedResearch(db, session).acquire(ident, body, candidate_id)
    )
