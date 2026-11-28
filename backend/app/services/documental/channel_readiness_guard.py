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
# Only canonical, deterministic copy derived from individually approved facts
# may be marked channel-ready in the single-source pilot. Drafts can still be
# edited freely and a separate editorial approval path can be added later.
COPY_FIELDS = (
    "brand", "manufacturer", "title", "short_title", "short_description",
    "description", "details", "presentation", "category", "subcategory",
    "seo_title", "seo_description", "seo_keywords",
)


def _commercial_coverage(research, item, fields, approved, *, facts=None, strict_stage4=False, applied_proposals=None, taxonomy=None):
    """Exact approved fields and explicit asset permissions, never inferred."""
    from .media_rights import media_grant_current
    from .proposals import Proposals, TEXT

    missing = []
    internal_pair = ((taxonomy or {}).get("record") or {}).get("target_pair") or {}
    reviewed_internal = bool(strict_stage4 and taxonomy and taxonomy.get("state") == "APPROVED" and taxonomy.get("catalog_bound") is True)
    for key in TAXONOMY_FIELDS:
        values = approved.get(key, [])
        supported = fields.get(key) == internal_pair.get(key) if reviewed_internal else values == [fields.get(key)]
        if not fields.get(key) or not supported:
            missing.append(key)

    # The editor's checksum validation only checks the format. It cannot
    # establish that an individual EAN belongs to this exact SKU. A candidate
    # from the Excel export is never enough to pass this gate.
    proposed_gtin = fields.get("proposed_gtin") or ""
    if proposed_gtin and approved.get("ean") != [proposed_gtin]:
        missing.append("proposed_gtin_unverified")

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

    # Text and SEO require the same evidence as technical attributes. A
    # commercially plausible paragraph or a checkbox does not verify a claim.
    # Use the very generator behind the reviewed-evidence proposal; this
    # excludes arbitrary health benefits, SEO synonyms and promotional copy.
    canonical_facts = facts if facts is not None else [
        {"id": f"reviewed-{key}", "field": key, "value": values[0], "unit": None}
        for key, values in approved.items()
        if len(values) == 1
    ]
    canonical, _missing = Proposals.generate_fields(canonical_facts)
    assessment = None
    if strict_stage4:
        from .completion import saved_field_coverage
        assessment = saved_field_coverage(research, item, fields, applied_proposals=applied_proposals, taxonomy=taxonomy)
    field_rows = {row["field"]: row for row in assessment["fields"]} if assessment else {}
    copy_errors = []
    for key in COPY_FIELDS:
        generated = canonical.get(key)
        expected = generated["value"] if generated else ""
        supported = (field_rows.get(key) or {}).get("state") == "APPROVED_BACKED" if assessment else fields.get(key, "") == expected
        # Empty optional fields do not acquire a fictitious citation, but do
        # not block a package merely because an unknown value was omitted.
        if fields.get(key, "") and not supported or not fields.get(key, "") and expected:
            copy_errors.append(key)
            missing.append("commercial_copy[" + key + "]")

    media = fields.get("media") or []
    media_approved = 0
    if not media:
        missing.append("media")
    strict_media = None
    if strict_stage4:
        from .media_rights import media_permission_report
        strict_media = media_permission_report(research, item, media)
    for index, resource in enumerate(media, 1):
        if media_grant_current(research, item, resource) and (not strict_stage4 or strict_media[index - 1].get("stage4_ready") is True):
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
        "commercial_copy_supported": not copy_errors,
        "commercial_copy_fields_checked": len(COPY_FIELDS),
        "commercial_copy_mismatches": copy_errors,
        "field_evidence": {
            key: (field_rows[key].get("citations") or [])
            for key in field_rows
            if field_rows[key].get("state") == "APPROVED_BACKED"
        } if assessment else {
            key: [{"fact_id": ident} for ident in value.get("evidence_ids", [])]
            for key, value in canonical.items()
            if fields.get(key) == value.get("value")
        },
        "field_lineage": {key: row["lineage"] for key, row in field_rows.items()
                          if row.get("state") == "APPROVED_BACKED" and row.get("lineage")},
        "media_rights_verified": bool(media) and media_approved == len(media),
        "media_rights_status": (
            "AUTORIZACIONES_DOCUMENTADAS_Y_VIGENTES"
            if media and media_approved == len(media)
            else "PENDIENTE_ACREDITAR_DERECHOS"
        ),
        "media_resources_reviewed": media_approved,
        "media_resources_total": len(media),
    }


def require_primary_evidence(db, session, ecomm_id, fields, *, research=None, strict_stage4=False, applied_proposals=None, taxonomy=None):
    if session is None:
        raise ValueError("Validación documental exige una sesión autenticada.")
    # Reuse exactly the documentary mutex and current-source reconciliation:
    # no parallel editor save can race a revocation of the same evidence.
    research = research if research is not None else Research(db, session)
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
                or (not strict_stage4 and fields.get("short_title") != name)
                or (not strict_stage4 and fields.get("title") != name + " · " + fields["presentation"])
            ):
                continue
            coverage_facts, coverage_approved = facts, approved
            if strict_stage4:
                # A complete fiche can cite several reviewed originals. Keep
                # the primary identity anchor above, then reuse *all* current
                # individual approvals instead of silently discarding labels
                # or technical documents outside that one original.
                coverage_facts = [fact for fact in dossier.facts
                                  if fact.get("state") == "APPROVED" and fact.get("reviewer")
                                  and fact.get("verification_digest")
                                  and not research.blockers(dossier, fact)]
                coverage_approved = {}
                for fact in coverage_facts:
                    value = fact["value"] + (" " + fact["unit"] if fact.get("unit") else "")
                    if value not in coverage_approved.setdefault(fact["field"], []):
                        coverage_approved[fact["field"]].append(value)
                if any(len(values) != 1 for values in coverage_approved.values()):
                    raise ValueError("Hay hechos aprobados contradictorios entre las fuentes; revisá las afirmaciones antes de preparar canales.")
            coverage = _commercial_coverage(research, dossier, fields, coverage_approved, facts=coverage_facts, strict_stage4=strict_stage4, applied_proposals=applied_proposals, taxonomy=taxonomy)
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
