"""Same-origin UI capabilities. Reuses authentication; no DDL or provider calls."""

from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import inspect, select
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.core.security import require_session
from app.database.session import get_db

router = APIRouter(prefix="/api/ui/v2", tags=["v2-rollout"])


def capabilities(db, synthetic=False):
    from app.database.models import Base
    from app.services.documental.storage import ResearchBase, Control
    from app.services.editorial_batches.storage import EditorialBase

    config = get_settings()
    inspector = inspect(db.get_bind())
    tables = set(inspector.get_table_names())

    def missing(metadata):
        result = []
        for table in metadata.sorted_tables:
            if table.name not in tables:
                result.append(table.name)
            else:
                columns = {c["name"] for c in inspector.get_columns(table.name)}
                result.extend(f"{table.name}.{c.name}" for c in table.columns if c.name not in columns)
        return result

    documents_missing = missing(ResearchBase.metadata)
    batches_missing = missing(EditorialBase.metadata)
    core_missing = missing(Base.metadata)
    if not documents_missing:
        if db.scalar(select(Control.id).where(Control.id == 1)) is None:
            documents_missing.append("kiki_evidence_control.row_1")
        indices = {i["name"] for i in inspector.get_indexes("kiki_evidence_documents")}
        if "kiki_evidence_documents_variant" not in indices:
            documents_missing.append("kiki_evidence_documents_variant")
    if not batches_missing:
        expected = {
            "kiki_editorial_batches": {"kiki_editorial_batches_created", "kiki_editorial_claimable"},
            "kiki_editorial_batch_items": {"kiki_editorial_items_state", "kiki_editorial_active_identity"},
        }
        for table, names in expected.items():
            actual = {i["name"] for i in inspector.get_indexes(table)}
            batches_missing.extend(sorted(names - actual))
    documents = config.kiki_document_workspace_enabled and not documents_missing
    return {
        "contract": "kiki-same-origin-v2-1",
        "synthetic": synthetic,
        "enabled": config.kiki_v2_enabled,
        "writes": config.kiki_v2_writes_enabled,
        "connections": config.kiki_v2_connections_enabled,
        "documents": documents,
        "document_upload": documents and Path("/document-parser/parser.sock").is_socket(),
        "channels": config.kiki_channel_workspace_enabled,
        "batches": documents and config.kiki_editorial_batches_enabled and not batches_missing,
        "executor": config.kiki_editorial_executor_enabled,
        "openai_configured": config.kiki_ai_enabled and bool(config.kiki_ai_api_key),
        "openai_generation": config.kiki_v2_ai_generation_enabled and config.kiki_ai_enabled and bool(config.kiki_ai_api_key),
        "evidence_openai_generation": False,
        "external_research": False,
        "missing_schema": {"core": core_missing, "documents": documents_missing, "batches": batches_missing},
        "legacy_path": "/dashboard-classic",
    }


@router.get("")
def configuration(request: Request, db: Session = Depends(get_db), _session=Depends(require_session)):
    if not get_settings().kiki_v2_enabled:
        raise HTTPException(404, "KIKI Tech 2.0 no está habilitado en este backend.")
    result = capabilities(db, getattr(request.app.state, "local_synthetic", False))
    if result["missing_schema"]["core"]:
        raise HTTPException(503, "Esquema original pendiente de validación; no se ejecutaron migraciones automáticas.")
    return result


def guard_request(path, method, db):
    """Only v2-tagged requests. Classic contracts and operators are unchanged."""
    config = get_settings()
    if path in {"/api/auth/login", "/api/auth/logout", "/api/auth/me"}:
        return
    if not config.kiki_v2_enabled:
        raise HTTPException(404, "KIKI Tech 2.0 deshabilitado.")
    if method != "GET" and not config.kiki_v2_writes_enabled:
        raise HTTPException(403, "KIKI Tech 2.0 está en modo de sólo lectura.")
    if path in {"/api/ecomm-app/stage/manual/start", "/api/mercadolibre/auth-url", "/api/mercadolibre/sync", "/api/tiendanube/import-csv"}:
        if not config.kiki_v2_connections_enabled:
            raise HTTPException(403, "Actualizaciones y OAuth requieren habilitación explícita.")
    if path.endswith("/suggest") and not config.kiki_v2_ai_generation_enabled:
        raise HTTPException(403, "Consumo OpenAI no autorizado para esta interfaz.")
    if "/editorial-batches" in path or any(part in path for part in ("/evidence", "/documents", "/proposals")):
        caps = capabilities(db)
        if ("/editorial-batches" in path and not caps["batches"]) or ("/editorial-batches" not in path and not caps["documents"]):
            raise HTTPException(403, "Función pendiente de configuración y esquema validado.")
