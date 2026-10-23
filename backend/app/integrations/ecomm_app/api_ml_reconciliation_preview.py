"""Conservative read-only diagnostic: Ecomm API variants vs Mercado Libre API listings.

No historical Excel, mutations, operational reconciliation runs or decisions.
ML simple listings have product-level SKU; variations need a variation SKU.
Exact SKU and matching GTIN are still EVIDENCE, not validated channel linkage.
"""
from collections import Counter, defaultdict
import re
import unicodedata

from ...services.tiendanube_assisted_match_service import pack_units, variant_conflict
from ...services.tiendanube_quality_audit_service import gtin_status
from .catalog_stage import stage_status

MAX_EXAMPLES_PER_STATUS = 6

STATUSES = (
    "SKU_GTIN_AGREE_REVIEW",
    "SKU_ONLY_REVIEW",
    "PRODUCT_SKU_ONLY",
    "SHARED_GTIN",
    "GTIN_CONFLICT",
    "PRESENTATION_CONFLICT",
    "PACK_QUANTITY_EQUIVALENCE_REVIEW",
    "INVALID_ML_GTIN",
    "INVALID_ECOMM_GTIN",
    "DUPLICATE_API_SKU",
    "SKU_NOT_IN_API",
    "NO_EXPLICIT_VARIANT_SKU",
    "NO_ML_SKU",
)


def _string(value):
    return str(value).strip() if value is not None else ""


def _sku(value):
    # Only case/outer whitespace normalization. Never infer SKU families,
    # strip punctuation, or use prefixes to connect separate variants.
    return _string(value).casefold()


def _gtin(value):
    code = _string(value)
    return code if gtin_status(code) == "VALID_CHECK_DIGIT" else ""


def _product_sku(row):
    return _string(
        row.get("sku_product") or row.get("sku_effective") or row.get("sku")
    )


# Conservative: arithmetic agreement can EXPLAIN a unit/total discrepancy,
# but never establish product identity, GTIN, combo components or approval.
_GENERIC_WORDS = {
    "pack", "kit", "combo", "un", "und", "unidad", "unidades",
    "con", "sin", "los", "las", "una", "uno", "para", "de", "del",
    "en", "por", "las", "sabor", "sabores", "capsula", "capsulas",
    "comprimidos", "tabletas", "caps", "cap", "gramos", "gramo",
    "frascos", "frasco", "suplemento", "suplementos", "producto",
    "polvo", "bebible", "natier", "vitamin", "way",
    "vitamina", "vitaminas", "geonat",
}


def _pack_multiplier(name):
    normalized = unicodedata.normalize("NFKD", _string(name)).encode(
        "ascii", "ignore"
    ).decode().lower()
    matches = {
        int(value)
        for value in re.findall(
            r"\b(?:pack|kit|combo)\s*(?:x\s*)?(\d{1,3})\b", normalized
        )
    }
    return next(iter(matches)) if len(matches) == 1 else None


def _distinctive_words(name):
    normalized = unicodedata.normalize("NFKD", _string(name)).encode(
        "ascii", "ignore"
    ).decode().lower()
    return {
        word for word in re.findall(r"\b[a-z][a-z0-9]*\b", normalized)
        if len(word) >= 3 and word not in _GENERIC_WORDS
    }


def _pack_equivalence_reason(ecomm_title, ml_title):
    """Only a review lead when a documented pack has an arithmetical explanation.

    Conservatively require at least two shared distinctive product words;
    otherwise a different ingredient with the same pack size stays a conflict.
    """
    ec_pack = _pack_multiplier(ecomm_title)
    ml_pack = _pack_multiplier(ml_title)
    if not ec_pack or ec_pack < 2 or ec_pack != ml_pack:
        return None
    ec_amounts = pack_units(ecomm_title)
    ml_amounts = pack_units(ml_title)
    if len(ec_amounts) != 1 or len(ml_amounts) != 1:
        return None
    (ec_amount, ec_unit), = ec_amounts
    (ml_amount, ml_unit), = ml_amounts
    if ec_unit != ml_unit or ec_amount == ml_amount:
        return None
    smaller, larger = sorted((ec_amount, ml_amount))
    if larger != smaller * ec_pack:
        return None
    shared_words = _distinctive_words(ecomm_title) & _distinctive_words(ml_title)
    if len(shared_words) < 2:
        return None
    return (
        f"Posible equivalencia entre {ec_pack} unidades de {smaller} "
        f"{ec_unit} y un total de {larger} {ec_unit}. "
        "Los títulos mantienen diferencias; revisar manualmente producto, "
        "presentación y componentes antes de cualquier vínculo."
    )


def api_ml_reconciliation_preview(
    pages: list[dict] | None,
    ml_rows: list[dict] | None,
    *,
    cases_page: int | None = None,
    cases_limit: int = 20,
    cases_status: str = "",
    cases_query: str = "",
):
    """One classifier for summary and searchable read-only review."""
    if cases_page is not None:
        if not isinstance(cases_page, int) or cases_page < 1 or cases_page > 100000:
            raise ValueError("La página de casos no es válida.")
        if not isinstance(cases_limit, int) or cases_limit < 1 or cases_limit > 50:
            raise ValueError("El límite de casos debe estar entre 1 y 50.")
        if cases_status and cases_status not in STATUSES:
            raise ValueError("El filtro de estado de casos no es válido.")
        if len(cases_query) > 80:
            raise ValueError("La búsqueda admite hasta 80 caracteres.")
    search_text = _sku(cases_query)
    case_hits = []

    state = stage_status(pages)
    quality = state["quality"]
    blocking = (
        "parents_without_variants", "invalid_variants",
        "without_variant_id", "without_sku", "duplicate_variant_ids",
    )
    if (
        not state["complete"]
        or quality["parents"] != state["expected_parents"]
        or any(quality.get(field, 0) for field in blocking)
    ):
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
            if not isinstance(parent, dict):
                raise ValueError("La copia Ecomm API tiene datos incompletos.")
            for variant in parent.get("variants") or []:
                if not isinstance(variant, dict) or variant.get("invalid"):
                    raise ValueError("La copia Ecomm API tiene variantes inválidas.")
                ecomm_id = _string(variant.get("id"))
                sku = _string(variant.get("sku"))
                if not ecomm_id or not sku:
                    raise ValueError("La copia Ecomm API contiene una variante sin ID/SKU.")
                candidate = {
                    "ecomm_id": ecomm_id,
                    "sku": sku,
                    "name": _string(parent.get("description")),
                    "variant_description": _string(
                        variant.get("variant_description") or variant.get("description")
                    ),
                    "is_combo": variant.get("is_combo"),
                    "gtin": _string(variant.get("gtin") or variant.get("barcode")),
                }
                api_ids.add(ecomm_id)
                by_sku[_sku(sku)].append(candidate)
                valid = _gtin(candidate["gtin"])
                if valid:
                    gtin_owners[valid].add(ecomm_id)

    counts = Counter()
    examples = defaultdict(list)
    results_by_id = defaultdict(set)
    identity_counts = Counter()
    for ml in ml_rows:
        if not isinstance(ml, dict):
            raise ValueError("Hay registros ML API que no son objetos válidos.")
        external_id = _string(ml.get("external_id"))
        explicit_variant = _string(ml.get("variant_sku"))
        general_sku = _product_sku(ml)
        ml_gtin = _string(ml.get("ean"))
        title = _string(ml.get("title"))

        # The ML transformer creates "MLA...#variation_id" ONLY when a real
        # variation exists. Product-level SKU from that record must NEVER be
        # assigned to a variation whose own SELLER_SKU is missing.
        has_variation = "#" in external_id
        if has_variation:
            identity_counts["ml_variation_rows"] += 1
        else:
            identity_counts["ml_simple_rows"] += 1

        if explicit_variant:
            lookup_sku = explicit_variant
            match_basis = "VARIANT_SKU"
            identity_counts["ml_rows_with_variant_sku"] += 1
        elif has_variation:
            lookup_sku = ""
            match_basis = "MISSING_VARIANT_SKU"
            identity_counts["ml_variations_without_variant_sku"] += 1
        else:
            lookup_sku = general_sku
            match_basis = "SIMPLE_PRODUCT_SKU"
            if general_sku:
                identity_counts["ml_simple_rows_with_product_sku"] += 1

        candidates = by_sku.get(_sku(lookup_sku), []) if lookup_sku else []
        selected = None
        note = ""
        if has_variation and not explicit_variant:
            kind = "NO_EXPLICIT_VARIANT_SKU"
            note = (
                "Publicación con variación ML sin SKU propio de variante. "
                "El SKU del producto madre, si existe, no la identifica."
            )
        elif not lookup_sku:
            kind = "NO_ML_SKU"
            note = "La publicación simple ML no informa SKU para comparar."
        elif len(candidates) > 1:
            kind = "DUPLICATE_API_SKU"
            note = "El SKU exacto apunta a varios IDs Ecomm; no se elige uno."
        elif not candidates:
            kind = "SKU_NOT_IN_API"
            note = "El SKU exacto ML no aparece en la copia API Ecomm."
        else:
            selected = candidates[0]
            identity_counts["exact_unique_sku_candidates"] += 1
            if match_basis == "SIMPLE_PRODUCT_SKU":
                identity_counts["exact_simple_product_sku_candidates"] += 1
            else:
                identity_counts["exact_variant_sku_candidates"] += 1
            results_by_id[selected["ecomm_id"]].add(external_id)
            full_name = " ".join((selected["name"], selected["variant_description"]))
            if variant_conflict(full_name, selected["sku"], title, lookup_sku):
                # Check the parent product name separately, avoiding duplicated
                # or unrelated variant-description quantities in the heuristic.
                pack_reason = _pack_equivalence_reason(selected["name"], title)
                if pack_reason:
                    kind = "PACK_QUANTITY_EQUIVALENCE_REVIEW"
                    note = pack_reason
                else:
                    kind = "PRESENTATION_CONFLICT"
                    note = (
                        "El SKU coincide pero hay una diferencia de presentación "
                        "sin explicación segura; verificar producto y pack."
                    )
            else:
                api_gtin = _gtin(selected["gtin"])
                listing_gtin = _gtin(ml_gtin)
                if ml_gtin and not listing_gtin:
                    kind = "INVALID_ML_GTIN"
                    note = "El GTIN de ML no es válido o comprobable."
                elif selected["gtin"] and not api_gtin:
                    kind = "INVALID_ECOMM_GTIN"
                    note = "El GTIN de Ecomm no es válido o comprobable."
                elif api_gtin and listing_gtin and api_gtin != listing_gtin:
                    kind = "GTIN_CONFLICT"
                    note = "SKU exacto pero GTIN válidos diferentes; verificar presentaciones."
                elif api_gtin and listing_gtin and len(gtin_owners[api_gtin]) > 1:
                    kind = "SHARED_GTIN"
                    note = "GTIN repetido entre IDs Ecomm; no inferir composición de combos."
                elif api_gtin and listing_gtin and api_gtin == listing_gtin:
                    kind = "SKU_GTIN_AGREE_REVIEW"
                    note = "SKU y GTIN coinciden; falta confirmar identidad comercial."
                elif match_basis == "SIMPLE_PRODUCT_SKU":
                    kind = "PRODUCT_SKU_ONLY"
                    note = (
                        "Publicación simple con SKU de producto exacto y único. "
                        "No hay corroboración suficiente de GTIN; revisar, no aprobar."
                    )
                else:
                    kind = "SKU_ONLY_REVIEW"
                    note = (
                        "Variante ML con SKU de variante exacto y único. "
                        "Sin corroboración suficiente de GTIN; revisar, no aprobar."
                    )

        counts[kind] += 1
        if cases_page is not None and (
            not cases_status or kind == cases_status
        ) and (not search_text or any(search_text in _sku(v) for v in (
            external_id, title, general_sku, explicit_variant,
            selected["ecomm_id"] if selected else "",
            selected["sku"] if selected else "",
            selected["name"] if selected else "",
        ))):
            case_hits.append({
                "status": kind,
                "mla": external_id,
                "ml_title": title[:160],
                "ml_variant_sku": explicit_variant or None,
                "ml_product_sku": general_sku or None,
                "ml_gtin": ml_gtin or None,
                "match_basis": match_basis,
                "api_ecomm_id": selected["ecomm_id"] if selected else None,
                "api_sku": selected["sku"] if selected else None,
                "api_name": selected["name"] if selected else None,
                "api_variant_description": (
                    selected["variant_description"] if selected else None
                ),
                "api_is_combo": selected["is_combo"] if selected else None,
                "api_gtin": selected["gtin"] if selected else None,
                "reason": note,
            })
        if len(examples[kind]) < MAX_EXAMPLES_PER_STATUS:
            examples[kind].append({
                "status": kind,
                "mla": external_id,
                "ml_title": title[:160],
                "ml_variant_sku": explicit_variant or None,
                "ml_product_sku": general_sku or None,
                "ml_gtin": ml_gtin or None,
                "match_basis": match_basis,
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
            **{name: identity_counts[name] for name in (
                "ml_simple_rows", "ml_variation_rows",
                "ml_rows_with_variant_sku", "ml_simple_rows_with_product_sku",
                "ml_variations_without_variant_sku", "exact_unique_sku_candidates",
                "exact_simple_product_sku_candidates", "exact_variant_sku_candidates",
            )},
            **{kind: counts[kind] for kind in STATUSES},
        },
        "examples": dict(examples),
        **({
            "cases": {
                "total": len(case_hits),
                "page": cases_page,
                "limit": cases_limit,
                "status": cases_status,
                "query": cases_query,
                "items": case_hits[
                    (cases_page - 1) * cases_limit:cases_page * cases_limit
                ],
            }
        } if cases_page is not None else {}),
        "warning": (
            "Diagnóstico entre dos snapshots API, NO datos en tiempo real. "
            "SKU de publicación simple se compara como pista; la variante exige "
            "SKU propio. Coincidencias exactas, incluso por GTIN, requieren "
            "verificación humana y no confirman vínculos de inventario. "
            "No se leyó Excel, no se aplicaron decisiones y no se creó "
            "reconciliación operativa ni publicaciones."
        ),
    }
