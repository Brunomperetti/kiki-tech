"""Read-only Mercado Libre listing evidence for suspected duplicate Ecomm products.

An MLA is NOT a variant ID. One shared alias or listing may match several Ecomm
products. This helper only shows what the imported ML snapshot actually says;
it cannot authorize a link, a stock update, or the duplicate-review decision.
"""
from collections import defaultdict


def _clean(value) -> str:
    return str(value).strip() if value is not None else ""


def _product_skus(product: dict) -> tuple[set[str], set[str]]:
    primary = {
        _clean(product.get(field))
        for field in ("sku_variant", "sku_effective", "sku", "sku_product")
    }
    primary.discard("")
    aliases = {_clean(value) for value in (product.get("sku_aliases") or [])}
    aliases.discard("")
    return ({x.casefold() for x in primary}, {x.casefold() for x in aliases})


def explain_ml_evidence(group: dict, snapshot_rows: list[dict] | None,
                        source: str, snapshot_at: str | None,
                        changed_since_run: bool) -> dict:
    """Inspect only referenced MLAs and classify SKU evidence per listing row.

    A unique exact SKU is an identity *candidate*, not a confirmed variant;
    the ML XLSX may have no real variation ID. Rows without a concrete SKU or
    with only a shared SKU alias are always ambiguous/unresolved.
    """
    products = [
        {
            "key": _clean((item.get("product") or {}).get("ecomm_id"))
                   or _clean((item.get("product") or {}).get("sku"))
                   or str(i),
            "name": _clean((item.get("product") or {}).get("name")),
            "skus": _product_skus(item.get("product") or {}),
        }
        for i, item in enumerate(group.get("results") or [])
    ]
    ml_ids = sorted({
        _clean(ml_id)
        for item in group.get("results") or []
        for ml_id in [
            *(item.get("matched_listing_ids") or []),
            (item.get("listing") or {}).get("external_id"),
        ]
        if _clean(ml_id)
    })
    if not ml_ids:
        return {
            "available": False,
            "reason": "No hay MLA identificados en esta conciliación.",
            "source": source, "snapshot_at": snapshot_at,
            "changed_since_run": changed_since_run, "rows": [],
        }

    if snapshot_rows is None:
        return {
            "available": False,
            "reason": "No está disponible el snapshot ML usado en la conciliación.",
            "source": source, "snapshot_at": snapshot_at,
            "changed_since_run": changed_since_run, "rows": [],
        }

    by_mla: dict[str, list[dict]] = defaultdict(list)
    reference_ids = {value.casefold() for value in ml_ids}
    for row in snapshot_rows:
        mla = _clean(row.get("external_id"))
        if mla.casefold() in reference_ids:
            by_mla[mla.casefold()].append(row)

    evidence = []
    for mla in ml_ids:
        matching = by_mla.get(mla.casefold(), [])
        if not matching:
            evidence.append({
                "mla": mla, "sku": "", "variation_id": "", "title": "",
                "listing_status": "", "price": None,
                "classification": "NOT_IN_SNAPSHOT", "candidates": [],
                "explanation": "El MLA asociado no existe en este snapshot. Recargá la fuente y conciliá antes de tomar decisiones.",
            })
            continue
        for row in matching:
            sku = _clean(row.get("variant_sku") or row.get("sku_effective")
                         or row.get("sku") or row.get("sku_product"))
            key = sku.casefold()
            strong = [p for p in products if key and key in p["skus"][0]]
            aliases = [p for p in products if key and key in p["skus"][1]]
            matches = strong or aliases
            if len(strong) == 1:
                classification = "ONE_EXACT_SKU_CANDIDATE"
                message = "SKU exacto en una ficha Ecomm; falta comprobar presentación y variante ML."
            elif len(strong) > 1:
                classification = "SHARED_EXACT_SKU"
                message = "Este SKU figura como principal en varias fichas Ecomm; no se puede elegir una."
            elif len(aliases) > 1:
                classification = "SHARED_ALIAS"
                message = "El SKU aparece como alias de varios productos. No asignar stock por este dato."
            elif len(aliases) == 1:
                classification = "ALIAS_CANDIDATE"
                message = "SKU coincidente solo por alias; requiere confirmar la identidad de la variación."
            else:
                classification = "NO_SKU_EVIDENCE"
                message = "Sin SKU exacto identificable para estas fichas; no se puede inferir una relación."
            variation_id = _clean(row.get("variation_id"))
            if not variation_id:
                message += " El snapshot no trae un ID de variación ML verificable."
            evidence.append({
                "mla": mla,
                "sku": sku,
                "variation_id": variation_id,
                "title": _clean(row.get("title")),
                "listing_status": _clean(row.get("status")),
                "price": str(row.get("price")) if row.get("price") is not None else None,
                "classification": classification,
                "candidates": [{"key": p["key"], "name": p["name"]} for p in matches],
                "explanation": message,
            })

    evidence.sort(key=lambda x: (x["mla"], x["variation_id"], x["sku"]))
    return {
        "available": True,
        "source": source,
        "snapshot_at": snapshot_at,
        "changed_since_run": changed_since_run,
        "reason": (
            "El snapshot cambió después de la conciliación: estas evidencias son orientativas; ejecutá una nueva conciliación."
            if changed_since_run else
            "Evidencia del snapshot utilizado; no se confirma una vinculación ni un descuento de stock."
        ),
        "rows": evidence,
        "summary": {
            "mlas": len(ml_ids),
            "offer_rows": len(evidence),
            "exact_sku_candidate_rows": sum(r["classification"] == "ONE_EXACT_SKU_CANDIDATE" for r in evidence),
            "ambiguous_rows": sum(r["classification"] not in {"ONE_EXACT_SKU_CANDIDATE"} for r in evidence),
            "with_variation_id": sum(bool(r["variation_id"]) for r in evidence),
        },
    }
