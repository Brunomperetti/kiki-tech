"""Installed only by checked sandbox bootstrap, never production app.main."""

from typing import Literal, Annotated
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session
from app.core.security import require_csrf, require_session
from app.database.session import get_db
from app.api.routes.ecomm_api_workspace import SaveProductEdit
from app.services.ecomm_api_product_workspace_service import EcommApiProductWorkspace
from .proposals import Proposals
from .research.routes import execute
from .generation_contract import generation_context

router = APIRouter(prefix="/api/test-proposals", tags=["synthetic-proposals-only"])
editor_router = APIRouter()


@router.get("/{ecomm_id}/generation-context")
def context_for_future_generation(
    ecomm_id: str, db: Session = Depends(get_db), session=Depends(require_session)
):
    return execute(db, lambda: generation_context(db, session, ecomm_id))


class Generate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=0)


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["ACCEPTED", "REJECTED"]
    value: str | list[dict[str, str]]


class Review(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)
    decisions: dict[str, Decision] = Field(max_length=18)


@router.get("/{ecomm_id}")
def latest(
    ecomm_id: str, db: Session = Depends(get_db), session=Depends(require_session)
):
    return execute(db, lambda: Proposals(db, session).latest(ecomm_id))


@router.post("/{ecomm_id}/generate")
def generate(
    ecomm_id: str,
    body: Generate,
    db: Session = Depends(get_db),
    session=Depends(require_csrf),
):
    return execute(
        db, lambda: Proposals(db, session).generate(ecomm_id, body.expected_version)
    )


@router.post("/{ecomm_id}/{draft_id}/review")
def review(
    ecomm_id: str,
    draft_id: int,
    body: Review,
    db: Session = Depends(get_db),
    session=Depends(require_csrf),
):
    return execute(
        db,
        lambda: Proposals(db, session).review(
            ecomm_id,
            draft_id,
            body.expected_revision,
            {key: value.model_dump() for key, value in body.decisions.items()},
        ),
    )


@editor_router.post("/api/ecomm-app/workspace/{ecomm_id}")
def save_editor(
    ecomm_id: str,
    body: SaveProductEdit,
    proposal_id: Annotated[int | None, Header(alias="X-Kiki-Proposal-Id", ge=1)] = None,
    proposal_revision: Annotated[
        int | None, Header(alias="X-Kiki-Proposal-Revision", ge=1)
    ] = None,
    db: Session = Depends(get_db),
    session=Depends(require_csrf),
):
    try:
        if proposal_id is None and proposal_revision is None:
            return EcommApiProductWorkspace(db).save(
                ecomm_id,
                body.fields.model_dump(),
                body.status,
                body.expected_version,
            )
        if proposal_id is None or proposal_revision is None:
            raise ValueError(
                "Identificación y revisión de propuesta requeridas conjuntamente."
            )
        return Proposals(db, session).apply(
            ecomm_id, proposal_id, proposal_revision, body
        )
    except ValueError as exc:
        # Never commit a failed application/a partial APPLIED event.
        db.rollback()
        raise HTTPException(409, str(exc)) from None
