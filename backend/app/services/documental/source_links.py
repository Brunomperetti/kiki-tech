"""Read-only suggestions for reusing already reviewed documentary originals.

The commercial editor remains the only writer. Suggestions never mark a
source as verified: the operator must confirm the exact source before saving.
No network, media-license, barcode or channel-publication inference.
"""
from ipaddress import ip_address
from urllib.parse import urlsplit

from .local_documents import valid_url


def _safe_reference(value):
    if not isinstance(value, str) or not value or len(value) > 1000:
        return None
    try:
        valid_url(value)
        parsed = urlsplit(value)
        if parsed.hostname in ("localhost", "127.0.0.1", "::1"):
            return None
        try:
            if not ip_address(parsed.hostname).is_global:
                return None
        except ValueError:
            pass  # A conventional DNS hostname: no network lookup here.
        return parsed.hostname
    except ValueError:
        return None


def suggest_reviewed_sources(research, ecomm_id):
    """Offer official-source *candidates*, not automatic verified attestations.

    Identity, per-document provenance and at least one fact must already have
    received separate operator review. The fact must still be current and
    unblocked against the exact Ecomm ID and document version.
    """
    dossier = research.dossier(ecomm_id)
    candidates = {}
    for doc in research.documents(ecomm_id):
        body = doc.body
        if body.get("synthetic") or body.get("associated_ecomm_id") != ecomm_id:
            continue
        source = body.get("source") or {}
        url = source.get("reference_url", "")
        host = _safe_reference(url)
        original = body.get("original") or {}
        sha = original.get("sha256", "")
        if (
            not host
            or source.get("review_state") != "REVIEWED"
            or not research.equivalence_current(dossier, doc)
            or body.get("parse_status") != "TEXT_EXTRACTED"
            or not isinstance(sha, str)
            or len(sha) != 64
            or any(c not in "0123456789abcdef" for c in sha.lower())
            or not isinstance(original.get("size"), int)
            or original["size"] < 1
        ):
            continue
        facts = [
            f for f in dossier.facts
            if f.get("ecomm_id") == ecomm_id
            and f.get("document_id") == doc.id
            and f.get("state") == "APPROVED"
            and not research.blockers(dossier, f)
        ]
        if not facts:
            continue
        # Never invent FABRICANTE or an operator attestation. That choice
        # must be made by a person even for a TLS-retrieved web page.
        note = (
            f"Original KIKI {doc.id} v{doc.version}; SHA-256 {sha}; "
            f"{len(facts)} hechos vigentes. Verificar titularidad y presentación."
        )
        record = {
            "kind": "OTRO",
            "name": ("Documento revisado · " + host)[:180],
            "url": url,
            "note": note[:500],
            "verified": False,
        }
        key = url.rstrip("/").casefold()
        previous = candidates.get(key)
        if not previous or doc.version > previous["document_version"]:
            candidates[key] = {
                "source": record,
                "document_id": doc.id,
                "document_version": doc.version,
                "sha256": sha,
                "approved_fact_count": len(facts),
                "requires_operator_confirmation": True,
            }
    return {
        "ecomm_id": ecomm_id,
        "suggestions": list(candidates.values())[:10],
        "internal_only": True,
        "external_writes_enabled": False,
        "automatically_verified": False,
    }
