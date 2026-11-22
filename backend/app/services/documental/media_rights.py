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
import re

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


def original_grant_is_current(doc, media_url, location, quote):
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
        or doc.digest != digest(body)
        or not stored.get("sha256")
        or not isinstance(stored.get("size"), int)
        or body.get("provenance") != "local://sha256/" + stored["sha256"]
        or not isinstance(location, str)
        or not isinstance(quote, str)
        or not isinstance(media_url, str)
        or not media_url.startswith("https://")
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
    try:
        raw = base64.b64decode(body["original_base64"], validate=True)
        original_text = raw.decode("utf-8-sig")
    except (KeyError, TypeError, ValueError, UnicodeError, binascii.Error):
        return False
    return (
        len(raw) == stored["size"]
        and hashlib.sha256(raw).hexdigest() == stored["sha256"]
        and quote in original_text
    )


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
    ):
        return False
    doc = research._document(record.get("document_id"))
    return bool(
        doc and doc.body.get("associated_ecomm_id") == item.ecomm_id
        and doc.version == record.get("document_version")
        and doc.digest == record.get("document_hash")
        and original_grant_is_current(
            doc, media_url, record.get("location"), record.get("quote")
        )
    )


def media_permission_report(research, item, resources):
    """Effective rights for exact saved assets; an old approval is not current.

    Uses the same check as channel preparation, without mutating a decision or
    loading any remote resource. The editor already bounds resources to thirty.
    """
    if not isinstance(resources, list) or len(resources) > 30:
        raise ValueError("La lista multimedia guardada supera el contrato del editor.")
    result = []
    for media in resources:
        record = latest_media_rights(item, media.get("kind"), media.get("url"))
        if not record:
            state = "NO_PERMISSION"
        elif record.get("decision") == "REVOKED":
            state = "REVOKED"
        elif media_grant_current(research, item, media):
            state = "APPROVED_CURRENT"
        else:
            state = "STALE"
        result.append({
            "kind": media.get("kind"),
            "url": media.get("url"),
            "source_url": media.get("source_url"),
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
        })
    return result


def review_media_rights(
    research, ident, expected_version, document_id, document_version,
    media_url, media_kind, source_url, decision, licence_basis,
    location, quote, reason,
):
    if len(reason.strip()) < 25:
        raise ValueError("Explicá el permiso y su alcance (mínimo 25 caracteres).")
    if media_kind not in ("IMAGE", "VIDEO"):
        raise ValueError("El recurso debe ser imagen o video.")
    if not media_url.startswith("https://") or not source_url.startswith("https://"):
        raise ValueError("El recurso y su fuente deben usar HTTPS.")
    item = research.dossier(ident)
    research.expect(item, expected_version)
    doc = research._document(document_id)
    research.validate_document(ident, doc)
    if doc is None or doc.version != document_version:
        raise ValueError("El documento del permiso cambió o no existe.")
    if decision == "APPROVED":
        if licence_basis not in ("OWNER_AUTHORIZATION", "DOCUMENTED_LICENSE"):
            raise ValueError("Indicá el tipo de autorización de uso.")
        if not original_grant_is_current(doc, media_url, location, quote):
            raise ValueError(
                "No hay permiso explícito para esta URL respaldado "
                "por texto literal en el documento original revisado."
            )
    elif decision == "REVOKED":
        current = latest_media_rights(item, media_kind, media_url)
        if not current or current["decision"] != "APPROVED":
            raise ValueError("No existe permiso vigente para revocar.")
        if current["document_id"] != document_id:
            raise ValueError("La revocación debe señalar el documento del permiso.")
    else:
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
    }
    from copy import deepcopy

    research.commit_change(item, deepcopy(item.facts), "MEDIA_RIGHTS_REVIEW", record)
    return research.serialize(item)
