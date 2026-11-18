"""Read-only, evidence-backed commercial readiness plan for up to 20 variants.

This is not a content generator or an AI/provider call. It reuses the same
versioned, approved-fact inspection as the established editorial batch engine.
Only field NAMES and blockers are returned; no unverifiable marketing copy.
"""
from collections import Counter

from app.core.config import get_settings
from app.integrations.ecomm_app.api_catalog_browser import valid_variant_id
from app.services.editorial_batches.context import Context, sources
from .taxonomy_alignment import align_taxonomy, reviewed_internal_pairs, seo_field_audit


MAX_ITEMS = 20

TASK_LABELS = {
    "REVIEW_IDENTITY": "Resolver identidad o datos contradictorios",
    "FIND_SOURCE": "Obtener documentación de fabricante o etiqueta",
    "REVALIDATE": "Revalidar evidencia o revisión vencida",
    "APPROVE_FACTS": "Revisar procedencia y aprobar hechos respaldados",
    "REVIEW_TAXONOMY": "Revisar la equivalencia de categorías y subcategorías",
    "GENERATE": "Preparar propuesta interna con hechos aprobados",
    "REVIEW_EDITORIAL": "Revisar campos comerciales, SEO, categorías y medios",
}


def task_for(inspection, taxonomy=None):
    """Priority order is deliberately strict; no approval by omission."""
    if inspection["conflicts"]:
        return "REVIEW_IDENTITY"
    if inspection["no_documentation"]:
        return "FIND_SOURCE"
    if inspection["stale"]:
        return "REVALIDATE"
    if not inspection["sufficient_evidence"]:
        return "APPROVE_FACTS"
    if taxonomy and taxonomy["state"] in {
        "CONFLICTING_APPROVED_FACTS", "SAVED_SOURCE_MISMATCH",
        "INCOMPLETE_SAVED", "NO_REVIEWED_PAIRS", "NEEDS_MAPPING",
    }:
        return "REVIEW_TAXONOMY"
    if inspection["eligible"]:
        return "GENERATE"
    return "REVIEW_EDITORIAL"


def summarize_inspections(rows, vocabulary=None):
    vocabulary = vocabulary if vocabulary is not None else {}
    result = []
    for ident, inspected in rows:
        taxonomy = align_taxonomy(inspected, vocabulary)
        task = task_for(inspected, taxonomy)
        supported = list(inspected.get("supported_proposal_fields") or [])
        missing = list(inspected.get("fields_without_support") or [])
        if inspected.get("conflicts") or inspected.get("stale"):
            # No cached proposal may look actionable while evidence is invalid.
            supported = []
        elif taxonomy["state"] != "EXACT_REVIEWED_PAIR":
            # An approved manufacturer label is not automatically a KIKI
            # category. Keep it out of supported editorial fields until mapped.
            held = [key for key in supported if key in {"category", "subcategory"}]
            supported = [key for key in supported if key not in held]
            missing = list(dict.fromkeys([*missing, *held]))
        seo_fields = seo_field_audit(inspected, taxonomy)
        if seo_fields["seo_keywords"] == "REVIEW_TAXONOMY":
            supported = [field for field in supported if field != "seo_keywords"]
            missing = list(dict.fromkeys([*missing, "seo_keywords"]))
        result.append({
            "ecomm_id": ident,
            "name": inspected.get("name") or "",
            "presentation": inspected.get("presentation"),
            "next_task": task,
            "next_task_label": TASK_LABELS[task],
            "approved_facts": inspected.get("approved_fact_count", 0),
            "fields_supported": supported,
            "fields_needing_support": missing,
            "taxonomy_alignment": taxonomy,
            "seo_fields": seo_fields,
            "reasons": list(dict.fromkeys(inspected.get("reasons") or []))[:8],
            "review_due": bool((inspected.get("review_schedule") or {}).get("review_due")),
            "human_review_required": True,
            "commercial_fiche_saved": False,
        })
    tally = Counter(row["next_task"] for row in result)
    taxonomy_counts = Counter(row["taxonomy_alignment"]["state"] for row in result)
    return {
        "mode": "READ_ONLY_COMMERCIAL_EVIDENCE_PLAN",
        "total": len(result),
        "counts": {key: tally[key] for key in TASK_LABELS},
        "taxonomy_counts": dict(sorted(taxonomy_counts.items())),
        "reviewed_internal_pairs": len(vocabulary),
        "taxonomy_reference": "KIKI_EDITORIAL_READY_FOR_CHANNELS_ONLY",
        "items": result,
        "external_writes_enabled": False,
        "provider_calls": 0,
        "ai_requests": 0,
        "facts_approved": 0,
        "automatic_publications": 0,
        "policy": (
            "Planificación sin cambios. Solo los hechos aprobados y vigentes "
            "permiten proponer campos. Identidad, categorías, contenido, "
            "medios y publicación conservan revisión humana. La taxonomía de "
            "fabricante solo se compara con categorías internas ya marcadas "
            "listas para canales, sin asignarlas automáticamente."
        ),
    }


def commercial_plan(
    db, session, ids, *, source_loader=sources, context_type=Context,
    taxonomy_loader=reviewed_internal_pairs,
):
    if (
        not 1 <= len(ids) <= MAX_ITEMS or len(set(ids)) != len(ids)
        or not all(isinstance(i, str) and valid_variant_id(i) for i in ids)
    ):
        raise ValueError("Seleccioná entre 1 y 20 Ecomm ID únicos y válidos.")
    catalog = source_loader(db)
    if any(ident not in catalog for ident in ids):
        raise ValueError("Una variante no está en la captura completa Ecomm-App API.")

    context = context_type(
        db, ids, catalog, get_settings().kiki_editorial_context_bytes
    )
    try:
        reports = [(ident, context.inspect(db, session, ident)) for ident in ids]
        vocabulary = taxonomy_loader(db)
        return summarize_inspections(reports, vocabulary)
    finally:
        context.release()
