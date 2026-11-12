"""Internal API-variant linkage review; never calls ML, TN, OAuth or imports CSV."""

from datetime import datetime, timezone
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from ...core.config import get_settings
from ...core.security import require_csrf, require_session
from ...database.session import get_db
from ...database.models import (
    CatalogSnapshot,
    EcommApiProductEdit,
    InventoryLinkageDecision,
    TiendanubeMatchDecision,
)
from ...integrations.ecomm_app.catalog_stage import STAGE_SOURCE, stage_status
from ...integrations.ecomm_app.api_catalog_browser import valid_variant_id
from ...services.ecomm_channel_coverage_service import build_channel_coverage
from ...services.ecomm_api_channel_evidence import PROFILE, decision_key

CHECKS = {"name", "brand", "presentation", "quantity", "sale_type", "codes"}


def enabled():
    if not get_settings().kiki_channel_workspace_enabled:
        raise HTTPException(
            403, "Revisión API de canales deshabilitada por configuración."
        )


router = APIRouter(
    prefix="/api/ecomm-app/workspace",
    tags=["api-channel-evidence"],
    dependencies=[Depends(enabled)],
)


class Review(BaseModel):
    model_config = ConfigDict(extra="forbid")
    channel: Literal["ml", "tn"]
    listing_id: str = Field(min_length=1, max_length=80)
    expected_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    expected_revision: int = Field(ge=0)
    decision: Literal["APPROVED", "REVOKED"]
    checks: set[
        Literal["name", "brand", "presentation", "quantity", "sale_type", "codes"]
    ]
    quantity_commercial: int = Field(ge=1, le=1000)
    reason: str = Field(min_length=20, max_length=600)


def report(db, ident):
    if not valid_variant_id(ident):
        raise ValueError("ID de variante inválido; no se consulta por SKU o EAN.")
    capture = db.scalar(
        select(CatalogSnapshot).where(CatalogSnapshot.source == STAGE_SOURCE)
    )
    pages = capture.payload if capture else []
    status = stage_status(pages)
    if (
        not status["complete"]
        or status["quality"].get("duplicate_variant_ids")
        or status["quality"].get("without_variant_id")
    ):
        raise ValueError(
            "Captura API incompleta; no se consulta Excel como alternativa."
        )
    edits = {e.ecomm_id: e for e in db.scalars(select(EcommApiProductEdit))}
    matrix = build_channel_coverage(db, pages, api_validation=True, edits=edits)
    item = matrix["items_by_id"].get(ident)
    if not item:
        raise ValueError("No existe una variante API única con este Ecomm ID.")
    return {
        **item,
        "sources": matrix["sources"],
        "policy": matrix["policy"],
        "external_writes_enabled": False,
        "scope": "API_VARIANT_CAPTURE_REVIEW",
    }


@router.get("/channels/listings")
def captured_listings(
    channel: Literal["ml", "tn"],
    q: str = Query("", max_length=80),
    page: int = Query(1, ge=1, le=100000),
    limit: int = Query(25, ge=1, le=50),
    linkage: Literal["all", "unlinked", "verified"] = "all",
    db: Session = Depends(get_db),
    session=Depends(require_session),
):
    from ...services.ecomm_channel_listings import listings

    try:
        return listings(db, channel, query=q, page=page, limit=limit, linkage=linkage)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None


@router.get("/{ecomm_id}/channels")
def read_channels(
    ecomm_id: str, db: Session = Depends(get_db), session=Depends(require_session)
):
    try:
        return report(db, ecomm_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None


@router.post("/{ecomm_id}/channels/review")
def review(
    ecomm_id: str,
    body: Review,
    db: Session = Depends(get_db),
    session=Depends(require_csrf),
):
    try:
        # Existing capture rows serialize reviews and exclude concurrent capture replacement.
        list(
            db.scalars(
                select(CatalogSnapshot)
                .where(
                    CatalogSnapshot.source.in_(
                        [STAGE_SOURCE, "MERCADOLIBRE_API", "TIENDANUBE"]
                    )
                )
                .order_by(CatalogSnapshot.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        )
        current = report(db, ecomm_id)
        candidate = next(
            (
                c
                for c in current[body.channel]["candidates"]
                if c["id"] == body.listing_id
            ),
            None,
        )
        if (
            not candidate
            or candidate["token"] != body.expected_fingerprint
            or candidate["revision"] != body.expected_revision
        ):
            raise ValueError(
                "La captura, identidad o decisión cambió; recuperá la versión nueva antes de decidir."
            )
        if body.decision == "APPROVED" and (
            not candidate["can_review"] or body.checks != CHECKS
        ):
            raise ValueError(
                "La vinculación requiere identidad sin conflictos y revisión explícita de todos sus datos."
            )
        source = db.scalar(
            select(CatalogSnapshot).where(
                CatalogSnapshot.source
                == ("MERCADOLIBRE_API" if body.channel == "ml" else "TIENDANUBE")
            )
        )
        rows = source.payload if source else []
        from ...services.ecomm_api_channel_evidence import row_key

        row = next(r for r in rows if row_key(body.channel, r) == body.listing_id)
        key = decision_key(body.channel, row)
        model, key_field = (
            (InventoryLinkageDecision, InventoryLinkageDecision.external_id)
            if body.channel == "ml"
            else (TiendanubeMatchDecision, TiendanubeMatchDecision.source_key)
        )
        record = db.scalar(select(model).where(key_field == key))
        previous_target = (
            (record.ecomm_id if body.channel == "ml" else record.target_ecomm_id)
            if record
            else None
        )
        if body.decision == "REVOKED" and (not record or previous_target != ecomm_id):
            raise ValueError(
                "Sólo se puede revocar la vinculación de esta variante exacta."
            )
        # Explicit operator attestation; False combo never silently supplies quantity=1.
        expected_qty = candidate["quantity_in_title"]
        if (
            body.decision == "APPROVED"
            and expected_qty is not None
            and body.quantity_commercial != expected_qty
        ):
            raise ValueError(
                "La cantidad declarada difiere de la presentación del canal."
            )
        if len(body.reason.strip()) < 20:
            raise ValueError("Registrá un motivo de revisión concreto.")
        at = datetime.now(timezone.utc)
        event = {
            "at": at.isoformat(),
            "actor": f"{get_settings().kiki_admin_username} · sesión {session.id}",
            "decision": body.decision,
            "ecomm_id": ecomm_id,
            "fingerprint": candidate["token"],
            "checks": sorted(body.checks),
            "quantity_commercial": body.quantity_commercial,
            "quantity_origin": "EXPLICIT_OPERATOR_ATTESTATION",
            "reason": body.reason.strip(),
            "external_writes": False,
            "identity": current["identity"],
            "channel_row": row,
            "snapshot_at": current[body.channel]["snapshot_at"],
            "source": current[body.channel]["source"],
        }
        if not record:
            record = (
                InventoryLinkageDecision(external_id=key, history=[])
                if body.channel == "ml"
                else TiendanubeMatchDecision(source_key=key, history=[])
            )
            db.add(record)
        record.source_snapshot = {
            "profile": PROFILE,
            "fingerprint": candidate["token"],
            "row": row,
            "checks": sorted(body.checks),
            "quantity_commercial": body.quantity_commercial,
        }
        target = {**current["identity"], "source": STAGE_SOURCE, "ecomm_id": ecomm_id}
        if body.channel == "ml":
            record.decision = body.decision
            record.ecomm_id = ecomm_id
            record.product_snapshot = target
        else:
            record.status = body.decision
            record.target_ecomm_id = ecomm_id
            record.target_snapshot = target
        record.note = body.reason.strip()
        record.updated_at = at
        record.history = [*(record.history or []), event]
        db.commit()
        return report(db, ecomm_id)
    except (ValueError, StopIteration) as exc:
        db.rollback()
        raise HTTPException(
            409, str(exc) or "Fila no disponible en la captura."
        ) from None
