"""Human resolution of ambiguous search references; never fetches or approves.

Only an already-persisted, allowlisted official *candidate* can be selected.
The original job identity, attempt limits and reserved cost counters survive.
"""
from copy import deepcopy

from sqlalchemy import select

from app.services.editorial_batches.context import sources
from .source_fetch import target
from .source_intake_queue import MAX_ATTEMPTS, _processing, now
from .source_intake_pipeline import check_identity
from .storage import Document

MAX_SELECTION_HISTORY = 20


def select_source(service, jobid, expected_revision, ecommid, url, reason):
    if type(expected_revision) is not int or expected_revision < 1:
        raise ValueError("Revisión de lote inválida")
    if not isinstance(reason, str) or not 20 <= len(reason.strip()) <= 600:
        raise ValueError("Explicá la selección humana de fuente (20 a 600 caracteres)")
    # _job validates this is the integral workflow. The existing queue locks
    # the documentary Control singleton and job in the established order.
    job = service._job(jobid, locked=True)
    if job.revision != expected_revision:
        raise ValueError("El lote cambió; recuperá la revisión actual antes de seleccionar")
    if job.state in {"CANCELLED", "COMPLETED"} or any(row["state"] == "RUNNING" for row in job.items):
        raise ValueError("El lote está cancelado o tiene un paso activo")
    rows = deepcopy(job.items)
    row = next((item for item in rows if item["ecomm_id"] == ecommid), None)
    if not row or row["state"] not in {"PENDING", "BLOCKED"}:
        raise ValueError("Seleccioná una variante pendiente o bloqueada del mismo lote")
    if type(row.get("attempts")) is not int or not 0 <= row["attempts"] < MAX_ATTEMPTS:
        raise ValueError("La variante agotó los intentos; seleccionar una fuente no reinicia el presupuesto")
    if row.get("document_id") or (row.get("processing") or {}).get("document_id"):
        raise ValueError("La variante ya tiene un original; conservá su revisión documental")
    if row.get("url") and service.db.scalar(select(Document.id).where(
            Document.body["associated_ecomm_id"].as_string() == ecommid,
            Document.body["source"]["reference_url"].as_string() == row["url"]).limit(1)):
        raise ValueError("Ya existe un original archivado para esta fuente; recuperá su procesamiento")
    check_identity(row, sources(service.db))
    metadata = row.get("automation") or {}
    search = metadata.get("search") or {}
    candidates = search.get("results") or []
    if (not isinstance(url, str) or not any(isinstance(found, dict)
            and found.get("url") == url and found.get("source_kind") == "OFFICIAL_CANDIDATE"
            for found in candidates)):
        raise ValueError("La URL debe ser una referencia oficial candidata ya registrada en este lote")
    target(url, service.queue.hosts)  # Pure validation; no DNS or HTTP.
    history = list(metadata.get("source_selections") or [])
    history.append({"url": url, "previous_url": row.get("url"),
                    "reason": reason.strip(), "at": now().isoformat(),
                    "by": service.queue.actor, "ecomm_id": ecommid,
                    "previous_error_code": _processing(row).get("error_code"),
                    "official_verified": False, "facts_approved": 0})
    if len(history) > MAX_SELECTION_HISTORY:
        metadata["source_selection_events_dropped"] = metadata.get("source_selection_events_dropped", 0) + len(history) - MAX_SELECTION_HISTORY
    metadata["source_selections"] = history[-MAX_SELECTION_HISTORY:]
    metadata["phase"] = "SOURCE_SELECTED_PENDING_REVIEW"
    metadata["official_verified"] = False
    row.update(url=url, state="PENDING", error=None, next_action="IMPORT_SELECTED_SOURCE",
               claim_token=None, claim_until=None, automation=metadata)
    row["processing"] = {**_processing(row), "phase": "PENDING", "error_code": None, "retryable": False}
    service.queue._update(job, rows, "HUMAN_SOURCE_SELECTED_PENDING_REVIEW")
    return service.detail(jobid)
