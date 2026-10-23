"""Bounded read-only quality audit for the Ecomm-App inventory listing.

This intentionally does not persist any snapshot. Before promoting a source,
pagination stability, uniqueness of variant IDs, and payload completeness
need to be verified against real vendor results.
"""
from collections import Counter

from .public_api import _items, API_PREFIX, EcommAppApiError


PAGE_SIZE = 50
MAX_AUDIT_PAGES = 2


def _public_pagination(data: object) -> dict:
    meta = {}
    if isinstance(data, dict):
        raw = data.get("paginacion")
        if not isinstance(raw, dict):
            raw = data.get("pagination")
        if isinstance(raw, dict):
            meta = raw
    # Never expose the entire external response; only safe scalar metadata.
    safe = {}
    for key in ("page", "current_page", "total", "total_items", "per_page",
                "limit", "last_page", "total_pages", "pages", "has_next"):
        value = meta.get(key)
        if isinstance(value, (int, bool)) and not isinstance(value, float):
            safe[key] = value
    return {
        "present": bool(meta),
        "available_fields": sorted(meta.keys())[:25],
        "values": safe,
    }


def audit_catalog_pages(fetch_page, *, start_page: int = 1) -> dict:
    if isinstance(start_page, bool) or not isinstance(start_page, int) or not 1 <= start_page <= 10000:
        raise ValueError("La página inicial debe estar entre 1 y 10000.")

    pages = []
    seen_ids = set()
    seen_skus = set()
    duplicate_ids = set()
    duplicate_skus = set()
    counters = Counter()
    samples = []
    for page in range(start_page, start_page + MAX_AUDIT_PAGES):
        data = fetch_page(page)
        parents, envelope_fields = _items(data)
        if parents is None:
            raise EcommAppApiError(
                502, "PAGINACION_DESCONOCIDA",
                "La API respondió con un formato de catálogo desconocido. No se interpretó como catálogo vacío.",
            )
        if len(parents) > PAGE_SIZE:
            raise EcommAppApiError(
                502, "PAGINA_EXCEDIDA", "Ecomm-App devolvió más de 50 productos para una página.",
            )
        pagination = _public_pagination(data)
        pages.append({
            "page": page,
            "parents": len(parents),
            "pagination": pagination,
            "envelope_fields": envelope_fields,
        })
        counters["parents"] += len(parents)
        for parent in parents:
            variants = parent.get("variants")
            if not isinstance(variants, list):
                counters["parents_without_variants_array"] += 1
                continue
            if parent.get("is_combo") is True:
                counters["combo_parents"] += 1
            for variant in variants:
                if not isinstance(variant, dict):
                    counters["invalid_variants"] += 1
                    continue
                counters["variants"] += 1
                vid = variant.get("id")
                sku = variant.get("sku")
                if vid is None or vid == "":
                    counters["variants_without_id"] += 1
                else:
                    token = str(vid)
                    if token in seen_ids:
                        duplicate_ids.add(token)
                    seen_ids.add(token)
                if not isinstance(sku, str) or not sku.strip():
                    counters["variants_without_sku"] += 1
                else:
                    if sku in seen_skus:
                        duplicate_skus.add(sku)
                    seen_skus.add(sku)
                if variant.get("is_combo") is True:
                    counters["combo_variants"] += 1
                if variant.get("total_stock") is None:
                    counters["variants_without_total_stock"] += 1
                if len(samples) < 4:
                    samples.append({
                        "parent_code": parent.get("code"),
                        "sku": sku,
                        "variant_id": vid,
                        "is_combo": variant.get("is_combo") if isinstance(variant.get("is_combo"), bool) else None,
                        "total_stock": variant.get("total_stock"),
                    })
        # An incomplete page may mark the end; report its pagination metadata
        # rather than guessing that the entire catalog was consumed.
        if len(parents) < PAGE_SIZE:
            break

    last_count = pages[-1]["parents"]
    next_page = pages[-1]["page"] + 1 if last_count == PAGE_SIZE else None
    return {
        "mode": "READ_ONLY_AUDIT",
        "start_page": start_page,
        "page_size": PAGE_SIZE,
        "pages_read": len(pages),
        "pages": pages,
        "next_page_to_check": next_page,
        "is_full_catalog": False,
        "totals_in_this_batch": {
            "parents": counters["parents"],
            "variants": counters["variants"],
            "combo_parents": counters["combo_parents"],
            "combo_variants": counters["combo_variants"],
            "variants_without_id": counters["variants_without_id"],
            "variants_without_sku": counters["variants_without_sku"],
            "variants_without_total_stock": counters["variants_without_total_stock"],
            "parents_without_variants_array": counters["parents_without_variants_array"],
            "invalid_variants": counters["invalid_variants"],
            "repeated_variant_ids": len(duplicate_ids),
            "repeated_skus": len(duplicate_skus),
        },
        "examples": samples,
        "notice": (
            "Auditoría parcial: solo se leyeron las páginas indicadas. "
            "No se importó ni guardó el catálogo; no se cambiaron snapshots, "
            "precios, stock, familias ni decisiones. Los duplicados se cuentan "
            "únicamente dentro del bloque consultado."
        ),
    }
