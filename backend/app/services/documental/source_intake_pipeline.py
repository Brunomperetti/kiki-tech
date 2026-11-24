"""Local, idempotent documentary candidate processing for the existing queue.

An archived source remains PENDING. This module neither approves facts nor
creates commercial drafts, contacts suppliers, invokes AI or changes a fiche.
"""

import base64
import binascii
from copy import deepcopy
from hashlib import sha256
import re

from sqlalchemy import select

from app.services.documental.research import Research
from app.services.documental.storage import Document, digest
from app.services.editorial_batches.context import AtomicSession, sources
from app.services.ecomm_api_product_workspace_service import _gtin_check_digit_valid
from .source_fetch import SourceFetchError, SourceTransportError

PIPELINE_SCHEMA = "kiki-documental-pipeline-v1"
IDENTITY_KEYS = (
    "ecomm_id",
    "sku",
    "product_name",
    "variant_description",
    "gtin",
    "barcode",
    "gtin_raw",
    "is_combo",
    "parent_is_combo",
    "identity_blockers",
    "parent_code",
    "brand",
    "manufacturer",
)


class PipelineError(ValueError):
    def __init__(self, code, message, *, retryable=False):
        self.code = code
        self.public_message = message
        self.retryable = retryable
        super().__init__(message)


def identity_pin(row):
    # Preserve strings, zeroes, False and unknown flags separately. No parent
    # EAN, SKU or historical spreadsheet is promoted to a variant identity.
    return {key: deepcopy(row.get(key)) for key in IDENTITY_KEYS}


def check_identity(item, catalog):
    if item.get("identity_schema") != 2 or not item.get("expected_identity_v2"):
        raise PipelineError(
            "LEGACY_IDENTITY_REVIEW_REQUIRED",
            "Lote anterior sin identidad completa firmada; requiere una selección nueva revisada.",
        )
    ident = item["ecomm_id"]
    row = catalog.get(ident)
    expected = item["expected_identity_v2"]
    if (
        not row
        or expected != identity_pin(row)
        or item.get("identity_digest") != digest(expected)
        or item.get("identity_digest") != digest(identity_pin(row))
    ):
        raise PipelineError(
            "API_IDENTITY_CHANGED",
            "Cambió la identidad en Ecomm-App; revisar la variante antes de continuar.",
        )
    if row.get("identity_blockers"):
        raise PipelineError(
            "API_CODE_CONFLICT",
            "Barcode y GTIN originales contradictorios; no se procesa la fuente.",
        )
    if row.get("is_combo") is not False or row.get("parent_is_combo") is True:
        raise PipelineError(
            "PACK_REVIEW_REQUIRED",
            "Pack o tipo de venta sin identidad individual inequívoca; requiere revisión.",
        )
    sku = str(row.get("sku") or "").strip().casefold()
    if (
        not sku
        or sum(
            str(other.get("sku") or "").strip().casefold() == sku
            for other in catalog.values()
        )
        != 1
    ):
        raise PipelineError(
            "AMBIGUOUS_API_SKU",
            "SKU ausente o compartido entre variantes; requiere revisar la identidad.",
        )
    raw = row.get("gtin")
    if raw not in (None, ""):
        if not isinstance(raw, str) or not _gtin_check_digit_valid(raw):
            raise PipelineError(
                "INVALID_API_CODE",
                "Código API inválido o numérico sin ceros verificables; requiere revisión.",
            )

        def same_code(other):
            code = other.get("gtin")
            return (
                isinstance(code, str)
                and bool(code)
                and _gtin_check_digit_valid(code)
                and code.zfill(14) == raw.zfill(14)
            )

        if sum(same_code(other) for other in catalog.values()) != 1:
            raise PipelineError(
                "AMBIGUOUS_API_CODE",
                "Código API repetido entre variantes; no prueba la identidad ni permite asignar una fuente.",
            )
    return row


def document_for_item(db, item):
    documents = db.scalars(
        select(Document)
        .where(
            Document.body["associated_ecomm_id"].as_string() == item["ecomm_id"],
            Document.body["source"]["reference_url"].as_string() == item["url"],
        )
        .limit(2)
    ).all()
    if len(documents) > 1:
        raise PipelineError(
            "AMBIGUOUS_DOCUMENT",
            "Hay varios originales para esa URL y variante; elegir la evidencia manualmente.",
        )
    if not documents:
        return None
    doc = documents[0]
    if item.get("document_id") and doc.id != item["document_id"]:
        raise PipelineError(
            "DOCUMENT_CHANGED",
            "El original archivado no coincide con el documento del paso.",
        )
    return doc


def receipt_for_document(db, item, document_id, *, allow_current=False):
    check_identity(item, sources(db))
    doc = db.scalar(
        select(Document).where(Document.id == document_id).with_for_update()
    )
    if not doc or doc.body.get("associated_ecomm_id") != item["ecomm_id"]:
        raise PipelineError(
            "DOCUMENT_IDENTITY_MISMATCH",
            "El documento no pertenece al Ecomm ID exacto del lote.",
        )
    body = doc.body
    if (
        body.get("source", {}).get("reference_url") != item["url"]
        or digest(body) != doc.digest
    ):
        raise PipelineError(
            "DOCUMENT_INTEGRITY",
            "URL o integridad del original no coincide con la evidencia archivada.",
        )
    original = body.get("original") or {}
    try:
        raw = base64.b64decode(body.get("original_base64", ""), validate=True)
    except (ValueError, TypeError, binascii.Error):
        raise PipelineError(
            "ORIGINAL_INTEGRITY", "El original no contiene bytes verificables."
        ) from None
    source_hash = original.get("sha256")
    if (
        not raw
        or len(raw) > 4 * 1024 * 1024
        or not isinstance(source_hash, str)
        or not re.fullmatch(r"[a-f0-9]{64}", source_hash)
        or sha256(raw).hexdigest() != source_hash
        or original.get("size") != len(raw)
    ):
        raise PipelineError(
            "ORIGINAL_INTEGRITY", "SHA-256 o tamaño del original no verificable."
        )
    pinned = item.get("processing") or {}
    if pinned.get("document_sha256") and any(
        pinned.get(key) != value
        for key, value in (
            ("document_id", doc.id),
            ("document_sha256", source_hash),
            ("document_digest", doc.digest),
            ("document_version", doc.version),
            ("identity_digest", item["identity_digest"]),
        )
    ):
        raise PipelineError(
            "DOCUMENT_CHANGED",
            "La versión o procedencia del documento cambió; no se transfieren decisiones.",
        )
    if not pinned.get("document_sha256") and doc.version != 1 and not allow_current:
        raise PipelineError(
            "DOCUMENT_CHANGED",
            "El original cambió antes de fijar su primera versión en el lote; requiere revisión.",
        )
    if body.get("source", {}).get("review_state") not in {"PENDING", "REVIEWED"}:
        raise PipelineError(
            "SOURCE_REVOKED",
            "La procedencia fue rechazada o revocada; no se extraen hechos.",
        )
    request_count = (body.get("retrieval") or {}).get("request_count")
    if type(request_count) is not int or not 0 <= request_count <= 32:
        request_count = None
    previous_requests = pinned.get("http_requests_reported", 0)
    total_requests = previous_requests
    if pinned.get("request_measurement_pending"):
        total_requests = (
            previous_requests + request_count
            if type(previous_requests) is int and type(request_count) is int
            else None
        )
    return {
        **pinned,
        "schema_version": 1,
        "document_id": doc.id,
        "document_sha256": source_hash,
        "document_digest": doc.digest,
        "document_version": doc.version,
        "identity_digest": item["identity_digest"],
        "source_bytes": len(raw),
        # The existing fetch contract does not report failed HTTP requests.
        # Do not invent a measured count from the number of importer calls.
        "http_requests_reported": total_requests,
        "request_measurement_pending": False,
    }


def repin_reviewed_metadata(db, item, expected_version, expected_digest):
    """Explicit current-document CAS for a human provenance-only revision.

    The pinned historical body must be intact and content-identical. A source
    replacement, changed citation or identity requires new research instead.
    Research.extract still reextracts old-version facts as PENDING.
    """
    old = item.get("processing") or {}
    doc = db.scalar(
        select(Document).where(Document.id == item["document_id"]).with_for_update()
    )
    if not doc or doc.version != expected_version or doc.digest != expected_digest:
        raise PipelineError(
            "DOCUMENT_VERSION_CONFLICT",
            "El documento cambió desde la previsualización; recuperá su versión actual.",
        )
    if (
        old.get("document_version") == doc.version
        and old.get("document_digest") == doc.digest
    ):
        return deepcopy(item)
    historic = next(
        (
            entry.get("body")
            for entry in doc.history or []
            if entry.get("version") == old.get("document_version")
            and entry.get("hash") == old.get("document_digest")
            and digest(entry.get("body")) == old.get("document_digest")
        ),
        None,
    )
    fixed = (
        "original",
        "original_base64",
        "identity",
        "claims",
        "sections",
        "parser_blockers",
        "parse_status",
        "associated_ecomm_id",
        "origin_kind",
        "synthetic",
        "title",
        "kind",
        "provenance",
    )
    if (
        not historic
        or any(historic.get(key) != doc.body.get(key) for key in fixed)
        or doc.body.get("source", {}).get("reference_url") != item["url"]
        or historic.get("source", {}).get("reference_url") != item["url"]
        or doc.body.get("source", {}).get("review_state") != "REVIEWED"
        or doc.body.get("original", {}).get("sha256") != old.get("document_sha256")
    ):
        raise PipelineError(
            "DOCUMENT_CHANGED",
            "Cambió el contenido, identidad o procedencia del original; requiere una selección documental nueva.",
        )
    result = deepcopy(item)
    result["processing"] = {
        **old,
        "document_digest": doc.digest,
        "document_version": doc.version,
    }
    receipt_for_document(db, result, doc.id)
    return result


def extract_candidates(db, session, item):
    """Reuse the versioned Research extractor without changing source approval."""
    receipt = receipt_for_document(db, item, item["document_id"])
    doc = db.get(Document, item["document_id"])
    if doc.body.get("parse_status") != "TEXT_EXTRACTED" or doc.body.get(
        "parser_blockers"
    ):
        raise PipelineError(
            "DOCUMENT_NOT_EXTRACTABLE",
            "El original requiere revisión del lector antes de extraer candidatos.",
        )
    if not doc.body.get("claims"):
        raise PipelineError(
            "NO_CITED_CLAIMS",
            "No hay afirmaciones con citas extraíbles; hace falta documentación específica.",
        )
    # Research holds the existing evidence mutex. AtomicSession prevents its
    # serialize() from committing facts separately from the queue result.
    research = Research(AtomicSession(db), session)
    dossier = research.dossier(item["ecomm_id"])
    if research.identity_blockers(dossier, doc) or research.additional_blockers(
        dossier, doc
    ):
        raise PipelineError(
            "DOCUMENT_IDENTITY_MISMATCH",
            "Nombre, marca, presentación o cantidad documental requieren revisión de identidad.",
        )
    section_map = doc.body.get("sections") or {}
    for claim in doc.body["claims"]:
        quote, location, value = (
            claim.get("quote"),
            claim.get("location"),
            claim.get("value"),
        )
        if (
            not isinstance(quote, str)
            or not quote
            or not isinstance(location, str)
            or quote not in section_map.get(location, "")
            or not isinstance(value, str)
            or not re.search(
                r"(?<!\w)" + re.escape(value) + r"(?!\w)", quote, re.IGNORECASE
            )
        ):
            raise PipelineError(
                "INVALID_CITATION",
                "Una afirmación no coincide con la cita literal del original.",
            )
    report = research.extract(item["ecomm_id"], dossier.version, doc.id, doc.version)
    facts = [
        fact
        for fact in report["facts"]
        if fact["document_id"] == doc.id
        and fact["document_version"] == doc.version
        and fact["document_hash"] == doc.digest
    ]
    return {
        **receipt,
        "phase": "EXTRACTED",
        "candidate_count": sum(fact["state"] == "PENDING" for fact in facts),
        "candidate_ids": [fact["id"] for fact in facts if fact["state"] == "PENDING"],
        "dossier_version": report["version"],
        "error_code": None,
        "retryable": False,
    }


def safe_failure(error):
    """Persist only bounded public categories, never arbitrary provider errors."""
    if isinstance(error, PipelineError):
        return error
    if isinstance(error, (SourceFetchError, SourceTransportError)):
        failure = PipelineError(
            error.code,
            "El fabricante no pudo entregar el original mediante la consulta permitida.",
            retryable=error.retryable,
        )
        failure.request_count = error.request_count
        return failure
    if isinstance(error, (TimeoutError, ConnectionError, OSError)):
        return PipelineError(
            "SOURCE_UNAVAILABLE",
            "No se pudo consultar el fabricante; puede reintentarse explícitamente.",
            retryable=True,
        )
    message = str(error).casefold() if isinstance(error, ValueError) else ""
    for tokens, code, public, retryable in (
        (
            ("robots",),
            "SOURCE_ROBOTS_BLOCKED",
            "robots.txt no permitió verificar el acceso al original.",
            False,
        ),
        (
            ("dns", "privadas"),
            "SOURCE_DNS_BLOCKED",
            "Destino DNS no permitido por los controles de seguridad.",
            False,
        ),
        (
            ("hoy", "cuota"),
            "DAILY_QUOTA_BLOCKED",
            "La variante ya agotó la cuota diaria de incorporación documental.",
            False,
        ),
        (
            ("no disponible", "no se pudo consultar"),
            "SOURCE_UNAVAILABLE",
            "Consulta al fabricante no disponible; reintento manual permitido.",
            True,
        ),
        (
            ("cambió", "otra sesión"),
            "EVIDENCE_CONFLICT",
            "La identidad o evidencia cambió; revisar antes de continuar.",
            False,
        ),
    ):
        if any(token in message for token in tokens):
            return PipelineError(code, public, retryable=retryable)
    return PipelineError(
        "SOURCE_REVIEW_REQUIRED"
        if isinstance(error, ValueError)
        else "PIPELINE_FAILED",
        "No se pudo completar el paso; revisar la fuente y el estado registrado.",
    )
