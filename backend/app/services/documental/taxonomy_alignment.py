"""Read-only taxonomy alignment against KIKI's *reviewed* editorial vocabulary.

A manufacturer's category is not a channel category. We only identify an
exact pre-existing pair for human consideration; no new category IDs, fuzzy
matching, publication or saved editorial fields are produced.
"""

from collections import Counter

from sqlalchemy import select

from app.database.models import EcommApiProductEdit

SEO_FIELDS = ("seo_title", "seo_description", "seo_keywords")

TAXONOMY_STATES = {
    "BLOCKED_EVIDENCE": "Documento vencido o identidad contradictoria",
    "CONFLICTING_APPROVED_FACTS": "Categorías aprobadas contradictorias",
    "SAVED_SOURCE_MISMATCH": "La ficha guardada difiere de la fuente aprobada",
    "ALREADY_SAVED": "La ficha ya tiene categoría y subcategoría",
    "INCOMPLETE_SAVED": "La ficha guardada tiene jerarquía incompleta",
    "NO_APPROVED_CATEGORY": "Falta categoría respaldada",
    "NO_APPROVED_SUBCATEGORY": "Falta subcategoría respaldada",
    "NO_REVIEWED_PAIRS": "Todavía no hay jerarquías listas para canales",
    "EXACT_REVIEWED_PAIR": "Coincidencia exacta con jerarquía interna ya revisada",
    "NEEDS_MAPPING": "La jerarquía del fabricante requiere equivalencia interna",
    "REVIEWED_INTERNAL_MAPPING": "Equivalencia interna revisada y versionada por operador",
}


def _key(text):
    if not isinstance(text, str):
        return ""
    text = " ".join(text.split())
    if (
        not text
        or len(text) > 160
        or any(ord(ch) < 32 or ord(ch) == 127 for ch in text)
    ):
        return ""
    return text.casefold()


def reviewed_internal_pairs(db):
    """Reference vocabulary only from edits marked READY_FOR_CHANNELS.

    Even that state is NOT proof of manufacturer provenance or channel
    publishing rights. Do not allow unreviewed DRAFT labels to propagate.
    """
    values = db.scalars(
        select(EcommApiProductEdit.fields).where(
            EcommApiProductEdit.status == "READY_FOR_CHANNELS"
        )
    )
    counts = Counter()
    labels = {}
    for fields in values:
        if not isinstance(fields, dict):
            continue
        category = " ".join(str(fields.get("category") or "").split())
        subcategory = " ".join(str(fields.get("subcategory") or "").split())
        pair = (_key(category), _key(subcategory))
        if not all(pair):
            continue
        counts[pair] += 1
        display = (category, subcategory)
        if pair not in labels or display < labels[pair]:
            labels[pair] = display
    return {
        pair: {
            "category": labels[pair][0],
            "subcategory": labels[pair][1],
            "referenced_fiches": count,
        }
        for pair, count in counts.items()
    }


def align_taxonomy(inspection, vocabulary):
    """Return exactly one documented state, never a guessed mapping."""
    approved = inspection.get("approved_taxonomy") or []
    grouping = {"category": {}, "subcategory": {}}
    for fact in approved:
        if not isinstance(fact, dict) or fact.get("field") not in grouping:
            continue
        value, evidence_id = fact.get("value"), fact.get("evidence_id")
        key = _key(value)
        if not key or not isinstance(evidence_id, str) or not evidence_id:
            continue
        grouping[fact["field"]].setdefault(
            key,
            {
                "value": " ".join(value.split()),
                "ids": [],
            },
        )["ids"].append(evidence_id)

    category, subcategory = grouping["category"], grouping["subcategory"]
    source = {
        "category": next(iter(category.values()))["value"]
        if len(category) == 1
        else None,
        "subcategory": next(iter(subcategory.values()))["value"]
        if len(subcategory) == 1
        else None,
    }
    evidence_ids = sorted(
        {
            ident
            for field in (category, subcategory)
            for row in field.values()
            for ident in row["ids"]
        }
    )
    existing = inspection.get("existing_taxonomy") or {}
    saved = {
        "category": str(existing.get("category") or "").strip(),
        "subcategory": str(existing.get("subcategory") or "").strip(),
        "status": str(existing.get("status") or "NOT_STARTED"),
    }
    proposed = None
    references = 0
    if inspection.get("conflicts") or inspection.get("stale"):
        state = "BLOCKED_EVIDENCE"
    elif len(category) > 1 or len(subcategory) > 1:
        state = "CONFLICTING_APPROVED_FACTS"
        source = {"category": None, "subcategory": None}
    elif saved["category"] or saved["subcategory"]:
        if (
            source["category"]
            and source["subcategory"]
            and saved["category"]
            and saved["subcategory"]
            and (_key(source["category"]), _key(source["subcategory"]))
            != (_key(saved["category"]), _key(saved["subcategory"]))
        ):
            state = "SAVED_SOURCE_MISMATCH"
        elif not saved["category"] or not saved["subcategory"]:
            state = "INCOMPLETE_SAVED"
        else:
            state = "ALREADY_SAVED"
    elif not source["category"]:
        state = "NO_APPROVED_CATEGORY"
    elif not source["subcategory"]:
        state = "NO_APPROVED_SUBCATEGORY"
    elif not vocabulary:
        state = "NO_REVIEWED_PAIRS"
    else:
        pair = (_key(source["category"]), _key(source["subcategory"]))
        match = vocabulary.get(pair)
        if match:
            state = "EXACT_REVIEWED_PAIR"
            proposed = {
                "category": match["category"],
                "subcategory": match["subcategory"],
            }
            references = match["referenced_fiches"]
        else:
            state = "NEEDS_MAPPING"
    mapping = inspection.get("reviewed_taxonomy_mapping")
    if (
        mapping
        and mapping.get("state") == "APPROVED"
        and state
        not in {
            "BLOCKED_EVIDENCE",
            "CONFLICTING_APPROVED_FACTS",
        }
    ):
        state = "REVIEWED_INTERNAL_MAPPING"
    return {
        "state": state,
        "label": TAXONOMY_STATES[state],
        "source_approved": source,
        "source_evidence_ids": evidence_ids,
        "existing_editorial": saved,
        "exact_internal_reference": proposed,
        "reference_fiches": references,
        "operator_review_required": True,
        "mapping_saved": False,
        "external_category_ids": None,
        "reviewed_mapping": mapping,
    }


def seo_field_audit(inspection, taxonomy=None):
    supported = set(inspection.get("supported_proposal_fields") or [])
    saved = set(inspection.get("existing_seo_fields") or [])
    blocked = inspection.get("conflicts") or inspection.get("stale")
    # Existing commercial/SEO drafts keep their contract, but a new preview
    # cannot claim that manufacturer taxonomy terms are ready to propagate.
    pending_taxonomy = bool(inspection.get("approved_taxonomy")) and (
        taxonomy is None
        or taxonomy["state"]
        not in {
            "EXACT_REVIEWED_PAIR",
            "ALREADY_SAVED",
        }
    )
    reviewed = (taxonomy or {}).get("reviewed_mapping") or {}
    if reviewed.get("state") == "APPROVED":
        record = reviewed.get("record") or {}
        # The existing generator uses manufacturer labels. An approved but
        # different commercial classification is not silently substituted.
        pending_taxonomy = record.get("target_pair") != record.get("source_pair")
    return {
        field: (
            "REVALIDATE"
            if blocked
            else "ALREADY_SAVED"
            if field in saved
            else "REVIEW_TAXONOMY"
            if field == "seo_keywords" and pending_taxonomy
            else "EVIDENCE_BACKED"
            if field in supported
            else "NEEDS_EVIDENCE"
        )
        for field in SEO_FIELDS
    }
