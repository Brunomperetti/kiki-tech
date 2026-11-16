"""Read-only documented research batch plan from the *complete* Ecomm capture.

This does not discover manufacturer URLs, fetch a web page, call AI or approve
data. Classification is exhaustive: every variant belongs to one safe/manual
bucket, while the eligible cohort only contains stable unique ID+SKU records
with a valid export-GTIN research *hint*, not a manufacturer's verified EAN.
"""
from collections import Counter
from datetime import datetime, timezone

from .ecomm_api_product_workspace_service import EcommApiProductWorkspace
from .ecomm_api_work_queue_service import build_queue
from .ecomm_gtin_export_service import safe_gtin_candidates_for_pages

BUCKETS = (
    "identity_review", "pack_review", "name_missing",
    "presentation_missing", "gtin_lookup_unavailable", "research_candidate",
)
MAX_BATCH = 20


def _bucket(row):
    if row["identity_issue"]:
        return "identity_review"
    if row["is_combo"]:
        return "pack_review"
    if not row["source_name_present"]:
        return "name_missing"
    if not row["source"].get("variant_description"):
        return "presentation_missing"
    if "research_gtin_unique" not in row["flags"]:
        return "gtin_lookup_unavailable"
    return "research_candidate"


def build_research_batch_plan(db, *, limit=10, offset=0):
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= MAX_BATCH:
        raise ValueError("Lote de investigación fuera de 1 a 20 productos.")
    if not isinstance(offset, int) or isinstance(offset, bool) or not 0 <= offset <= 10000:
        raise ValueError("Paginación de investigación inválida.")

    pages = EcommApiProductWorkspace(db)._source_pages()
    candidates = safe_gtin_candidates_for_pages(db, pages)
    # One complete queue projection, not the first page or a filtered partial
    # capture; all 2,784 variants remain classified.
    work = build_queue(db, export_rows=True)
    rows = work["items"]
    counters = Counter()
    eligible = []
    for row in rows:
        bucket = _bucket(row)
        counters[bucket] += 1
        if bucket == "research_candidate":
            ecomm_id = row["ecomm_id"]
            gtin = candidates.get(ecomm_id)
            if not gtin:
                # Detect stale/improper export rather than inventing an EAN.
                raise ValueError("GTIN de investigación no conciliado con captura completa.")
            eligible.append({
                "ecomm_id": ecomm_id,
                "sku": row["sku"],
                "name": row["source"]["product_name"],
                "presentation_original": row["source"]["variant_description"],
                "gtin_lookup_hint": gtin,
                "editorial_status": row["status"],
                "priority": row["priority"],
                "source_url": None,
                "manufacturer_verified": False,
                "facts_approved": False,
                "next_step": "ENCONTRAR_URL_OFICIAL_Y_VERIFICAR_IDENTIDAD",
            })
    if sum(counters.values()) != len(rows):
        raise ValueError("No se clasificó todo el catálogo.")
    if len(eligible) != counters["research_candidate"]:
        raise ValueError("La selección difiere de la clasificación real.")
    # The priority of each item was computed by the existing editorial queue.
    # Never pretend a higher priority certifies a better manufacturer match.
    result = eligible[offset:offset + limit]
    return {
        "mode": "READ_ONLY_RESEARCH_BATCH_PLAN",
        "source": work["source"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_variants": len(rows),
        "classified_variants": sum(counters.values()),
        "buckets": {key: counters[key] for key in BUCKETS},
        "eligible_total": len(eligible),
        "batch_size": len(result),
        "limit": limit,
        "offset": offset,
        "next_offset": offset + limit if offset + limit < len(eligible) else None,
        "items": result,
        "network_requests": 0,
        "ai_requests": 0,
        "external_writes_enabled": False,
        "can_auto_fetch": False,
        "manufacturer_urls_discovered": 0,
        "policy": (
            "Planificación únicamente. Los códigos del Excel son pistas de búsqueda, "
            "no EAN certificados. Cada fabricante, presentación, fuente, claim y "
            "material gráfico requieren evidencia original y revisión humana."
        ),
    }
