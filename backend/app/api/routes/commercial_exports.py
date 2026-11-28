"""Existing authenticated workspace: preview, reports and review-only CSV."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import require_session, require_csrf
from app.database.session import get_db
from app.services.contractual_delivery_audit_service import build_delivery_audit
from app.services.commercial_channel_export_service import (
    preview_commercial_export,
    download_commercial_export,
    download_monthly_report,
)
from app.services.monthly_catalog_reports import (
    save_monthly_report,
    monthly_report,
    acknowledge_monthly_report,
    list_monthly_reports,
    download_archived_report,
)


def enabled():
    if not get_settings().kiki_document_workspace_enabled:
        raise HTTPException(
            403,
            "Exportaciones y revisión documental requieren el espacio documental habilitado.",
        )


router = APIRouter(
    prefix="/api/ecomm-app/workspace",
    tags=["commercial-review-exports"],
    dependencies=[Depends(enabled)],
)


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CommercialPreview(Strict):
    channel: Literal["ml", "tn"]
    ecomm_ids: list[str] = Field(min_length=1, max_length=20)


class TiendanubePreview(Strict):
    ecomm_id: str = Field(pattern=r"^[1-9][0-9]{0,19}$")


class CommercialDownload(CommercialPreview):
    expected_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    confirm: Literal[True]


class MonthlyDownload(Strict):
    expected_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    confirm: Literal[True]


class MonthlySave(MonthlyDownload):
    responsible: str = Field(min_length=2, max_length=120)


class MonthlyAcknowledgement(MonthlyDownload):
    expected_revision: int = Field(ge=1)
    reason: str = Field(min_length=25, max_length=600)


def execute(db, operation):
    try:
        return operation()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from None


def csv_response(data, filename, count, fingerprint):
    return Response(
        data,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "X-Kiki-Export-Variants": str(count),
            "X-Kiki-Preview-Fingerprint": fingerprint,
        },
    )


@router.post("/exports/commercial/preview")
def commercial_preview(
    body: CommercialPreview,
    db: Session = Depends(get_db),
    session=Depends(require_csrf),
):
    return execute(
        db, lambda: preview_commercial_export(db, session, body.channel, body.ecomm_ids)
    )


@router.post("/exports/commercial/download")
def commercial_download(
    body: CommercialDownload,
    db: Session = Depends(get_db),
    session=Depends(require_csrf),
):
    def operation():
        data, preview = download_commercial_export(
            db, session, body.channel, body.ecomm_ids, body.expected_fingerprint
        )
        return csv_response(
            data,
            f"kiki-comercial-{body.channel}-revision.csv",
            preview["total"],
            preview["preview_fingerprint"],
        )

    return execute(db, operation)


@router.get("/reports/monthly/preview")
def monthly_preview(db: Session = Depends(get_db), _session=Depends(require_session)):
    return execute(db, lambda: build_delivery_audit(db)[0])


@router.post("/reports/monthly/download")
def monthly_download(
    body: MonthlyDownload, db: Session = Depends(get_db), _session=Depends(require_csrf)
):
    def operation():
        data, summary = download_monthly_report(db, body.expected_fingerprint)
        return csv_response(
            data,
            "kiki-auditoria-comercial-mensual.csv",
            summary["total"],
            summary["preview_fingerprint"],
        )

    return execute(db, operation)


@router.post("/reports/monthly")
def save_report(
    body: MonthlySave, db: Session = Depends(get_db), session=Depends(require_csrf)
):
    return execute(
        db,
        lambda: {
            key: value
            for key, value in save_monthly_report(
                db, session, body.expected_fingerprint, body.responsible
            ).items()
            if key != "rows"
        },
    )


@router.get("/reports/monthly")
def reports(
    page: int = Query(1, ge=1, le=10000),
    limit: int = Query(12, ge=1, le=12),
    db: Session = Depends(get_db),
    _session=Depends(require_session),
):
    return execute(db, lambda: list_monthly_reports(db, limit, page))


@router.get("/reports/monthly/{report_id}")
def report(
    report_id: str, db: Session = Depends(get_db), _session=Depends(require_session)
):
    return execute(db, lambda: monthly_report(db, report_id))


@router.post("/reports/monthly/{report_id}/acknowledge")
def acknowledge(
    report_id: str,
    body: MonthlyAcknowledgement,
    db: Session = Depends(get_db),
    session=Depends(require_csrf),
):
    return execute(
        db,
        lambda: {
            key: value
            for key, value in acknowledge_monthly_report(
                db,
                session,
                report_id,
                body.expected_revision,
                body.expected_fingerprint,
                body.reason,
            ).items()
            if key != "rows"
        },
    )


@router.post("/reports/monthly/{report_id}/download")
def archived_download(
    report_id: str,
    body: MonthlyDownload,
    db: Session = Depends(get_db),
    _session=Depends(require_csrf),
):
    def operation():
        data, report = download_archived_report(
            db, report_id, body.expected_fingerprint
        )
        return csv_response(
            data,
            "kiki-auditoria-comercial-mensual.csv",
            report["summary"]["total"],
            report["fingerprint"],
        )

    return execute(db, operation)


@router.post("/tiendanube/preview")
def tiendanube_preview(
    body: TiendanubePreview,
    db: Session = Depends(get_db),
    session=Depends(require_csrf),
):
    from app.services.tiendanube_publication_preview import local_preview

    return execute(db, lambda: local_preview(db, session, body.ecomm_id))


@router.post("/mercadolibre/preview")
def mercadolibre_preview(
    body: TiendanubePreview,
    db: Session = Depends(get_db),
    session=Depends(require_csrf),
):
    from app.services.mercadolibre_publication_preview import local_preview

    return execute(db, lambda: local_preview(db, session, body.ecomm_id))


@router.post("/tiendanube/connection/check")
def tiendanube_connection_check(_session=Depends(require_csrf)):
    from app.services.tiendanube_connection import check_connection

    result = check_connection(get_settings())
    return result
