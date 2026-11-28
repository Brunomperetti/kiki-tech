"""Authenticated orchestration over the existing documentary queue; default OFF."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import require_csrf, require_session
from app.database.session import get_db
from app.services.documental.catalog_automation import CatalogAutomation
from app.services.documental.search_provider import SearchConfig, SearchProvider
from app.services.documental.source_fetch import allowed_hosts
from .commercial_exports import enabled, execute
from .documental_workspace import _resumable_intake_ready
from app.services.documental.local_documents import reader_available

router = APIRouter(
    prefix="/api/ecomm-app/workspace/research/automation",
    tags=["catalog-automation"],
    dependencies=[Depends(enabled)],
)


def make_automation(db, session):
    settings = get_settings()
    hosts = settings.kiki_document_source_fetch_hosts
    return CatalogAutomation(
        db,
        session,
        SearchProvider(
            SearchConfig(
                enabled=settings.kiki_research_search_enabled,
                provider=settings.kiki_research_search_provider,
                api_key=settings.kiki_research_search_api_key,
                max_requests=settings.kiki_research_search_max_requests,
                official_hosts=tuple(sorted(allowed_hosts(hosts))),
            )
        ),
        hosts,
        max_search_requests=settings.kiki_research_search_max_requests,
        daily_search_limit=settings.kiki_research_search_daily_requests,
        readiness_check=lambda: _resumable_intake_ready(db),
        network_enabled=bool(
            settings.kiki_research_search_enabled
            and settings.kiki_research_search_api_key.strip()
            and settings.kiki_document_explicit_url_intake_enabled
            and settings.kiki_document_source_fetch_hosts.strip()
        ),
    )


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Create(Strict):
    request_key: UUID
    ecomm_ids: list[str] = Field(min_length=1, max_length=20)
    confirm: Literal[True]


class Step(Strict):
    expected_revision: int = Field(ge=1)
    confirm: Literal[True]


class Retry(Step):
    ecomm_id: str = Field(pattern=r"^[1-9][0-9]{0,19}$")


@router.get("/capabilities")
def capabilities(session=Depends(require_session)):
    settings = get_settings()
    search = bool(
        settings.kiki_research_search_enabled
        and settings.kiki_research_search_api_key.strip()
    )
    download = bool(
        settings.kiki_document_explicit_url_intake_enabled
        and settings.kiki_document_source_fetch_hosts.strip()
        and settings.kiki_document_resumable_intake_enabled
        and settings.kiki_document_parser_kernel_required
        and reader_available()
    )
    return {
        "enabled": settings.kiki_research_search_enabled,
        "search_configured": search,
        "download_authorized": download,
        "max_items": 20,
        "provider": settings.kiki_research_search_provider,
        "real_external_calls_enabled": search and download,
        "paid_ai_enabled": False,
        "external_writes_enabled": False,
        "execution": "ONE_ITEM_PER_REQUEST_BROWSER_CONTROLS_PAUSE",
    }


@router.get("")
def listing(db: Session = Depends(get_db), session=Depends(require_session)):
    return execute(db, lambda: make_automation(db, session).listing())


@router.post("")
def create(body: Create, db: Session = Depends(get_db), session=Depends(require_csrf)):
    return execute(
        db,
        lambda: make_automation(db, session).create(
            str(body.request_key), body.ecomm_ids
        ),
    )


@router.get("/{job_id}")
def detail(
    job_id: UUID, db: Session = Depends(get_db), session=Depends(require_session)
):
    return execute(db, lambda: make_automation(db, session).detail(str(job_id)))


@router.post("/{job_id}/step")
def step(
    job_id: UUID,
    body: Step,
    db: Session = Depends(get_db),
    session=Depends(require_csrf),
):
    return execute(
        db,
        lambda: make_automation(db, session).step(str(job_id), body.expected_revision),
    )


@router.post("/{job_id}/recover")
def recover(
    job_id: UUID,
    body: Step,
    db: Session = Depends(get_db),
    session=Depends(require_csrf),
):
    def run():
        service = make_automation(db, session)
        service._job(str(job_id))
        service.queue.recover(str(job_id), body.expected_revision)
        return service.detail(str(job_id))

    return execute(db, run)


@router.post("/{job_id}/retry")
def retry(
    job_id: UUID,
    body: Retry,
    db: Session = Depends(get_db),
    session=Depends(require_csrf),
):
    def run():
        service = make_automation(db, session)
        service._job(str(job_id))
        service.queue.retry(str(job_id), body.expected_revision, body.ecomm_id)
        return service.detail(str(job_id))

    return execute(db, run)


@router.post("/{job_id}/cancel")
def cancel(
    job_id: UUID,
    body: Step,
    db: Session = Depends(get_db),
    session=Depends(require_csrf),
):
    def run():
        service = make_automation(db, session)
        service._job(str(job_id))
        service.queue.cancel(str(job_id), body.expected_revision)
        return service.detail(str(job_id))

    return execute(db, run)


@router.post("/{job_id}/proposals")
def proposals(
    job_id: UUID,
    body: Step,
    db: Session = Depends(get_db),
    session=Depends(require_csrf),
):
    return execute(
        db,
        lambda: make_automation(db, session).prepare_proposals(
            str(job_id), body.expected_revision
        ),
    )


class SelectSource(Retry):
    url: str = Field(min_length=9, max_length=1000)
    reason: str = Field(min_length=20, max_length=600)


@router.post("/{job_id}/select-source")
def select_source(
    job_id: UUID,
    body: SelectSource,
    db: Session = Depends(get_db),
    session=Depends(require_csrf),
):
    return execute(
        db,
        lambda: make_automation(db, session).select_source(
            str(job_id), body.expected_revision, body.ecomm_id, body.url, body.reason
        ),
    )
