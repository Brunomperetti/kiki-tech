"""Auditable explicit operator review of commercial media usage rights.

A product image URL is NOT a licence. Approval requires a reviewed local
source document with verbatim permission for the exact asset URL. This does
not independently establish legal ownership; it records the operator's basis.
Every decision is tied to the exact asset, source, document digest, version
and Ecomm identity and is reversible. No network or provider writes.
"""
import base64
import binascii
import hashlib
import ipaddress
import re
from datetime import datetime, timezone
from types import SimpleNamespace
from urllib.parse import urlsplit

from .storage import digest

GRANT_TERMS = re.compile(
    r"\b(?:autoriza(?:n|mos|do|da|ción)?|permite(?:n)?\s+el\s+uso|"
    r"licencia\s+(?:de\s+)?uso|permiso\s+(?:de\s+)?uso)\b",
    flags=re.IGNORECASE,
)
NO_GRANT = re.compile(
    r"\b(?:no\s+(?:se\s+)?autoriza|no\s+(?:se\s+)?permite|"
    r"prohibid[oa]|sin\s+licencia|no\s+cuenta\s+con\s+autorización)\b",
    flags=re.IGNORECASE,
)
COMMERCIAL_SCOPE = re.compile(r"\bcomercial(?:es)?\b", flags=re.IGNORECASE)


def safe_media_url(value):
    """A safe navigation reference, never a server-side fetch authorization.

    No DNS is performed. A hostname can change address; explicitly opening an
    approved URL remains a browser action, not a verified destination probe.
    """
    if not isinstance(value, str) or not 9 <= len(value) <= 1000 or any(ord(c) < 33 or ord(c) == 127 for c in value) or "\\" in value:
        return False
    try:
        parsed = urlsplit(value)
        host = parsed.hostname or ""
        if parsed.scheme != "https" or not host or parsed.username or parsed.password or parsed.port not in (None, 443):
            return False
        if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
            return False
        try:
            return ipaddress.ip_address(host).is_global
        except ValueError:
            if all(re.fullmatch(r"(?:0[xX][0-9a-fA-F]+|[0-9]+)", label) for label in host.split(".")):
                return False
            return bool(re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?", host)) and "." in host and ".." not in host
    except (ValueError, TypeError):
        return False


def _instant(value):
    if not isinstance(value, str):
        return None
    try:
        result = datetime.fromisoformat(value)
        return result.astimezone(timezone.utc) if result.tzinfo is not None else None
    except (ValueError, OverflowError):
        return None


def _quote_in_original(doc, raw, location, quote, parser=None):
    """PDF text must come from the same bounded isolated reader, not UTF-8.

    Cache one verified parsing result per loaded document/version. Changes to
    original, body, hash or version invalidate the key before any reuse.
    The bytes were checked before this helper; no remote resource is fetched.
    """
    stored = doc.body["original"]
    mime = stored.get("content_type")
    if mime != "application/pdf":
        try:
            if quote in raw.decode("utf-8-sig"):
                return True
        except UnicodeError:
            return False
        if mime != "text/html":
            return False
    elif not raw.startswith(b"%PDF-"):
        return False
    key = (doc.version, doc.digest, stored["sha256"], parser)
    cached = getattr(doc, "_media_permission_parse", None)
    if not cached or cached[0] != key:
        if parser is None:
            from .local_documents import parse_local
            parser = parse_local
        try:
            parsed = parser(SimpleNamespace(
                kind="FILE", filename=stored.get("filename", ""),
                content_type=mime, content_base64=doc.body["original_base64"],
                web_snapshot=mime == "text/html",
            ))
        except (ValueError, OSError):
            return False
        if not isinstance(parsed, dict) or parsed.get("parse_status") != "TEXT_EXTRACTED" or parsed.get("parser_blockers"):
            return False
        sections = parsed.get("sections")
        if not isinstance(sections, dict):
            return False
        # Unmapped attributes are operation-local cache, not JSON persistence.
        doc._media_permission_parse = (key, sections)
    else:
        sections = cached[1]
    return isinstance(sections.get(location), str) and quote in sections[location]


def _reference_current(doc, media_url, location, quote, *, projected=False):
    body = doc.body or {}
    stored = body.get("original") or {}
    source = body.get("source") or {}
    if (
        body.get("synthetic") is not False
        or body.get("origin_kind") != "FILE"
        or body.get("parse_status") != "TEXT_EXTRACTED"
        or body.get("parser_blockers")
        or source.get("review_state") != "REVIEWED"
        or not source.get("reviewer")
        or len(str(source.get("review_reason") or "")) < 10
        or doc.version != body.get("version")
        or (not projected and doc.digest != digest(body))
        or not stored.get("sha256")
        or not isinstance(stored.get("size"), int)
        or stored["size"] <= 0
        or body.get("provenance") != "local://sha256/" + stored["sha256"]
        or not isinstance(location, str)
        or not isinstance(quote, str)
        or not isinstance(media_url, str)
        or not safe_media_url(media_url)
        or len(media_url) > 1000
        or len(quote) > 1500
        or len(quote) < 30
        or media_url not in quote
        or not GRANT_TERMS.search(quote)
        or not COMMERCIAL_SCOPE.search(quote)
        or NO_GRANT.search(quote)
        or quote not in str((body.get("sections") or {}).get(location, ""))
    ):
        return False
    return True


def _original_bytes_valid(doc):
    body, stored = doc.body or {}, (doc.body or {}).get("original") or {}
    encoded = body.get("original_base64")
    # This is only an upper allocation bound. The existing reader still
    # enforces each format's smaller limit and the pinned large-PDF profile.
    from document_reader.hileret_brochure import ENCODED_SIZE
    if not isinstance(encoded, str) or len(encoded) > ENCODED_SIZE:
        return None
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (KeyError, TypeError, ValueError, binascii.Error):
        return None
    if len(raw) != stored.get("size") or hashlib.sha256(raw).hexdigest() != stored.get("sha256"):
        return None
    from document_reader.parser import safe_filename, MIMES, MAX_BYTES, MAX_SAVED_HTML_BYTES
    try:
        extension = safe_filename(stored.get("filename", ""))
    except ValueError:
        return None
    if MIMES[extension] != stored.get("content_type"):
        return None
    if extension == ".pdf" and len(raw) > MAX_BYTES:
        from document_reader.hileret_brochure import matches
        if not matches(raw):
            return None
    elif len(raw) > (MAX_SAVED_HTML_BYTES if extension == ".html" else MAX_BYTES):
        return None
    return raw


def original_grant_is_current(doc, media_url, location, quote, *, parser=None):
    if not _reference_current(doc, media_url, location, quote):
        return False
    raw = _original_bytes_valid(doc)
    return raw is not None and _quote_in_original(doc, raw, location, quote, parser)


def _verified_receipt_current(doc, record, media_url):
    """A pinned approval receipt supports bounded read-only projections.

    The approval itself always checked original bytes and the literal quote;
    read paths reuse it only for the same document version/digest/hash/quote.
    ORM documents still verify their complete stored bytes. Bulk Context's
    intentional non-ORM projection omits only original_base64, not provenance.
    """
    if record.get("original_verification_profile") != "ORIGINAL_BYTES_AND_LOCATION_V1":
        return original_grant_is_current(doc, media_url, record.get("location"), record.get("quote"))
    body, stored = doc.body or {}, (doc.body or {}).get("original") or {}
    quote = record.get("quote")
    projected = "original_base64" not in body and not hasattr(doc, "_sa_instance_state")
    if (
        record.get("original_sha256") != stored.get("sha256")
        or not isinstance(quote, str)
        or record.get("quote_sha256") != hashlib.sha256(quote.encode("utf-8")).hexdigest()
        or not _reference_current(doc, media_url, record.get("location"), quote, projected=projected)
    ):
        return False
    return projected or _original_bytes_valid(doc) is not None


def _identity_compatible(research, item, doc):
    if doc is None or not isinstance(doc.body.get("identity"), dict):
        return False
    if item.identity.get("parent_is_combo") is True and item.identity.get("is_combo") is not True:
        return False
    return not research.identity_blockers(item, doc) and not research.additional_blockers(item, doc)


def _resource_metadata(research, item, media):
    edit = research.edit_record(item.ecomm_id)
    fields = (edit.fields or {}) if edit else {}
    candidates = [resource for resource in fields.get("media", []) if resource.get("kind") == media.get("kind") and resource.get("url") == media.get("url")]
    return edit, fields, candidates


def latest_media_rights(item, kind, media_url):
    for event in reversed(item.history or []):
        if event.get("action") != "MEDIA_RIGHTS_REVIEW":
            continue
        detail = event.get("detail") or {}
        if detail.get("kind") == kind and detail.get("media_url") == media_url:
            return detail
    return None


def media_grant_current(research, item, media):
    kind = media.get("kind")
    media_url = media.get("url")
    record = latest_media_rights(item, kind, media_url)
    if not record or record.get("decision") != "APPROVED":
        return False
    if (
        record.get("ecomm_id") != item.ecomm_id
        or record.get("identity_digest") != item.identity_digest
        or record.get("source_url") != media.get("source_url")
        or record.get("licence_basis") not in ("OWNER_AUTHORIZATION", "DOCUMENTED_LICENSE")
        or not record.get("reviewer")
        or not safe_media_url(media_url)
        or not safe_media_url(media.get("source_url"))
    ):
        return False
    if record.get("valid_until"):
        expires = _instant(record["valid_until"])
        if expires is None or datetime.now(timezone.utc) >= expires:
            return False
    if record.get("resource_binding_schema") == 1:
        _edit, fields, matches = _resource_metadata(research, item, media)
        if (
            len(matches) != 1 or matches[0].get("source_url") != record.get("source_url")
            or matches[0].get("alt") != record.get("alt_text")
            or media.get("alt") != record.get("alt_text")
            or fields.get("presentation") != record.get("presentation")
            or item.identity.get("presentation") != record.get("source_presentation")
        ):
            return False
    doc = research._document(record.get("document_id"))
    return bool(
        doc and doc.body.get("associated_ecomm_id") == item.ecomm_id
        and doc.version == record.get("document_version")
        and doc.digest == record.get("document_hash")
        and (doc.body.get("source") or {}).get("reference_url") == record.get("source_url")
        and _identity_compatible(research, item, doc)
        and _verified_receipt_current(doc, record, media_url)
    )


def media_permission_report(research, item, resources):
    """Effective rights for exact saved assets; an old approval is not current.

    Uses the same check as channel preparation, without mutating a decision or
    loading any remote resource. The editor already bounds resources to thirty.
    """
    if not isinstance(resources, list) or len(resources) > 30:
        raise ValueError("La lista multimedia guardada supera el contrato del editor.")
    if any(not isinstance(media, dict) or media.get("kind") not in ("IMAGE", "VIDEO") or not isinstance(media.get("url"), str) or (media.get("source_url") is not None and not isinstance(media["source_url"], str)) for media in resources):
        raise ValueError("Un recurso multimedia no respeta el contrato del editor.")
    result = []
    for media in resources:
        record = latest_media_rights(item, media.get("kind"), media.get("url"))
        if not record:
            state = "NO_PERMISSION"
        elif record.get("decision") == "REVOKED":
            state = "REVOKED"
        elif record.get("decision") == "REJECTED":
            state = "REJECTED"
        elif media_grant_current(research, item, media):
            state = "APPROVED_CURRENT"
        else:
            state = "STALE"
        metadata_complete = bool(
            record and record.get("resource_binding_schema") == 1
            and isinstance(record.get("alt_text"), str) and len(record["alt_text"].strip()) >= 3
            and record.get("presentation") and record.get("source_presentation")
            and _instant(record.get("reviewed_at"))
            and re.fullmatch(r"[a-f0-9]{64}", str(record.get("original_sha256") or ""))
        )
        blockers = []
        if state != "APPROVED_CURRENT":
            blockers.append({"NO_PERMISSION": "Falta permiso explícito revisado; una URL pública no autoriza su uso.", "REJECTED": "El operador rechazó este recurso.", "REVOKED": "El permiso fue revocado.", "STALE": "Cambió el recurso, su identidad o la evidencia; se debe revalidar."}[state])
        if not metadata_complete:
            blockers.append("Falta revisar y vincular texto alternativo, presentación, fecha o hash del original.")
        if record and record.get("valid_until") and (_instant(record["valid_until"]) is None or _instant(record["valid_until"]) <= datetime.now(timezone.utc)):
            blockers.append("El permiso venció o su fecha no es válida.")
        result.append({
            "kind": media.get("kind"),
            "url": media.get("url"),
            "source_url": media.get("source_url") or "",
            "state": state,
            "current": state == "APPROVED_CURRENT",
            "ecomm_id": item.ecomm_id,
            "document_id": (record or {}).get("document_id"),
            "document_version": (record or {}).get("document_version"),
            "document_hash": (record or {}).get("document_hash"),
            "reviewer": (record or {}).get("reviewer"),
            "licence_basis": (record or {}).get("licence_basis"),
            "location": (record or {}).get("location"),
            "quote": (record or {}).get("quote"),
            "alt": media.get("alt", ""),
            "reviewed_alt": (record or {}).get("alt_text"),
            "presentation": (record or {}).get("presentation"),
            "source_presentation": (record or {}).get("source_presentation"),
            "reviewed_at": (record or {}).get("reviewed_at"),
            "valid_until": (record or {}).get("valid_until"),
            "original_sha256": (record or {}).get("original_sha256"),
            "metadata_complete": metadata_complete,
            "stage4_ready": state == "APPROVED_CURRENT" and metadata_complete,
            "preview_allowed": state == "APPROVED_CURRENT" and metadata_complete and safe_media_url(media.get("url")),
            "blockers": blockers,
        })
    return result


def review_media_rights(
    research, ident, expected_version, document_id, document_version,
    media_url, media_kind, source_url, decision, licence_basis,
    location, quote, reason,
    *, alt_text=None, presentation=None, valid_until=None, expected_workspace_version=None,
):
    if len(reason.strip()) < 25:
        raise ValueError("Explicá el permiso y su alcance (mínimo 25 caracteres).")
    if media_kind not in ("IMAGE", "VIDEO"):
        raise ValueError("El recurso debe ser imagen o video.")
    if not safe_media_url(media_url) or not safe_media_url(source_url):
        raise ValueError("El recurso y su fuente requieren URLs HTTPS públicas sin credenciales ni destinos privados.")
    item = research.dossier(ident)
    research.expect(item, expected_version)
    doc = research._document(document_id)
    research.validate_document(ident, doc)
    if doc is None or doc.version != document_version:
        raise ValueError("El documento del permiso cambió o no existe.")
    edit, fields, matches = _resource_metadata(research, item, {"kind": media_kind, "url": media_url})
    if expected_workspace_version is not None and expected_workspace_version != (edit.version if edit else 0):
        raise ValueError("La ficha cambió en otra sesión; recargá antes de revisar multimedia.")
    binding = alt_text is not None or presentation is not None
    if binding:
        if not isinstance(alt_text, str) or not 3 <= len(alt_text.strip()) <= 180 or not isinstance(presentation, str) or not 1 <= len(presentation.strip()) <= 750:
            raise ValueError("Indicá texto alternativo y presentación exacta para revisar el recurso.")
        if decision == "APPROVED" and (
            len(matches) != 1 or matches[0].get("source_url") != source_url
            or matches[0].get("alt") != alt_text or fields.get("presentation") != presentation
        ):
            raise ValueError("El recurso, su texto alternativo o presentación no coinciden con la ficha guardada.")
    if isinstance(valid_until, datetime):
        valid_until = valid_until.isoformat()
    if valid_until is not None:
        deadline = _instant(valid_until)
        if deadline is None or (decision == "APPROVED" and deadline <= datetime.now(timezone.utc)):
            raise ValueError("El vencimiento del permiso requiere una fecha futura con zona horaria.")
    if decision == "APPROVED":
        if licence_basis not in ("OWNER_AUTHORIZATION", "DOCUMENTED_LICENSE"):
            raise ValueError("Indicá el tipo de autorización de uso.")
        if not original_grant_is_current(doc, media_url, location, quote):
            raise ValueError(
                "No hay permiso explícito para esta URL respaldado "
                "por texto literal en el documento original revisado."
            )
        if (doc.body.get("source") or {}).get("reference_url") != source_url or not _identity_compatible(research, item, doc):
            raise ValueError("El permiso no corresponde a la fuente, identidad o presentación exacta de esta variante.")
    elif decision == "REVOKED":
        current = latest_media_rights(item, media_kind, media_url)
        if not current or current["decision"] != "APPROVED":
            raise ValueError("No existe permiso vigente para revocar.")
        if current["document_id"] != document_id:
            raise ValueError("La revocación debe señalar el documento del permiso.")
    elif decision != "REJECTED":
        raise ValueError("Decisión de uso multimedia no permitida.")
    record = {
        "decision": decision,
        "ecomm_id": ident,
        "kind": media_kind,
        "media_url": media_url,
        "source_url": source_url,
        "document_id": doc.id,
        "document_version": doc.version,
        "document_hash": doc.digest,
        "identity_digest": item.identity_digest,
        "licence_basis": licence_basis,
        "location": location,
        "quote": quote,
        "reason": reason.strip(),
        "reviewer": research.actor,
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "valid_until": valid_until,
        "original_sha256": (doc.body.get("original") or {}).get("sha256"),
        "resource_binding_schema": 1 if binding else 0,
        "alt_text": alt_text,
        "presentation": presentation,
        "source_presentation": item.identity.get("presentation"),
        "workspace_version": edit.version if edit else 0,
        "original_verification_profile": "ORIGINAL_BYTES_AND_LOCATION_V1" if decision == "APPROVED" else None,
        "quote_sha256": hashlib.sha256(quote.encode("utf-8")).hexdigest() if decision == "APPROVED" else None,
    }
    from copy import deepcopy

    research.commit_change(item, deepcopy(item.facts), "MEDIA_RIGHTS_REVIEW", record)
    return research.serialize(item)


def media_review_registry(research, ident, fields):
    """Registry over the existing editor/history; no new storage or downloads."""
    item = research.dossier(ident)
    edit = research.edit_record(ident)
    resources = fields.get("media") or []
    documents, used = [], 0
    for doc in research.documents(ident):
        if len(documents) >= 10:
            raise ValueError("Hay más documentos que el límite de revisión multimedia.")
        body, sections = doc.body or {}, []
        for location, text in (body.get("sections") or {}).items():
            if not isinstance(text, str) or not isinstance(location, str):
                continue
            if len(sections) >= 100 or used >= 256 * 1024:
                break
            excerpt = text[:1500]
            if used + len(excerpt.encode("utf-8")) > 256 * 1024:
                break
            used += len(excerpt.encode("utf-8"))
            sections.append({"location": location, "text": excerpt, "truncated": len(text) > len(excerpt)})
        source, original = body.get("source") or {}, body.get("original") or {}
        documents.append({
            "id": doc.id, "version": doc.version, "digest": doc.digest,
            "sha256": original.get("sha256"), "title": body.get("title"),
            "source_url": source.get("reference_url"), "review_state": source.get("review_state"),
            "source_reviewed_at": source.get("reviewed_at"),
            "declared_consulted_at": source.get("declared_consulted_at"),
            "identity_compatible": _identity_compatible(research, item, doc),
            "sections": sections, "sections_truncated": len(sections) < len(body.get("sections") or {}),
        })
    return {
        "mode": "MEDIA_REVIEW_REGISTRY", "ecomm_id": ident,
        "dossier_version": item.version, "workspace_version": edit.version if edit else 0,
        "presentation": fields.get("presentation") or "",
        "entries": media_permission_report(research, item, resources),
        "documents": documents, "external_writes_enabled": False,
        "remote_resources_loaded": 0,
    }
