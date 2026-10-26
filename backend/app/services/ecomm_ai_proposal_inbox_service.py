"""Read-only inbox for persisted Ecomm-App AI proposals.

Lists latest proposal per unique Ecomm variant. A saved commercial KIKI edit
is distinct from a generated AI draft; no application or review is inferred.
"""
from datetime import datetime, timezone

from sqlalchemy import func, select

from ..database.models import EcommApiProductEdit, KikiAiEditorialDraft

PREFIX = "ECOMM_API:"
VALID_FILTERS = {"all", "with_edit", "without_edit"}


def list_ecomm_ai_proposals(db, *, query="", saved_filter="all", page=1, limit=25):
    if saved_filter not in VALID_FILTERS:
        raise ValueError("Filtro de propuestas desconocido.")
    if page < 1 or page > 100000 or limit < 1 or limit > 50 or len(query) > 80:
        raise ValueError("Consulta o paginación fuera de límites.")
    # Last proposal per product, regardless of whether it has later been copied
    # or saved to KIKI. We do not treat an AI record as an editorial approval.
    last = (
        select(func.max(KikiAiEditorialDraft.id).label("latest_id"))
        .where(KikiAiEditorialDraft.product_key.like(PREFIX + "%"))
        .group_by(KikiAiEditorialDraft.product_key)
        .subquery()
    )
    proposals = db.scalars(
        select(KikiAiEditorialDraft)
        .join(last, KikiAiEditorialDraft.id == last.c.latest_id)
        .order_by(KikiAiEditorialDraft.id.desc())
    ).all()
    saved = {
        row.ecomm_id: row.status
        for row in db.scalars(select(EcommApiProductEdit)).all()
    }
    items = []
    term = query.strip().casefold()
    all_count = len(proposals)
    saved_count = 0
    for record in proposals:
        ecomm_id = record.product_key[len(PREFIX):]
        fields = {
            entry.get("field"): str(entry.get("value") or "")
            for entry in (record.source_facts or [])
            if isinstance(entry, dict) and isinstance(entry.get("field"), str)
        }
        sku = fields.get("sku", "")
        edit_status = saved.get(ecomm_id)
        if edit_status is not None:
            saved_count += 1
        if term and not any(term in str(value).casefold() for value in (
            ecomm_id, sku, record.original_name, record.title,
        )):
            continue
        if saved_filter == "with_edit" and edit_status is None:
            continue
        if saved_filter == "without_edit" and edit_status is not None:
            continue
        items.append({
            "ecomm_id": ecomm_id,
            "sku": sku,
            "product_name": record.original_name,
            "latest_draft_id": record.id,
            "created_at": record.created_at.isoformat() if record.created_at else None,
            "has_saved_product_edit": edit_status is not None,
            "product_edit_status": edit_status,
            "proposal_review_status": "REVIEW_IN_PRODUCT_EDITOR",
            "source_freshness": "VERIFY_ON_OPEN",
        })
    offset = (page - 1) * limit
    return {
        "total": len(items), "page": page, "limit": limit,
        "query": query.strip(), "filter": saved_filter,
        "summary": {
            "products_with_ai_proposals": all_count,
            "products_with_saved_edits": saved_count,
            "products_without_saved_edits": all_count - saved_count,
        },
        "items": items[offset:offset + limit],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "INTERNAL_GENERATED_AI_PROPOSALS_READ_ONLY",
        "external_writes_enabled": False,
        "policy": (
            "Una propuesta IA generada se guarda por separado de la ficha "
            "comercial de KIKI. Un producto con ficha guardada no demuestra "
            "que la propuesta IA haya sido aceptada. Abrí el editor para "
            "comprobar vigencia, revisar y guardar los campos correctos."
        ),
    }
