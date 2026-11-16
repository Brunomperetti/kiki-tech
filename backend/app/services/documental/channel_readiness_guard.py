"""Strict opt-in evidence gate for channel-ready *pilot* products.

The editor's manual source verified flag is an operator assertion only.
It is insufficient on its own to attest the documentary source. This guard
requires one intact reviewed manufacturer original and reviewed, still-valid
name/presentation facts tied to that exact Ecomm ID and source URL.

No provider writes, no auto-approval, no DDL or background processing.
The feature stays OFF by default until the real-source acceptance gate.
"""
import base64
import binascii
import hashlib

from .research import Research
from .storage import digest


REQUIRED = frozenset({"product_name", "presentation"})


def require_primary_evidence(db, session, ecomm_id, fields):
    if session is None:
        raise ValueError("Validación documental exige una sesión autenticada.")
    # Reuse exactly the documentary mutex and current-source reconciliation:
    # no parallel editor save can race a revocation of the same evidence.
    research = Research(db, session)
    dossier = research.dossier(ecomm_id)
    candidates = [
        s for s in (fields.get("sources") or [])
        if s.get("verified") is True
        and s.get("kind") == "FABRICANTE"
        and s.get("url")
    ]
    if not candidates:
        raise ValueError(
            "Fuente primaria documental: la ficha necesita un fabricante "
            "revisado con URL antes de estar lista para canales."
        )
    if not fields.get("presentation"):
        raise ValueError("Falta presentación editorial documentada.")

    for source in candidates:
        for doc in research.documents(ecomm_id):
            body = doc.body or {}
            origin = body.get("original") or {}
            reference = body.get("source") or {}
            if (
                body.get("synthetic") is not False
                or body.get("associated_ecomm_id") != ecomm_id
                or body.get("origin_kind") != "FILE"
                or body.get("parse_status") != "TEXT_EXTRACTED"
                or body.get("parser_blockers")
                or reference.get("reference_url") != source["url"]
                or reference.get("review_state") != "REVIEWED"
                or not reference.get("reviewer")
                or len(str(reference.get("review_reason") or "").strip()) < 10
                or doc.digest != digest(body)
                or doc.version != body.get("version")
                or not origin.get("size")
                or not origin.get("sha256")
                or not body.get("original_base64")
                or body.get("provenance") != "local://sha256/" + origin["sha256"]
                or not isinstance(body.get("identity"), dict)
            ):
                continue
            try:
                original_bytes = base64.b64decode(
                    body["original_base64"], validate=True
                )
            except (TypeError, ValueError, binascii.Error):
                continue
            if (
                len(original_bytes) != origin["size"]
                or hashlib.sha256(original_bytes).hexdigest()
                != origin["sha256"]
                or body["identity"].get("presentation") != fields["presentation"]
            ):
                continue
            # A manually reviewed relationship resolves only name/size
            # differences; it never overrides contradictory EAN, pack or brand.
            if research.identity_blockers(dossier, doc):
                continue
            valid = {
                fact["field"]: fact["value"]
                for fact in dossier.facts
                if fact["document_id"] == doc.id
                and fact["state"] == "APPROVED"
                and fact.get("reviewer")
                and fact.get("verification_digest")
                and not research.blockers(dossier, fact)
            }
            if not REQUIRED.issubset(valid):
                continue
            name = valid["product_name"]
            if (
                valid["presentation"] != fields["presentation"]
                or fields.get("short_title") != name
                or fields.get("title") != name + " · " + fields["presentation"]
            ):
                continue
            # This proves only the existence of an intact primary source
            # supporting identity. Taxonomy, media rights and each additional
            # commercial claim require separate approval before publication.
            return {
                "ready": True,
                "document_id": doc.id,
                "document_version": doc.version,
                "document_sha256": origin["sha256"],
                "source_url": source["url"],
                "approved_identity_facts": sorted(REQUIRED),
                "external_writes_enabled": False,
            }
    raise ValueError(
        "Fuente primaria documental sin respaldo suficiente: exige archivo "
        "original íntegro, revisión vigente, conciliación de identidad y "
        "hechos aprobados de nombre y presentación para este SKU."
    )
