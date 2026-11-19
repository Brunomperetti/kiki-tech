"""Operator-approved, exact-URL manufacturer pilot without requiring a sitemap.

This solves the independent no-sitemap case only; one human-selected URL
per request, one archived original per variant/day. The source must pass the
existing pinned-TLS / public DNS / robots and no-redirect fetch guard.
No vendor writes, AI or approval of source, identity or individual facts.
"""
import base64
from datetime import datetime, timezone

from sqlalchemy import select

from app.services.documental.contracts import Incorporate
from app.services.documental.local_documents import LocalDocuments, parse_local
from app.services.documental.storage import Dossier, Document
from app.services.editorial_batches.context import sources
from .manufacturer_batch_intake import _identity
from .source_fetch import fetch_html, allowed_hosts, target

MAX_SOURCE_BYTES = 4 * 1024 * 1024


def _existing_documents(db, ecomm_id):
    return db.scalars(
        select(Document).where(
            Document.body["associated_ecomm_id"].as_string() == ecomm_id
        )
    ).all()


def _reject_repeated(documents, url, *, today):
    for item in documents:
        source = item.body.get("source") or {}
        if source.get("reference_url") == url:
            raise ValueError(
                "La misma URL ya está archivada para esta variante. "
                "Revisá el documento original antes de repetir una descarga."
            )
        # Existing manual uploads do not spend an automated request quota.
        trace = item.body.get("retrieval") or {}
        acquired = trace.get("acquired_at")
        if (
            source.get("capture_mode") == "ALLOWLISTED_HTTPS_FETCH"
            and isinstance(acquired, str)
        ):
            try:
                accessed_date = datetime.fromisoformat(acquired).date()
            except ValueError:
                raise ValueError(
                    "Historial de consultas inconsistente; consulta bloqueada."
                ) from None
            if accessed_date == today:
                raise ValueError(
                    "La variante ya tiene una descarga automatizada de hoy."
                )


def import_explicit_url(
    db, session, *, ecomm_id, expected_version, reference_url,
    provenance_note, configured_hosts,
    downloader=fetch_html, parser=parse_local,
):
    """Get one exact human-reviewed URL, archive only PENDING source.

    The first read is deliberately rolled back before outbound I/O to avoid
    holding the shared documentary mutex while the remote server responds.
    All identity and dossier-version checks are repeated after the GET.
    """
    allowed = allowed_hosts(configured_hosts)
    host, _ = target(reference_url, allowed)
    if not isinstance(ecomm_id, str) or not ecomm_id.isdecimal():
        raise ValueError("Ecomm ID inválido.")
    if not 0 <= expected_version <= 1_000_000:
        raise ValueError("Versión documental inválida.")
    if not 10 <= len(provenance_note.strip()) <= 600:
        raise ValueError("Describí el origen de esta página (10-600 caracteres).")
    initial = sources(db)
    row = initial.get(ecomm_id)
    if not row or not row.get("sku") or row.get("is_combo") is not False:
        raise ValueError("Variante, SKU o presentación pack no apta para el piloto.")
    baseline = _identity(row)
    current = db.scalar(select(Dossier.version).where(Dossier.ecomm_id == ecomm_id))
    if (current if current is not None else 0) != expected_version:
        raise ValueError("El expediente cambió; actualizá antes de descargar.")
    today = datetime.now(timezone.utc).date()
    _reject_repeated(
        _existing_documents(db, ecomm_id), reference_url, today=today
    )
    # None of these reads may hold locks while making a network call.
    db.rollback()

    original, trace = downloader(
        reference_url, configured_hosts, max_bytes=MAX_SOURCE_BYTES
    )
    if (
        not original or len(original) > MAX_SOURCE_BYTES
        or trace.get("requested_url") != reference_url
        or trace.get("final_url") != reference_url
        or trace.get("host") != host
        or trace.get("robots_checked") is not True
        or trace.get("tls_hostname_verified") is not True
        or trace.get("network_enabled") is not True
        or trace.get("redirects_followed") != 0
    ):
        raise ValueError("La descarga no acreditó todos los controles HTTPS y robots.")
    imported = Incorporate(
        kind="FILE",
        web_snapshot=True,
        expected_version=expected_version,
        filename="fabricante-" + trace["sha256"][:16] + ".html",
        content_type="text/html",
        content_base64=base64.b64encode(original).decode("ascii"),
        provenance_note=provenance_note.strip(),
        reference_url=reference_url,
        declared_official=False,
        declared_consulted_at=datetime.now(timezone.utc),
        authorized_local_processing=True,
    )
    parsed = parser(imported)

    # The API capture can change between selecting and obtaining the page.
    # Never silently attach it to an edited/renumbered Ecomm variant.
    db.expire_all()
    latest = sources(db, lock=True)
    if _identity(latest.get(ecomm_id) or {}) != baseline:
        raise ValueError(
            "La variante Ecomm-App cambió durante la consulta; no se archivó."
        )
    service = LocalDocuments(db, session)
    case = service.research.dossier(ecomm_id)
    service.research.expect(case, expected_version)
    _reject_repeated(
        service.research.documents(ecomm_id), reference_url, today=today
    )
    result = service.incorporate(
        ecomm_id, imported, parsed,
        source_retrieval={
            **trace,
            "mode": "ALLOWLISTED_EXPLICIT_OPERATOR_URL",
            "selection_mode": "ONE_EXACT_OPERATOR_REVIEWED_URL",
        },
    )
    db.commit()
    return result
