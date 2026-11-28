"""Explain every existing editor field without equating presence with evidence.

Pure projection of the existing versioned proposal, human decisions and current
facts. It does not generate extra commercial claims or certify channel readiness.
"""

from collections import Counter

from app.services.ecomm_api_product_workspace_service import FIELDS

MAX_APPLIED_RECORDS = 100
MAX_LINEAGE_BYTES = 8 * 1024 * 1024
SAVED_STATES = ("APPROVED_BACKED", "FILLED_UNBACKED", "BLOCKED", "PENDING_REVIEW")

MANUAL = {
    "media": "MANUAL_RESOURCE_REVIEW_REQUIRED",
    "sources": "MANUAL_SOURCE_REVIEW_REQUIRED",
    "proposed_gtin": "API_CODE_REVIEW_REQUIRED",
    "note": "OPERATOR_NOTE",
}


def proposal_completion(
    proposed, saved, decisions, authorized, *, current, applied=False
):
    allowed = {fact["id"] for fact in authorized}
    rows = []
    for field in FIELDS:
        suggestion = proposed.get(field)
        evidence_ids = list(dict.fromkeys((suggestion or {}).get("evidence_ids", [])))
        supported = bool(evidence_ids) and set(evidence_ids).issubset(allowed)
        if suggestion:
            if applied:
                decision = decisions.get(field) or {}
                state = (
                    "SAVED_IN_INTERNAL_DRAFT"
                    if decision.get("decision") == "ACCEPTED"
                    and saved.get(field) == decision.get("value")
                    else "REJECTED"
                    if decision.get("decision") == "REJECTED"
                    else "PROPOSED_NOT_APPLIED"
                )
            elif not current or not supported:
                state = "STALE"
            else:
                state = {
                    "ACCEPTED": "ACCEPTED_FOR_INTERNAL_DRAFT",
                    "REJECTED": "REJECTED",
                }.get(
                    (decisions.get(field) or {}).get("decision"),
                    "PROPOSED_REVIEW_REQUIRED",
                )
        elif saved.get(field):
            state = "EXISTING_CONTENT_UNVERIFIED"
        else:
            state = MANUAL.get(field, "NEEDS_APPROVED_EVIDENCE")
        rows.append(
            {
                "field": field,
                "state": state,
                "proposed": suggestion is not None,
                "saved_content_present": bool(saved.get(field)),
                "current_evidence_supported": current and supported,
                "evidence_ids": evidence_ids,
                "human_review_required": state not in {"REJECTED", "OPERATOR_NOTE"},
            }
        )
    return {
        "schema_version": "kiki-editor-completion-v1",
        "total_fields": len(FIELDS),
        "states": dict(Counter(row["state"] for row in rows)),
        "fields": rows,
        "commercial_completion_certified": False,
        "channel_ready": False,
        "policy": "Cobertura de campos, no aprobación de producto. Texto guardado no acredita fuente; medios, códigos y taxonomía conservan sus revisiones independientes.",
    }


def _record_value(record, key, default=None):
    return (
        record.get(key, default)
        if isinstance(record, dict)
        else getattr(record, key, default)
    )


def _applied_records(research, ident):
    """Bound history before ORM materialization; never invoke a provider."""
    from sqlalchemy import Text, cast, func, select
    from app.database.models import KikiAiEditorialDraft
    from .evidence_ai import MODEL as AI_MODEL
    from .proposals import MODEL

    model = KikiAiEditorialDraft
    filters = (
        model.product_key == "ECOMM_DOCUMENTAL:" + ident,
        model.review_status == "APPLIED",
        model.model.in_((MODEL, AI_MODEL)),
    )
    length = func.octet_length
    multiplier = 1
    if research.db.get_bind().dialect.name == "sqlite":
        length, multiplier = func.length, 4
    projected = (
        select(
            (
                length(cast(model.history, Text))
                + length(cast(model.source_facts, Text))
            ).label("bytes")
        )
        .where(*filters)
        .order_by(model.id.desc())
        .limit(MAX_APPLIED_RECORDS)
        .subquery()
    )
    total = research.db.scalar(select(func.coalesce(func.sum(projected.c.bytes), 0)))
    if total * multiplier > MAX_LINEAGE_BYTES:
        raise ValueError(
            "El historial de propuestas supera el presupuesto; revisar individualmente."
        )
    return list(
        research.db.scalars(
            select(model)
            .where(*filters)
            .order_by(model.id.desc())
            .limit(MAX_APPLIED_RECORDS)
        )
    )


def _reviewed_values(research, item, fields, approved, records):
    """Validate applied field lineage independently of its obsolete base version.

    Applying a draft advances the editor version. That is not evidence drift.
    Identity, individual cited fact versions, decisions and exact saved values
    remain mandatory, so a later unrelated editor save cannot invent backing.
    """
    from .evidence_ai import COPY_FIELDS, EVENT as AI_EVENT, MODEL as AI_MODEL, validate
    from .proposals import EVENT, MODEL, Proposals
    from .research import fact_digest
    from .seo_validation import matches_documented_copy

    authorized = {fact["id"]: fact for fact in approved}
    result = {}
    records = sorted(
        records, key=lambda record: _record_value(record, "id", 0), reverse=True
    )
    for record in records[:MAX_APPLIED_RECORDS]:
        history = _record_value(record, "history", []) or []
        model = _record_value(record, "model")
        if (
            model not in {MODEL, AI_MODEL}
            or _record_value(record, "review_status") != "APPLIED"
            or _record_value(record, "product_key")
            != "ECOMM_DOCUMENTAL:" + item.ecomm_id
            or not history
            or history[0].get("event") != (AI_EVENT if model == AI_MODEL else EVENT)
        ):
            continue
        meta = history[0].get("proposal") or {}
        if meta.get("identity_hash") != item.identity_digest:
            continue
        old_facts = {
            fact["id"]: fact for fact in _record_value(record, "source_facts", [])
        }
        for key, decision in (meta.get("decisions") or {}).items():
            if (
                key in result
                or key not in fields
                or not isinstance(decision, dict)
                or decision.get("decision") != "ACCEPTED"
                or fields[key] != decision.get("value")
            ):
                continue
            reviewed = next(
                (
                    event
                    for event in reversed(history)
                    if event.get("event") == "FIELD_REVIEW"
                    and event.get("actor")
                    and (event.get("decisions") or {}).get(key) == decision
                ),
                None,
            )
            applied = next(
                (
                    event
                    for event in reversed(history)
                    if event.get("event") == "APPLIED_VIA_WORKSPACE"
                    and event.get("actor")
                    and key in (event.get("selected_fields") or [])
                ),
                None,
            )
            proposal = (meta.get("fields") or {}).get(key)
            ids = (proposal or {}).get("evidence_ids") or []
            if (
                not reviewed
                or not applied
                or not proposal
                or not ids
                or any(
                    ident not in authorized
                    or ident not in old_facts
                    or authorized[ident].get("version")
                    != old_facts[ident].get("version")
                    or fact_digest(authorized[ident]) != fact_digest(old_facts[ident])
                    for ident in ids
                )
            ):
                continue
            cited = [authorized[ident] for ident in ids]
            try:
                Proposals.validate_edit(key, fields[key], proposal)
                if (
                    model == AI_MODEL
                    and key in COPY_FIELDS
                    and key in meta.get("ai_fields", [])
                ):
                    validate({key: {"text": fields[key], "evidence_ids": ids}}, cited)
                else:
                    generated, _ = Proposals.generate_fields(cited)
                    if not matches_documented_copy(
                        key, fields[key], generated.get(key)
                    ):
                        continue
            except (ValueError, KeyError, TypeError):
                continue
            result[key] = {
                "evidence_ids": list(dict.fromkeys(ids)),
                "lineage": {
                    "draft_id": _record_value(record, "id"),
                    "model": model,
                    "reviewer": reviewed["actor"],
                    "applied_by": applied["actor"],
                },
            }
    return result


def saved_field_coverage(
    research,
    item,
    fields,
    *,
    applied_proposals=None,
    taxonomy=None,
    require_taxonomy_mapping=True,
    identity_blockers=(),
):
    """Current evidence for all eighteen saved fields, without writing anything.

    Research.blockers remains the authority for current identity, source and
    fact verification. Presence, an API barcode and an old APPLIED flag alone
    are never treated as documentary approval or permission to publish.
    """
    from .evidence_ai import COPY_FIELDS
    from .media_rights import media_permission_report
    from .proposals import Proposals
    from .seo_validation import field_limits, matches_documented_copy
    from .storage import digest
    from app.services.ecomm_api_product_workspace_service import _gtin_check_digit_valid

    edit = research.edit_record(item.ecomm_id)
    identity_blockers = list(identity_blockers)
    try:
        source = research.source_record(item.ecomm_id)
        identity_blockers.extend(source.get("identity_blockers") or [])
        if edit and edit.source_sku != source.get("sku"):
            identity_blockers.append(
                "Cambió el SKU de origen de esta ficha; revisar identidad."
            )
    except ValueError as exc:
        identity_blockers.append(str(exc))
    approved, blocked_fact_fields = [], set()
    for fact in item.facts:
        if fact.get("ecomm_id") != item.ecomm_id:
            continue
        if fact.get("state") == "APPROVED":
            issues = research.blockers(item, fact)
            if not issues:
                approved.append({**fact, "verified": True})
            else:
                blocked_fact_fields.add(fact["field"])
        elif fact.get("state") in {"STALE", "REVOKED"}:
            blocked_fact_fields.add(fact["field"])
    # Contradictory facts cannot become backing by selecting a convenient
    # subset from an older applied proposal. Keep unaffected field evidence.
    variants = {}
    for fact in approved:
        variants.setdefault(fact["field"], set()).add((fact["value"], fact.get("unit")))
    conflicts = {key for key, values in variants.items() if len(values) > 1}
    blocked_fact_fields.update(conflicts)
    approved = [fact for fact in approved if fact["field"] not in conflicts]
    by_id = {fact["id"]: fact for fact in approved}
    generation_errors = []
    try:
        generated, generation_errors = Proposals.generate_fields(approved)
    except ValueError as exc:
        generated = {}
        generation_errors = [str(exc)]
    direct = {
        key: value
        for key, value in generated.items()
        if fields.get(key) and matches_documented_copy(key, fields[key], value)
    }
    reviewed_copy = any(fields.get(key) for key in COPY_FIELDS)
    lineage_error, lineage = [], {}
    if reviewed_copy and approved and not identity_blockers:
        try:
            records = (
                applied_proposals
                if applied_proposals is not None
                else _applied_records(research, item.ecomm_id)
            )
            lineage = _reviewed_values(research, item, fields, approved, records)
        except ValueError as exc:
            lineage_error = [str(exc)]

    def citations(ids):
        output = []
        for ident in ids:
            fact = by_id[ident]
            doc = research._document(fact["document_id"])
            output.append(
                {
                    "fact_id": ident,
                    "field": fact["field"],
                    "state": "APPROVED",
                    "current": True,
                    "quote": fact["quote"],
                    "location": fact["location"],
                    "document_id": fact["document_id"],
                    "document_version": fact["document_version"],
                    "document_hash": fact["document_hash"],
                    "document_sha256": ((doc.body or {}).get("original") or {}).get(
                        "sha256"
                    )
                    if doc
                    else None,
                    "source_url": ((doc.body or {}).get("source") or {}).get(
                        "reference_url"
                    )
                    if doc
                    else None,
                }
            )
        return output

    rows = []
    for key in FIELDS:
        value = fields.get(
            key, "" if key not in {"attributes", "media", "sources"} else []
        )
        limits = field_limits(key, value)
        filled, ids, reasons, trace, extra_citations = bool(value), [], [], None, []
        state = "FILLED_UNBACKED" if filled else "PENDING_REVIEW"
        if identity_blockers or not limits["valid"]:
            state, reasons = "BLOCKED", [*identity_blockers, *limits["reasons"]]
        elif key == "media":
            permissions = media_permission_report(research, item, value)
            if filled:
                valid = len(permissions) == len(value) and all(
                    permission.get("stage4_ready", False)
                    and permission.get("current") is True
                    and permission.get("state") == "APPROVED_CURRENT"
                    for permission in permissions
                )
                state = "APPROVED_BACKED" if valid else "BLOCKED"
                reasons = (
                    []
                    if valid
                    else [
                        "Cada recurso necesita variante, presentación, hash, alt y permiso comercial vigentes."
                    ]
                )
                if valid:
                    extra_citations = [
                        {
                            "evidence_kind": "MEDIA_RIGHTS",
                            "fact_id": None,
                            "state": "APPROVED",
                            "current": True,
                            "document_id": permission.get("document_id"),
                            "document_version": permission.get("document_version"),
                            "document_hash": permission.get("document_hash"),
                            "document_sha256": permission.get("original_sha256"),
                            "quote": permission.get("quote"),
                            "location": permission.get("location"),
                            "source_url": resource.get("source_url"),
                            "resource_url": resource.get("url"),
                        }
                        for permission, resource in zip(permissions, value)
                    ]
            else:
                reasons = [
                    "Falta un recurso auténtico con procedencia y autorización documentada."
                ]
        elif key in {"category", "subcategory"} and require_taxonomy_mapping:
            mapping = (taxonomy or {}).get("record") or {}
            ids = mapping.get("evidence_ids") or []
            if (
                (taxonomy or {}).get("state") == "APPROVED"
                and (taxonomy or {}).get("catalog_bound") is True
                and mapping.get("review_kind") == "HUMAN_EXPLICIT"
                and mapping.get("ecomm_id") == item.ecomm_id
                and mapping.get("identity_hash") == item.identity_digest
                and ids
                and set(ids).issubset(by_id)
                and filled
                and (mapping.get("target_pair") or {}).get(key) == value
            ):
                state = "APPROVED_BACKED"
                trace = {
                    "evidence_kind": "INTERNAL_TAXONOMY_DECISION",
                    "mapping_version": (taxonomy or {}).get("mapping_version"),
                    "taxonomy_revision": mapping.get("taxonomy_revision"),
                    "reviewer": mapping.get("reviewer"),
                    "reason": mapping.get("reason"),
                    "target_pair": mapping.get("target_pair"),
                }
                reasons = [
                    "Clasificación interna revisada; no es una afirmación del fabricante."
                ]
            else:
                ids = []
                state = (
                    "BLOCKED"
                    if (taxonomy or {}).get("state") in {"STALE", "REVOKED", "BLOCKED"}
                    else state
                )
                reasons = [
                    "Falta equivalencia KIKI revisada, versionada y vigente para esta categoría/subcategoría."
                ]
        elif key == "proposed_gtin":
            ids = [
                fact["id"]
                for fact in approved
                if fact["field"] == "ean" and fact["value"] == value
            ]
            if filled and (
                not isinstance(value, str) or not _gtin_check_digit_valid(value)
            ):
                state, ids, reasons = (
                    "BLOCKED",
                    [],
                    ["Código con formato o dígito de control inválido."],
                )
            elif filled and ids:
                state = "APPROVED_BACKED"
            else:
                if filled and "ean" in blocked_fact_fields:
                    state = "BLOCKED"
                reasons = [
                    "El código de la API no certifica el EAN del fabricante; falta respaldo documental aprobado."
                ]
        elif key == "note":
            reasons = [
                "Nota interna opcional del operador; no acredita una afirmación comercial."
            ]
        elif key == "sources":
            allowed = {}
            for fact in approved:
                doc = research._document(fact["document_id"])
                url = (
                    ((doc.body or {}).get("source") or {}).get("reference_url")
                    if doc
                    else None
                )
                if url:
                    allowed.setdefault(url, []).append(fact["id"])
            if filled and all(
                row.get("verified") is True and row.get("url") in allowed
                for row in value
            ):
                state = "APPROVED_BACKED"
                ids = list(
                    dict.fromkeys(
                        ident for row in value for ident in allowed[row["url"]]
                    )
                )
            else:
                reasons = [
                    "La casilla de fuente verificada no reemplaza hechos vigentes y citados de ese original."
                ]
        elif key in direct or key in lineage:
            support = lineage.get(key) or direct[key]
            state, ids = "APPROVED_BACKED", support["evidence_ids"]
            trace = support.get("lineage")
        else:
            from .evidence_ai import SCOPE
            from .proposals import TEXT

            dependencies = (
                set(SCOPE.get(key) or {fact.get("field") for fact in item.facts})
                if key in COPY_FIELDS
                else set(TEXT)
                if key == "attributes"
                else {key}
            )
            if filled and blocked_fact_fields.intersection(dependencies):
                state = "BLOCKED"
            reasons = [
                "El contenido guardado no coincide con una propuesta respaldada vigente y revisada."
                if filled
                else "Faltan hechos aprobados vigentes o revisión del campo; no se inventa contenido.",
                *lineage_error,
            ]
        row = {
            "field": key,
            "state": state,
            "filled": filled,
            "limits": limits,
            "evidence_ids": list(dict.fromkeys(ids)),
            "citations": [*citations(ids), *extra_citations],
            "reasons": reasons,
            "field_review_required": not bool(trace),
            "lineage": trace,
            "suggested": generated.get(key)
            if state == "PENDING_REVIEW" and key not in {"category", "subcategory"}
            else None,
        }
        rows.append(row)
    counts = Counter(row["state"] for row in rows)
    result = {
        "schema_version": "kiki-saved-field-coverage-v1",
        "ecomm_id": item.ecomm_id,
        "workspace_version": edit.version if edit else 0,
        "total_fields": len(FIELDS),
        "states": {state: counts[state] for state in SAVED_STATES},
        "fields": rows,
        "supported_fields": [
            row["field"] for row in rows if row["state"] == "APPROVED_BACKED"
        ],
        "blocking_fields": [
            row["field"]
            for row in rows
            if row["state"] != "APPROVED_BACKED"
            and row["field"] not in {"note", "proposed_gtin"}
        ],
        "generation_gaps": generation_errors,
        "commercial_completion_certified": False,
        "publication_allowed": False,
    }
    result["fingerprint"] = digest(result)
    return result
