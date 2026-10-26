"""Shared, persistent coordination for manual and scheduled Ecomm API captures.

A singleton CatalogSnapshot records the current job; SQL row locking serializes
starts across Render workers and GitHub Actions. No external catalog writes.
"""
from datetime import datetime, timedelta, timezone
from secrets import token_urlsafe

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ..database.models import CatalogSnapshot
from ..database.session import SessionLocal
from ..integrations.ecomm_app.catalog_stage import EcommAppStageService, REFRESH_SOURCE
from ..integrations.ecomm_app.public_api import EcommAppApiError, EcommAppInventoryClient
from ..core.config import get_settings
from ..repositories.catalog_repository import CatalogRepository

JOB_SOURCE = "ECOMM_APP_API_REFRESH_JOB"
STALE_AFTER = timedelta(minutes=45)
MAX_BATCHES = 110


def utcnow():
    return datetime.now(timezone.utc)


def _job_row(db, *, lock=False):
    query = select(CatalogSnapshot).where(CatalogSnapshot.source == JOB_SOURCE)
    return db.scalar(query.with_for_update() if lock else query)


def job_status(db):
    row = _job_row(db)
    state = row.payload[0] if row and isinstance(row.payload, list) and row.payload else None
    if not state:
        return None
    result = dict(state)
    if result.get("status") == "RUNNING":
        last = datetime.fromisoformat(result["heartbeat_at"])
        if utcnow() - last > STALE_AFTER:
            result["status"] = "INTERRUPTED"
            result["message"] = "La actualización se interrumpió. Podés iniciar una nueva."
    result.pop("owner", None)
    return result


def start_job(db, origin):
    if origin not in ("MANUAL", "SCHEDULED"):
        raise ValueError("Origen de actualización desconocido.")
    now = utcnow()
    row = _job_row(db, lock=True)
    state = row.payload[0] if row and row.payload else None
    if state and state.get("status") == "RUNNING":
        last = datetime.fromisoformat(state["heartbeat_at"])
        if now - last <= STALE_AFTER:
            db.rollback()
            raise HTTPException(409, "Ya hay una actualización de Ecomm-App en curso.")
    owner = token_urlsafe(18)
    new_state = {
        "owner": owner, "origin": origin, "status": "RUNNING",
        "started_at": now.isoformat(), "heartbeat_at": now.isoformat(),
        "finished_at": None, "pages_saved": 0, "expected_pages": None,
        "variants": None, "message": "Iniciando captura completa por API.",
    }
    if row:
        row.payload = [new_state]
        row.updated_at = now
    else:
        db.add(CatalogSnapshot(source=JOB_SOURCE, payload=[new_state], updated_at=now))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Otra actualización comenzó al mismo tiempo.") from None
    return owner


def require_active(db, *, owner=None, origin=None):
    row = _job_row(db, lock=True)
    state = row.payload[0] if row and row.payload else None
    if not state or state.get("status") != "RUNNING":
        db.rollback()
        raise HTTPException(409, "No hay una actualización en curso.")
    if owner is not None and state.get("owner") != owner:
        db.rollback()
        raise HTTPException(409, "Otra actualización tomó el control.")
    if origin is not None and state.get("origin") != origin:
        db.rollback()
        raise HTTPException(409, "La actualización está controlada por otro proceso.")
    return state["owner"]


def update_job(db, owner, *, status="RUNNING", pages_saved=None,
               expected_pages=None, variants=None, message=None):
    row = _job_row(db, lock=True)
    if not row or not row.payload or row.payload[0].get("owner") != owner:
        db.rollback()
        return False
    state = dict(row.payload[0])
    if state["status"] != "RUNNING":
        db.rollback()
        return False
    now = utcnow()
    state["heartbeat_at"] = now.isoformat()
    state["status"] = status
    if status != "RUNNING":
        state["finished_at"] = now.isoformat()
    if pages_saved is not None:
        state["pages_saved"] = pages_saved
    if expected_pages is not None:
        state["expected_pages"] = expected_pages
    if variants is not None:
        state["variants"] = variants
    if message is not None:
        state["message"] = message
    row.payload = [state]
    row.updated_at = now
    db.commit()
    return True


def reset_stage(db, owner):
    require_active(db, owner=owner)
    CatalogRepository(db).save_snapshot(REFRESH_SOURCE, [])


def note_step(db, owner, result):
    done = result["complete"]
    update_job(
        db, owner, status="SUCCESS" if done else "RUNNING",
        pages_saved=result["pages_saved"], expected_pages=result["expected_pages"],
        variants=result["quality"]["variants"],
        message="Catálogo API completo y actualizado." if done
        else "Descargando y comprobando páginas de Ecomm-App.",
    )


def fail_job(db, owner, message):
    update_job(db, owner, status="FAILED", message=message[:220])


def run_manual_refresh(owner):
    """Continue on the server after the browser receives the start response."""
    try:
        with SessionLocal() as db:
            reset_stage(db, owner)
        for _ in range(MAX_BATCHES):
            with SessionLocal() as db:
                require_active(db, owner=owner, origin="MANUAL")
                # release the read lock before I/O; the row remains RUNNING
                db.rollback()
                client = EcommAppInventoryClient(get_settings().ecomm_app_api_token)
                result = EcommAppStageService(db, client, REFRESH_SOURCE).next_batch()
                note_step(db, owner, result)
                if result["complete"]:
                    return
        raise ValueError("La captura excedió la cantidad máxima de páginas prevista.")
    except (EcommAppApiError, ValueError) as exc:
        message = "La API no pudo completar la captura. Se conservó la copia anterior."
        if isinstance(exc, EcommAppApiError):
            message = f"{exc.code}: {exc.message}"
        with SessionLocal() as db:
            fail_job(db, owner, message)
    except Exception:
        # Never expose vendor secrets or internal connection errors in status.
        with SessionLocal() as db:
            fail_job(db, owner, "No se completó la actualización. La copia anterior permanece disponible.")
