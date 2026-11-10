"""Versioned read-only input contract for a future provider. No model/client/key."""

from copy import deepcopy
import json
from app.services.ecomm_api_product_workspace_service import TEXT_LIMITS, ARRAY_LIMITS
from app.services.ecomm_ai_editor_service import EcommAiEditor
from .proposals import Proposals
from .research.storage import digest

CONTRACT_VERSION = "kiki-evidence-generation-v1"


def generation_context(db, session, ident):
    service = Proposals(db, session)
    edit, dossier, approved, fingerprint = service.context(ident)
    facts = [
        {
            key: deepcopy(f[key])
            for key in (
                "id",
                "field",
                "value",
                "unit",
                "quote",
                "location",
                "document_id",
                "document_version",
                "document_hash",
                "version",
                "identity_hash",
                "presentation",
            )
        }
        for f in approved
    ]
    # Never truncate citations. A future invocation must be refused, not lose evidence.
    if len(facts) > 40:
        raise ValueError(
            "Hechos respaldados exceden el presupuesto de entrada; revisar alcance sin recortar citas."
        )
    context = {
        "schema_version": CONTRACT_VERSION,
        "ecomm_id": ident,
        "workspace_version": edit["version"],
        "dossier_version": dossier.version,
        "identity_hash": dossier.identity_digest,
        "evidence_fingerprint": fingerprint,
        "facts": facts,
        "allowed_text_fields": dict(TEXT_LIMITS),
        "allowed_array_fields": dict(ARRAY_LIMITS),
        "provider": {"name": "OpenAI", "enabled": False, "model": None, "calls": 0},
        "controls": {
            "max_input_characters": 24000,
            "max_facts": 40,
            "max_output_tokens": 1500,
            "max_calls_per_proposal": 1,
            "existing_daily_attempt_limit": EcommAiEditor.MAX_DAILY_ATTEMPTS,
            "reuse_existing_daily_reservations_and_draft_storage": True,
            "automatic_retries": 0,
            "max_cost_usd": "0.00",
            "max_daily_cost_usd": "0.00",
            "requires_model_price_review_and_atomic_budget_reservation": True,
            "source_text_is_untrusted_data": True,
            "require_fact_ids_per_field": True,
            "require_human_review": True,
            "reject_unbacked_claims": True,
            "apply_via_existing_versioned_editor": True,
        },
        "response_contract": {
            "schema_version": CONTRACT_VERSION,
            "context_hash": "must_equal_this_context",
            "fields": "only existing editor fields; each value requires approved fact IDs and exact quotes",
            "unknowns": "omit fields; never infer food, nutritional or certification claims",
        },
    }
    context["context_hash"] = digest(context)
    if len(json.dumps(context, ensure_ascii=False)) > 24000:
        raise ValueError(
            "Contexto completo excede el presupuesto; no se recortaron citas."
        )
    db.commit()
    return context
