"""Read-only Ecomm API snapshot vs ML API snapshot reconciliation *preview*.

Never reads ECOMM_APP/ECOMM_APP_RAW (historical Excel), never creates a
ReconciliationRun, and never applies any prior decision or changes stock.
SKU is a lead for manual verification, not an approved channel link.
"""
from collections import Counter, defaultdict

from ...services.tiendanube_assisted_match_service import variant_conflict
from ...services.tiendanube_quality_audit_service import gtin_status
from .catalog_stage import stage_status

MAX_EXAMPLES_PER_STATUS = 6


def _string(value):
    return str(value).strip() if value is not None else ""


def _sku(value):
    return _string(value).casefold()


def _gtin(value):
    code = _string(value)
    return code if gtin_status(code) == "VALID_CHECK_DIGIT" else ""


def api_ml_reconciliation_preview(pages: list[dict] | None, ml_rows: list[dict] | None):
    status = stage_status(pages)
    quality = status["quality"]
    blocking = (
        "parents_without_variants", "invalid_variants", "without_variant_id",
        "without_sku", "duplicate_variant_ids",
    )
    if (not status["complete"] or
            quality["parents"] != status["expected_parents"] or
            any(quality.get(field, 0) for field in blocking)):
        raise ValueError("La copia Ecomm API no está completa o tiene problemas de identidad.")
    if not isinstance(ml_rows, list) or not ml_rows:
        raise ValueError(
            "No hay una copia de publicaciones Mercado Libre API. "
            "Sin datos ML API no se puede hacer esta comparación."
        )

    by_sku = defaultdict(list)
    gtin_owners = defaultdict(set)
    api_ids = set()
    for page in pages or []:
        for parent in page.get("items") or []:
            for variant in parent.get("variants") or []:
                if not isinstance(variant, dict) or variant.get("invalid"):
                    continue
                ecomm_id = _string(variant.get("id"))
                sku = _string(variant.get("sku"))
                name = _string(parent.get("description"))
                detail = _string(variant.get("variant_description") or variant.get("description"))
                candidate = {
                    "ecomm_id": ecomm_id,
                    "sku": sku,
                    "name": name,
                    "variant_description": detail,
                    "is_combo": variant.get("is_combo"),
                    "gtin": _string(variant.get("gtin") or variant.get("barcode")),
                }
                api_ids.add(ecomm_id)
                if _sku(sku):
                    by_sku[_sku(sku)].append(candidate)
                valid = _gtin(candidate["gtin"])
                if valid:
                    gtin_owners[valid].add(ecomm_id)

    counts = Counter()
    examples = defaultdict(list)
    results_by_id = defaultdict(set)
    for ml in ml_rows:
        if not isinstance(ml, dict):
            raise ValueError("Hay registros ML API que no son objetos válidos.")
        external_id = _string(ml.get("external_id"))
        listing_sku = _string(ml.get("variant_sku"))
        product_sku = _string(ml.get("sku_effective") or ml.get("sku"))
        ml_gtin = _string(ml.get("ean"))
        title = _string(ml.get("title"))
        candidates = by_sku.get(_sku(listing_sku), []) if listing_sku else []

        selected = None
        note = ""
        if not listing_sku:
            kind = "NO_EXPLICIT_VARIANT_SKU"
            note = (
                "ML no informa SKU de variante verificable. "
                "Un SKU general no confirma identidad de variación."
            )
            if product_sku and by_sku.get(_sku(product_sku)):
                kind = "PRODUCT_SKU_ONLY"
        elif len(candidates) > 1:
            kind = "DUPLICATE_API_SKU"
            note = "El SKU de variante ML pertenece a varios IDs API; no elegir uno."
        elif not candidates:
            kind = "SKU_NOT_IN_API"
            note = "No existe coincidencia exacta para SKU de variante en la copia API."
        else:
            selected = candidates[0]
            results_by_id[selected["ecomm_id"]].add(external_id)
            full_name = " ".join((selected["name"], selected["variant_description"]))
            if variant_conflict(full_name, selected["sku"], title, listing_sku):
                kind = "PRESENTATION_CONFLICT"
                note = "El SKU coincide, pero hay una discrepancia de presentación."
            else:
                api_gtin = _gtin(selected["gtin"])
                listing_gtin = _gtin(ml_gtin)
                if ml_gtin and not listing_gtin:
                    kind = "INVALID_ML_GTIN"
                    note = "GTIN ML inválido o no verificable; no concluir identidad."
                elif selected["gtin"] and not api_gtin:
                    kind = "INVALID_ECOMM_GTIN"
                    note = "GTIN Ecomm inválido o no verificable; no concluir identidad."
                elif api_gtin and listing_gtin and api_gtin != listing_gtin:
                    kind = "GTIN_CONFLICT"
                    note = "El SKU coincide, pero el GTIN es distinto; investigar packs/componentes."
                elif api_gtin and listing_gtin and len(gtin_owners[api_gtin]) > 1:
                    kind = "SHARED_GTIN"
                    note = "GTIN compartido entre IDs API; confirmar presentación real."
                elif api_gtin and listing_gtin and api_gtin == listing_gtin:
                    kind = "SKU_GTIN_AGREE_REVIEW"
                    note = "SKU y GTIN coinciden; todavía requiere verificación comercial."
                else:
                    kind = "SKU_ONLY_REVIEW"
                    note = "Solo coincide el SKU de variante. No se comprobó un GTIN válido en ambos."

        counts[kind] += 1
        if len(examples[kind]) < MAX_EXAMPLES_PER_STATUS:
            examples[kind].append({
                "status": kind, "mla": external_id, "ml_title": title[:160],
                "ml_variant_sku": listing_sku or None,
                "ml_product_sku": product_sku or None,
                "ml_gtin": ml_gtin or None,
                "api_ecomm_id": selected["ecomm_id"] if selected else None,
                "api_sku": selected["sku"] if selected else None,
                "api_name": selected["name"] if selected else None,
                "api_is_combo": selected["is_combo"] if selected else None,
                "api_gtin": selected["gtin"] if selected else None,
                "reason": note,
            })

    repeated = sum(len(ids) > 1 for ids in results_by_id.values())
    return {
        "mode": "API_ONLY_ML_READ_ONLY_PREVIEW",
        "ecomm_source": "ECOMM_APP_API_STAGE",
        "mercadolibre_source": "MERCADOLIBRE_API",
        "external_writes_enabled": False,
        "operational_reconciliation_activated": False,
        "historical_decisions_applied": False,
        "summary": {
            "api_variants": len(api_ids),
            "ml_api_rows": len(ml_rows),
            "unique_api_sku": sum(len(value) == 1 for value in by_sku.values()),
            "ambiguous_api_skus": sum(len(value) > 1 for value in by_sku.values()),
            "api_variants_with_multiple_ml_rows_by_sku": repeated,
            **{kind: counts[kind] for kind in (
                "SKU_GTIN_AGREE_REVIEW", "SKU_ONLY_REVIEW", "SHARED_GTIN",
                "GTIN_CONFLICT", "PRESENTATION_CONFLICT", "INVALID_ML_GTIN",
                "INVALID_ECOMM_GTIN", "DUPLICATE_API_SKU", "SKU_NOT_IN_API",
                "NO_EXPLICIT_VARIANT_SKU", "PRODUCT_SKU_ONLY",
            )},
        },
        "examples": dict(examples),
        "warning": (
            "Diagnóstico entre dos copias por API, NO datos en tiempo real. "
            "No se leyó Excel, no se aplicaron decisiones anteriores y no se "
            "creó reconciliación operativa. Coincidir por SKU/GTIN no confirma "
            "por sí solo publicación, variante ni composición de combos. "
            "Se requiere verificar frescura, precios y vínculos antes de operar."
        ),
    }
