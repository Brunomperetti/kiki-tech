"""Explain every existing editor field without equating presence with evidence.

Pure projection of the existing versioned proposal, human decisions and current
facts. It does not generate extra commercial claims or certify channel readiness.
"""

from collections import Counter

from app.services.ecomm_api_product_workspace_service import FIELDS

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
