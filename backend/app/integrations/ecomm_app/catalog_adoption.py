"""Safety-gated adoption plan for a FULL Ecomm-App inventory source cutover.

This is a read-only planning report, not an execution or approval API.
Matching a stable variant ID identifies a record; it does NOT validate current
stock, prices, channel links, GTIN, or production source readiness.
"""


def build_adoption_plan(comparison: dict, stage: dict) -> dict:
    totals = comparison["totals"]
    staged_complete = bool(stage["complete"])
    structural_problems = sum(
        stage["quality"].get(key, 0)
        for key in (
            "parents_without_variants", "invalid_variants", "without_variant_id",
            "without_sku", "without_total_stock", "duplicate_variant_ids",
        )
    )
    duplicate_historic = totals["duplicate_legacy_ids"]
    unmatched_historic = totals["historical_no_stable_id_match"]
    unmatched_api = totals["api_no_stable_id_match"]
    changed_sku = totals["same_id_different_sku"]

    tasks = [
        {
            "key": "SUBSTANTIVE_SKU",
            "title": "Verificar SKU que cambiaron de código",
            "count": changed_sku,
            "priority": "HIGH" if changed_sku else "DONE",
            "description": (
                "Conservan el ID Ecomm, pero el SKU cambió más allá de espacios "
                "y mayúsculas. Confirmar el código vigente antes de elegir qué "
                "SKU usar en KIKI y en los canales."
            ),
            "review": "Revisar los SKU realmente distintos en la comparación.",
        },
        {
            "key": "LEGACY_ONLY",
            "title": "Investigar productos históricos que no llegaron por API",
            "count": unmatched_historic,
            "priority": "HIGH" if unmatched_historic else "DONE",
            "description": (
                "No aparecen bajo el mismo ID. Consultar en Ecomm-App si siguen "
                "activos, cambiaron de ID o ya no forman parte del catálogo."
            ),
            "review": "Revisar el producto histórico sin ID coincidente.",
        },
        {
            "key": "API_ONLY",
            "title": "Clasificar variantes que solo figuran en la API",
            "count": unmatched_api,
            "priority": "REVIEW" if unmatched_api else "DONE",
            "description": (
                "No asumir que son productos nuevos ni duplicados. Investigar "
                "32/67 u otro desglose según is_combo real y comprobar su "
                "situación comercial antes de incorporarlos."
            ),
            "combo_yes": totals.get("api_only_combo_yes", 0),
            "combo_no": totals.get("api_only_combo_no", 0),
            "combo_unknown": totals.get("api_only_combo_unknown", 0),
            "review": "Investigar variantes que solo figuran en la API.",
        },
        {
            "key": "FORMAT_ONLY",
            "title": "Conservar alias de SKU que solo cambiaron de escritura",
            "count": totals["same_id_format_sku_changed"],
            "priority": "INFO",
            "description": (
                "El ID coincide, pero cambiaron espacios o mayúsculas. "
                "Registrar la equivalencia antes de modificar códigos en otros canales."
            ),
            "review": "Revisar diferencias de escritura.",
        },
    ]

    gates = [
        {
            "key": "STAGED_CATALOG",
            "title": "Copia completa aislada",
            "status": "PASS" if staged_complete else "BLOCKED",
            "reason": (
                "La copia API se completó y está aislada del catálogo operativo."
                if staged_complete else "No hay copia completa validada."
            ),
        },
        {
            "key": "IDENTIFIERS",
            "title": "Identificadores y datos básicos",
            "status": "PASS" if not structural_problems and not duplicate_historic else "BLOCKED",
            "reason": (
                "Sin anomalías estructurales detectadas en IDs, SKU y stock."
                if not structural_problems and not duplicate_historic else
                "Existen IDs duplicados o registros incompletos. Revisar antes de continuar."
            ),
        },
        {
            "key": "EXCEPTIONS",
            "title": "Resolver diferencias de identidad",
            "status": "PASS" if not (unmatched_historic or unmatched_api or changed_sku) else "BLOCKED",
            "reason": (
                "Todos los registros quedan reconocidos y no hay cambios importantes de SKU."
                if not (unmatched_historic or unmatched_api or changed_sku) else
                "Hay registros históricos o API sin coincidencia, o SKU cambiados pendientes de revisión."
            ),
        },
        {
            "key": "PRICING_AND_CHANNELS",
            "title": "Cobertura de precios y vínculos comerciales",
            "status": "PENDING",
            "reason": (
                "La API inventario:leer utilizada hasta ahora no acredita precios, "
                "costos ni relaciones con Mercado Libre/Tiendanube. "
                "Verificar una fuente complementaria antes de reemplazar el Excel."
            ),
        },
        {
            "key": "FRESHNESS_AND_ROLLBACK",
            "title": "Actualización periódica, corte consistente y reversión",
            "status": "PENDING",
            "reason": (
                "La copia se recorrió por páginas, no es un snapshot transaccional "
                "garantizado. Falta validar recargas, conciliación y plan de reversión."
            ),
        },
    ]
    # This is explicitly NEVER an automatic go-live permission.
    # The entire cutover must be designed and separately approved later.
    return {
        "mode": "PLANNING_ONLY",
        "activation_allowed": False,
        "operational_source": "ECOMM_APP",
        "comparison_source": "ECOMM_APP_API_STAGE",
        "mapped_by_stable_id": totals["matched_stable_ids"],
        "mapped_with_identical_sku": totals["same_id_same_sku"],
        "mapped_with_format_difference": totals["same_id_format_sku_changed"],
        "mapped_with_substantive_sku_change": changed_sku,
        "informational_stock_differences": totals["stock_differences_informational"],
        "first_stage_page_at": stage.get("first_page_at"),
        "last_stage_page_at": stage.get("last_page_at"),
        "tasks": tasks,
        "gates": gates,
        "note": (
            "Este informe no incorpora registros, no aprueba vínculos y no cambia "
            "inventario ni publicaciones. Coincidir por ID no valida SKU de canal, "
            "precio o stock actual. Ecomm-App API es por ahora solo una fuente "
            "de lectura en pruebas."
        ),
    }
