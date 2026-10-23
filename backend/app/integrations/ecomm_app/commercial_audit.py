"""Read-only quality audit of commercial fields in the historical Ecomm catalog.

Never infer a manufacturer from a product title or treat historical prices as
current. Audits ONLY records with one unique variant ID in both snapshots.
"""
from collections import Counter
from decimal import Decimal, InvalidOperation

from .catalog_hybrid_preview import _indexes
from .catalog_stage import stage_status
from .catalog_comparison import _legacy_sku, _str

SAMPLE_LIMIT = 8
BRAND_PLACEHOLDERS = {"-", "n/a", "na", "s/m", "sin marca", "sin informar", "no informado"}


def _price_class(value) -> str:
    if value is None or isinstance(value, bool) or str(value).strip() == "":
        return "MISSING"
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return "INVALID"
    if not amount.is_finite():
        return "INVALID"
    if amount < 0:
        return "NEGATIVE"
    if amount == 0:
        return "ZERO"
    return "POSITIVE"


def _brand_class(value) -> str:
    if value is None or not _str(value):
        return "MISSING"
    if _str(value).casefold() in BRAND_PLACEHOLDERS:
        return "PLACEHOLDER"
    return "PRESENT"


def _compact(old: dict, parent: dict, variant: dict) -> dict:
    return {
        "ecomm_id": _str(old.get("ecomm_id")),
        "sku": _legacy_sku(old),
        "name": _str(old.get("name")),
        "api_sku": _str(variant.get("sku")),
        "is_combo": variant.get("is_combo") if isinstance(variant.get("is_combo"), bool) else None,
        "parent_code": _str(parent.get("code")),
    }


def _append(rows: list, data: dict) -> None:
    if len(rows) < SAMPLE_LIMIT:
        rows.append(data)


def commercial_fields_audit(stage_pages: list[dict], legacy: list[dict]) -> dict:
    state = stage_status(stage_pages)
    if (not state["complete"] or
            state["quality"]["parents"] != state["expected_parents"]):
        raise ValueError("Se requiere una copia API completa para auditar datos comerciales.")
    if not isinstance(legacy, list) or not legacy:
        raise ValueError("No existe un catálogo Ecomm histórico para auditar.")

    older, newer = _indexes(stage_pages, legacy)
    counts = Counter()
    samples = {
        "without_brand": [],
        "price_review": [],
        "cost_review": [],
    }

    for key in sorted(older):
        old_rows = older[key]
        api_rows = newer.get(key, [])
        # Skip all ambiguous/duplicate IDs, never choose one based on SKU.
        if len(old_rows) != 1 or len(api_rows) != 1:
            continue
        old = old_rows[0]
        parent, variant = api_rows[0]
        item = _compact(old, parent, variant)
        counts["matched_ids"] += 1

        brand_class = _brand_class(old.get("brand"))
        counts["brand_" + brand_class.lower()] += 1
        if brand_class in ("MISSING", "PLACEHOLDER"):
            _append(samples["without_brand"], {
                **item, "brand_status": brand_class,
            })

        # For the canonical historical product, price and list_price are
        # synonyms. Prefer an explicitly present list price to price.
        price_value = old.get("list_price")
        if price_value is None or str(price_value).strip() == "":
            price_value = old.get("price")
        price_class = _price_class(price_value)
        counts["price_" + price_class.lower()] += 1
        if price_class != "POSITIVE":
            _append(samples["price_review"], {
                **item, "status": price_class, "value": str(price_value) if price_value is not None else None,
            })

        cost_value = old.get("cost")
        cost_class = _price_class(cost_value)
        counts["cost_" + cost_class.lower()] += 1
        if cost_class != "POSITIVE":
            _append(samples["cost_review"], {
                **item, "status": cost_class, "value": str(cost_value) if cost_value is not None else None,
            })

        if _str(old.get("ean")):
            counts["ean_present"] += 1
        else:
            counts["ean_blank"] += 1
        if variant.get("is_combo") is True:
            counts["combo_matched"] += 1
            if brand_class != "PRESENT":
                counts["combo_without_brand"] += 1

    return {
        "mode": "READ_ONLY_COMMERCIAL_AUDIT",
        "source": "ECOMM_APP",
        "reference": "ECOMM_APP_API_STAGE",
        "activation_allowed": False,
        "counts": {
            "matched_ids": counts["matched_ids"],
            "brand_present": counts["brand_present"],
            "brand_missing": counts["brand_missing"],
            "brand_placeholder": counts["brand_placeholder"],
            "price_positive": counts["price_positive"],
            "price_zero": counts["price_zero"],
            "price_missing": counts["price_missing"],
            "price_negative": counts["price_negative"],
            "price_invalid": counts["price_invalid"],
            "cost_positive": counts["cost_positive"],
            "cost_zero": counts["cost_zero"],
            "cost_missing": counts["cost_missing"],
            "cost_negative": counts["cost_negative"],
            "cost_invalid": counts["cost_invalid"],
            "ean_present": counts["ean_present"],
            "ean_blank": counts["ean_blank"],
            "combo_matched": counts["combo_matched"],
            "combo_without_brand": counts["combo_without_brand"],
        },
        "samples": samples,
        "sampling_limit": SAMPLE_LIMIT,
        "note": (
            "Los datos comerciales provienen solo del Excel histórico de Ecomm-App. "
            "El recuento incluye exclusivamente los ID de variante únicos reconocidos "
            "en ambas fuentes. Un precio o costo positivo no demuestra vigencia. "
            "Cero, negativo, inválido y vacío se señalan para revisión, sin corregirlos. "
            "Los campos de marca en blanco o con un marcador genérico NO prueban que "
            "no exista marca en Tiendanube, Mercado Libre u otra fuente. "
            "No se modifica ninguna ficha ni se autoriza el reemplazo del Excel."
        ),
    }
