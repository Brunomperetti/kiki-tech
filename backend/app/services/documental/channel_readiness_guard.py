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
TAXONOMY_FIELDS = ("category", "subcategory")


def _commercial_coverage(research, item, fields, approved):
    """Exact approved fields and explicit asset permissions, never inferred."""
    from .media_rights import media_grant_current
    from .proposals import TEXT

    missing = []
    for key in TAXONOMY_FIELDS:
        values = approved.get(key, [])
        if not fields.get(key) or values != [fields[key]]:
            missing.append(key)

    # A label typed by the operator is not provenance. Every display attribute
    # must correspond exactly to one current, approved, source-quoted fact.
    required_attributes = []
    for fact_key, label in TEXT.items():
        for fact in approved.get(fact_key, []):
            candidate = {
                "name": label,
                "value": fact,
            }
            required_attributes.append(candidate)
    allowed = {(row["name"], row["value"]) for row in required_attributes}
    for index, row in enumerate(fields.get("attributes") or [], 1):
        if (row.get("name"), row.get("value")) not in allowed:
            missing.append(f"attributes[{index}]")
    if not fields.get("attributes"):
        missing.append("attributes")

    media = fields.get("media") or []
    media_approved = 0
    if not media:
        missing.append("media")
    for index, resource in enumerate(media, 1):
        if media_grant_current(research, item, resource):
            media_approved += 1
        else:
            missing.append(f"media_rights[{index}]")
    return {
        "verified": not missing,
        "missing": missing,
        "attributes_supported": len(fields.get("attributes") or []) - sum(
            code.startswith("attributes[") for code in missing
        ),
        "taxonomy_supported": all(key not in missing for key in TAXONOMY_FIELDS),
        "media_rights_verified": bool(media) and media_approved == len(media),
        "media_rights_status": (
            "AUTORIZACIONES_DOCUMENTADAS_Y_VIGENTES"
            if media and media_approved == len(media)
            else "PENDIENTE_ACREDITAR_DERECHOS"
        ),
        "media_resources_reviewed": media_approved,
        "media_resources_total": len(media),
    }


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
            facts = [
                fact for fact in dossier.facts
                if fact["document_id"] == doc.id
                and fact["state"] == "APPROVED"
                and fact.get("reviewer")
                and fact.get("verification_digest")
                and not research.blockers(dossier, fact)
            ]
            approved = {}
            for fact in facts:
                value = fact["value"] + (
                    " " + fact["unit"] if fact.get("unit") else ""
                )
                approved.setdefault(fact["field"], []).append(value)
            # Conflicting duplicate facts never silently select an arbitrary
            # reviewed value or pass a taxonomy label by coincidence.
            if any(len(values) != 1 for values in approved.values()):
                continue
            if not REQUIRED.issubset(approved):
                continue
            valid = {key: values[0] for key, values in approved.items()}
            name = valid["product_name"]
            if (
                valid["presentation"] != fields["presentation"]
                or fields.get("short_title") != name
                or fields.get("title") != name + " · " + fields["presentation"]
            ):
                continue
            coverage = _commercial_coverage(research, dossier, fields, approved)
            if not coverage["verified"]:
                raise ValueError(
                    "Faltan datos respaldados o permisos multimedia vigentes "
                    "para esta ficha: " + ", ".join(coverage["missing"])
                )
            # A media URL alone never constitutes permission. Every asset
            # requires an original grant with exact quoted URL and human review.
            return {
                "ready": True,
                "commercial_coverage": coverage,
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
