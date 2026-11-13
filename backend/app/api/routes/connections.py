"""Compact projection of existing connections. Never probes a provider."""

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ...core.config import get_settings
from ...core.security import require_session
from ...database.session import get_db
from ...repositories.catalog_repository import CatalogRepository
from ...services.mercadolibre_service import MercadoLibreService
from .ecomm_app import ecomm_app_auto_status, ecomm_app_status

router = APIRouter(prefix="/api/connections", tags=["connections"])


def upcoming_updates(now=None):
    """Matches ecomm-api-refresh.yml: 11:25 and 19:25 UTC. Not a scheduler."""
    now = (now or datetime.now(timezone.utc)).astimezone(
        ZoneInfo("America/Argentina/Buenos_Aires")
    )
    candidates = [
        datetime.combine(now.date() + timedelta(days=day), time(hour, 25), now.tzinfo)
        for day in (0, 1)
        for hour in (8, 16)
    ]
    return [date.isoformat() for date in candidates if date > now][:2]


@router.get("/status")
def status(
    request: Request, db: Session = Depends(get_db), _session=Depends(require_session)
):
    settings = get_settings()
    repo = CatalogRepository(db)
    record = repo.snapshot_record("TIENDANUBE")
    rows = record.payload if record else []
    snapshot = repo.snapshot_record("MERCADOLIBRE_API")
    ml_rows = snapshot.payload if snapshot else []
    if (
        not isinstance(rows, list)
        or not isinstance(ml_rows, list)
        or any(not isinstance(row, dict) for row in [*rows, *ml_rows])
    ):
        raise ValueError("Captura de canal inválida; no se informa un cero ficticio.")
    ml = MercadoLibreService(db).status()
    # Same grain as ecomm_channel_listings: variations remain separate rows,
    # publication count is the unique MLA parent. Capture does not prove linkage.
    ml.update(
        {
            "last_sync": snapshot.updated_at.isoformat() if snapshot else None,
            "listing_count": len(ml_rows) if snapshot else None,
            "publication_count": len(
                {
                    str(row["external_id"]).split("#")[0]
                    for row in ml_rows
                    if row.get("external_id")
                }
            )
            if snapshot
            else None,
        }
    )
    isolated = getattr(request.app.state, "local_synthetic", False)
    test_actions = getattr(request.app.state, "connection_test_mode", False)
    return {
        "external_writes_enabled": False,
        "synthetic": isolated,
        "actions_enabled": (settings.kiki_v2_writes_enabled and settings.kiki_v2_connections_enabled) if request.headers.get("X-Kiki-UI") == "v2" else not isolated or test_actions,
        "external_oauth_allowed": not isolated and (settings.kiki_v2_connections_enabled if request.headers.get("X-Kiki-UI") == "v2" else True),
        "max_csv_bytes": min(settings.max_upload_mb, 20) * 1024 * 1024,
        "ecomm": {
            **ecomm_app_status(_session=_session),
            **ecomm_app_auto_status(db=db, _session=_session),
            "api_configured": bool(settings.ecomm_app_api_token.strip()),
            "live_authorization_verified": False,
            "schedule_timezone": "America/Argentina/Buenos_Aires",
            "schedule_times": ["08:25", "16:25"],
            "next_updates": upcoming_updates(),
            "github_schedule_verified": False,
        },
        "ml": ml,
        "tn": {
            "source": "TIENDANUBE_CSV",
            "available": bool(record),
            "imported_at": record.updated_at.isoformat() if record else None,
            "records": len(rows),
            "products": len({row.get("slug") for row in rows if row.get("slug")}),
            "current_publication_verified": False,
        },
    }
