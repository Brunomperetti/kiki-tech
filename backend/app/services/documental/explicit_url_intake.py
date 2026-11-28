"""Operator-approved, exact-URL manufacturer pilot without requiring a sitemap.

This solves the independent no-sitemap case only; one human-selected URL
per request, one archived original per variant/day. The source must pass the
existing pinned-TLS / public DNS / robots and no-redirect fetch guard.
No vendor writes, AI or approval of source, identity or individual facts.
"""
import base64
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256

from sqlalchemy import select

from app.services.documental.contracts import Incorporate
from app.services.documental.local_documents import LocalDocuments, parse_local
from app.services.documental.storage import Dossier, Document, digest
from app.services.editorial_batches.context import sources
from .manufacturer_batch_intake import _identity, _eligible_unit, _reject_duplicate_original
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



def _refresh_candidate(documents, url):
    selected = [doc for doc in documents if (doc.body.get("source") or {}).get("reference_url") == url]
    if len(selected) != 1:
        raise ValueError("La revisión periódica requiere un único original de esta variante y URL exacta.")
    doc = selected[0]
    body, source = doc.body, doc.body.get("source") or {}
    original = body.get("original") or {}
    if (doc.version >= 8 or digest(body) != doc.digest or body.get("origin_kind") != "FILE"
            or original.get("content_type") != "text/html"
            or source.get("capture_mode") != "ALLOWLISTED_HTTPS_FETCH"
            or source.get("review_state") not in {"PENDING", "REVIEWED"}):
        raise ValueError("Original sin integridad, revocado o límite de 8 versiones; requiere revisión manual.")
    try:
        raw = base64.b64decode(body.get("original_base64") or "", validate=True)
        if not raw or len(raw) > MAX_SOURCE_BYTES or original.get("size") != len(raw) or sha256(raw).hexdigest() != original.get("sha256"):
            raise ValueError
    except (ValueError, TypeError):
        raise ValueError("El original archivado no acredita SHA-256 y bytes íntegros; no se consultó la fuente.") from None
    return doc


def _refresh_quota(documents, case, *, today):
    for doc in documents:
        acquired = (doc.body.get("retrieval") or {}).get("acquired_at")
        if (doc.body.get("source") or {}).get("capture_mode") != "ALLOWLISTED_HTTPS_FETCH":
            continue
        try:
            observed = datetime.fromisoformat(acquired)
            if observed.tzinfo is None or observed.astimezone(timezone.utc).date() == today or observed > datetime.now(timezone.utc):
                raise ValueError
        except (ValueError, TypeError):
            raise ValueError("La variante ya fue consultada hoy o tiene fecha de descarga inválida; no se repite.") from None
    for event in case.history if case else []:
        if event.get("action") not in {"SOURCE_UNCHANGED_OBSERVED", "SOURCE_ORIGINAL_REFRESHED"}:
            continue
        try:
            when = datetime.fromisoformat(event.get("at"))
            if when.tzinfo is None or when.astimezone(timezone.utc).date() == today or when > datetime.now(timezone.utc):
                raise ValueError
        except (ValueError, TypeError):
            raise ValueError("Ya existe una observación de fuente de hoy o su fecha no es verificable.") from None


def _refresh_pin(doc):
    return (doc.id, doc.version, doc.digest, doc.body["original"]["sha256"])


def import_explicit_url(
    db, session, *, ecomm_id, expected_version, reference_url,
    provenance_note, configured_hosts,
    downloader=fetch_html, parser=parse_local,
    selection_mode="ONE_EXACT_OPERATOR_REVIEWED_URL",
    refresh_existing=False,
    expected_refresh_receipt=None,
    refresh_request_key=None,
):
    """Get one exact human-reviewed URL, archive only PENDING source.

    The first read is deliberately rolled back before outbound I/O to avoid
    holding the shared documentary mutex while the remote server responds.
    All identity and dossier-version checks are repeated after the GET.
    """
    if selection_mode not in {"ONE_EXACT_OPERATOR_REVIEWED_URL", "AUTOMATED_SEARCH_CANDIDATE"}:
        raise ValueError("Procedencia de selección no admitida.")
    if type(refresh_existing) is not bool or (refresh_existing and selection_mode != "AUTOMATED_SEARCH_CANDIDATE"):
        raise ValueError("La actualización de originales solo admite el circuito integral autorizado.")
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
    if not _eligible_unit(row):
        raise ValueError("Variante, SKU o presentación pack no apta para el piloto.")
    baseline = _identity(row)
    current = db.scalar(select(Dossier.version).where(Dossier.ecomm_id == ecomm_id))
    if (current if current is not None else 0) != expected_version:
        raise ValueError("El expediente cambió; actualizá antes de descargar.")
    today = datetime.now(timezone.utc).date()
    documents = _existing_documents(db, ecomm_id)
    refresh_pin = None
    if refresh_existing:
        existing = _refresh_candidate(documents, reference_url)
        _refresh_quota(documents, db.get(Dossier, ecomm_id), today=today)
        refresh_pin = _refresh_pin(existing)
        if expected_refresh_receipt is not None and expected_refresh_receipt != {
            "document_id": existing.id, "document_version": existing.version,
            "document_digest": existing.digest, "document_sha256": existing.body["original"]["sha256"],
        }:
            raise ValueError("El original ya no coincide con la versión fijada en el lote; no se descargó.")
    else:
        _reject_repeated(documents, reference_url, today=today)
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
        or trace.get("sha256") != sha256(original).hexdigest()
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
    if (
        not _eligible_unit(latest.get(ecomm_id))
        or _identity(latest.get(ecomm_id) or {}) != baseline
    ):
        raise ValueError(
            "La variante Ecomm-App cambió durante la consulta; no se archivó."
        )
    service = LocalDocuments(db, session)
    case = service.research.dossier(ecomm_id)
    service.research.expect(case, expected_version)
    existing_documents = service.research.documents(ecomm_id)
    if refresh_existing:
        existing = _refresh_candidate(existing_documents, reference_url)
        # Lock the same version after the documentary mutex: no metadata or
        # approval made during HTTP may be silently overwritten.
        existing = db.scalar(select(Document).where(Document.id == existing.id).with_for_update().execution_options(populate_existing=True))
        if _refresh_pin(existing) != refresh_pin:
            raise ValueError("El original cambió en otra sesión durante la consulta; no se reemplazó.")
        _refresh_quota(existing_documents, case, today=today)
        if trace["sha256"] == refresh_pin[3]:
            proof = _refresh_proof(existing, refresh_pin, reference_url, "UNCHANGED", refresh_request_key, trace)
            service.research.commit_change(case, deepcopy(case.facts), "SOURCE_UNCHANGED_OBSERVED", {
                "document_id": existing.id, "document_version": existing.version,
                "document_hash": existing.digest, "document_sha256": trace["sha256"],
                "reference_url": reference_url, "observed_at": datetime.now(timezone.utc).isoformat(),
                "request_count": trace.get("request_count") if type(trace.get("request_count")) is int else None,
                "human_review_performed": False, "automatic_approvals": 0,
                "refresh_receipt": proof,
            })
            result = service.research.serialize(case)
            result.update(incorporated_document_id=existing.id, refresh_outcome="UNCHANGED",
                          observed_document_version=existing.version, observed_document_sha256=trace["sha256"],
                          refresh_receipt=proof)
            db.commit()
            return result
        _reject_duplicate_original([doc for doc in existing_documents if doc.id != existing.id], trace["sha256"])
        imported = imported.model_copy(update={"document_id": existing.id, "expected_document_version": existing.version})
    else:
        _reject_repeated(existing_documents, reference_url, today=today)
        _reject_duplicate_original(existing_documents, trace["sha256"])
    result = service.incorporate(
        ecomm_id, imported, parsed,
        source_retrieval={
            **trace,
            "mode": "ALLOWLISTED_SEARCH_CANDIDATE_URL" if selection_mode == "AUTOMATED_SEARCH_CANDIDATE" else "ALLOWLISTED_EXPLICIT_OPERATOR_URL",
            "selection_mode": selection_mode,
        },
    )
    if refresh_existing:
        current_doc = service.document(ecomm_id, refresh_pin[0])
        proof = _refresh_proof(current_doc, refresh_pin, reference_url, "CHANGED_REQUIRES_HUMAN_REVIEW", refresh_request_key, trace)
        service.research.commit_change(case, deepcopy(case.facts), "SOURCE_ORIGINAL_REFRESHED", {
            "refresh_receipt": proof, "human_review_performed": False, "automatic_approvals": 0,
        })
        result = service.research.serialize(case)
        result.update(incorporated_document_id=current_doc.id, refresh_outcome="CHANGED_REQUIRES_HUMAN_REVIEW", refresh_receipt=proof)
    db.commit()
    return result


def _refresh_proof(doc, prior, url, outcome, request_key, trace):
    return {
        "prior": {"document_id": prior[0], "document_version": prior[1],
                  "document_digest": prior[2], "document_sha256": prior[3]},
        "current": {"document_id": doc.id, "document_version": doc.version,
                    "document_digest": doc.digest, "document_sha256": doc.body["original"]["sha256"]},
        "ecomm_id": doc.body["associated_ecomm_id"], "url": url,
        "outcome": outcome, "request_key": request_key,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "observed_request_count": trace.get("request_count") if type(trace.get("request_count")) is int else None,
    }


def verified_refresh_result(db, item, result):
    """Validate a committed backend proof, not a client-supplied approval."""
    from .source_intake_pipeline import PipelineError, receipt_for_document
    proof = result.get("refresh_receipt") if isinstance(result, dict) else None
    expected = (item.get("automation") or {}).get("refresh_receipt")
    if (not isinstance(proof, dict) or not isinstance(expected, dict)
            or not isinstance(item.get("claim_token"), str) or not item["claim_token"]
            or proof.get("prior") != expected
            or proof.get("request_key") != item.get("claim_token")
            or proof.get("ecomm_id") != item["ecomm_id"] or proof.get("url") != item["url"]):
        raise PipelineError("REFRESH_PROOF_MISSING", "La actualización no acreditó su recibo exacto; revisar sin repetir la descarga.")
    case = db.get(Dossier, item["ecomm_id"])
    if not case or not any((event.get("detail") or {}).get("refresh_receipt") == proof
                           for event in case.history if event.get("action") in {"SOURCE_UNCHANGED_OBSERVED", "SOURCE_ORIGINAL_REFRESHED"}):
        raise PipelineError("REFRESH_PROOF_MISSING", "No existe una observación persistida de esta actualización.")
    current = proof.get("current") or {}
    doc = db.get(Document, current.get("document_id"))
    if (not doc or doc.body.get("associated_ecomm_id") != item["ecomm_id"]
            or doc.body.get("source", {}).get("reference_url") != item["url"]
            or current != {"document_id": doc.id, "document_version": doc.version,
                           "document_digest": doc.digest, "document_sha256": doc.body.get("original", {}).get("sha256")}
            or current.get("document_id") != expected.get("document_id")):
        raise PipelineError("DOCUMENT_CHANGED", "El original cambió después de obtenerlo; requiere contraste humano.")
    outcome = proof.get("outcome")
    if outcome == "UNCHANGED":
        valid = current == expected
    else:
        valid = (outcome == "CHANGED_REQUIRES_HUMAN_REVIEW"
                 and current.get("document_version") == expected.get("document_version", 0) + 1
                 and current.get("document_sha256") != expected.get("document_sha256")
                 and doc.body.get("source", {}).get("review_state") == "PENDING")
    if not valid:
        raise PipelineError("REFRESH_PROOF_MISSING", "La actualización no acredita la transición esperada del original.")
    detached = deepcopy(item)
    detached["processing"] = {key: value for key, value in (item.get("processing") or {}).items()
                              if key not in {"document_id", "document_version", "document_digest", "document_sha256"}}
    receipt = receipt_for_document(db, detached, doc.id, allow_current=True)
    if (item.get("processing") or {}).get("request_measurement_pending"):
        previous = (item.get("processing") or {}).get("http_requests_reported", 0)
        reported = proof.get("observed_request_count")
        receipt["http_requests_reported"] = previous + reported if type(previous) is int and type(reported) is int and 0 <= reported <= 32 else None
        receipt["request_measurement_pending"] = False
    receipt["refresh_verified"] = True
    return doc.id, receipt


def recover_refresh_result(db, item):
    case = db.get(Dossier, item["ecomm_id"])
    for event in reversed(case.history if case else []):
        proof = (event.get("detail") or {}).get("refresh_receipt")
        if isinstance(proof, dict) and proof.get("request_key") == item.get("claim_token"):
            return verified_refresh_result(db, item, {"refresh_receipt": proof})
    from .source_intake_pipeline import PipelineError
    raise PipelineError("REFRESH_PROOF_MISSING", "La consulta interrumpida no acredita una actualización; requiere revisión o reintento explícito.", retryable=True)
