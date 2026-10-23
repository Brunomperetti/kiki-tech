"""Read-only Tiendanube brand evidence for Ecomm variants lacking historical brand.

Exact *unique* SKU across BOTH historical Ecomm and TN is required, plus unique
stable variant ID in complete Ecomm API stage and non-divergent API SKU.
These are review leads, not confirmed manufacturer names or source updates.
"""
from collections import Counter, defaultdict

from sqlalchemy import select

from ...database.models import CatalogSnapshot
from .catalog_comparison import _format_key, _legacy_sku, _str
from .catalog_hybrid_preview import _indexes
from .catalog_stage import STAGE_SOURCE, stage_status
from .commercial_audit import _brand_class
from .tn_brand_secondary import diagnose_tn_brand_gaps

SAMPLE_LIMIT = 20


def _sku_key(value) -> str:
    # Only trim edges and fold case; whitespace *inside* a SKU can identify
    # distinct catalog records. Never remove punctuation or digits.
    return _str(value).casefold()


def brand_evidence_report(pages: list[dict], legacy: list[dict], tn: list[dict]) -> dict:
    state = stage_status(pages)
    if not state["complete"] or state["quality"]["parents"] != state["expected_parents"]:
        raise ValueError("La copia Ecomm-App API debe estar completa antes del cruce.")
    if not isinstance(legacy, list) or not legacy:
        raise ValueError("No hay inventario histórico Ecomm-App para comparar.")
    if not isinstance(tn, list) or not tn:
        return {
            "available": False, "mode": "REVIEW_ONLY_TN_BRAND_EVIDENCE",
            "activation_allowed": False,
            "summary": {},
            "candidates": [],
            "policy": "Falta un CSV de Tiendanube cargado. No se buscaron ni inventaron marcas.",
        }

    old_by_id, new_by_id = _indexes(pages, legacy)
    ecomm_by_sku = defaultdict(set)
    for old in legacy:
        if not isinstance(old, dict):
            continue
        key = _sku_key(_legacy_sku(old))
        if key:
            ecomm_by_sku[key].add(_str(old.get("ecomm_id")) or "SIN_ID")
    tn_by_sku = defaultdict(list)
    for item in tn:
        if not isinstance(item, dict):
            continue
        key = _sku_key(item.get("sku"))
        if key:
            tn_by_sku[key].append(item)

    counts = Counter()
    proposals = []
    for identifier in sorted(old_by_id):
        old_rows = old_by_id[identifier]
        api_rows = new_by_id.get(identifier, [])
        if len(old_rows) != 1 or len(api_rows) != 1:
            continue
        old, (_, variant) = old_rows[0], api_rows[0]
        if _brand_class(old.get("brand")) == "PRESENT":
            continue
        counts["missing_brand_unique_id"] += 1
        historical_sku = _legacy_sku(old)
        if not historical_sku:
            counts["without_historical_sku"] += 1
            continue
        sku = _sku_key(historical_sku)
        api_sku = _sku_key(variant.get("sku"))
        if not api_sku or _format_key(historical_sku) != _format_key(variant.get("sku")):
            counts["api_sku_changed"] += 1
            continue
        if len(ecomm_by_sku.get(sku, set())) != 1:
            counts["ambiguous_ecomm_sku"] += 1
            continue
        tn_rows = tn_by_sku.get(sku, [])
        if not tn_rows:
            counts["no_exact_tn_sku"] += 1
            continue
        if len(tn_rows) != 1:
            counts["ambiguous_tn_sku"] += 1
            continue
        tn_row = tn_rows[0]
        proposed = _str(tn_row.get("brand"))
        if _brand_class(proposed) != "PRESENT":
            counts["tn_brand_empty"] += 1
            continue
        counts["candidate_unique_exact_sku"] += 1
        is_combo = variant.get("is_combo") if isinstance(variant.get("is_combo"), bool) else None
        if is_combo:
            counts["combo_candidate"] += 1
        if len(proposals) < SAMPLE_LIMIT:
            proposals.append({
                "ecomm_id": identifier,
                "ecomm_sku": historical_sku,
                "api_sku": _str(variant.get("sku")),
                "ecomm_name": _str(old.get("name")),
                "tn_sku": _str(tn_row.get("sku")),
                "tn_name": _str(tn_row.get("name")),
                "tn_slug": _str(tn_row.get("slug")),
                "brand_from_tn": proposed,
                "is_combo": is_combo,
                "match_basis": "SINGLE_EXACT_SKU_IN_BOTH_SNAPSHOTS_PLUS_UNIQUE_ECOMM_ID",
                "review_status": "NEEDS_HUMAN_VERIFICATION",
                "note": (
                    "Marca copiada textualmente como evidencia desde Tiendanube; "
                    "no prueba marca fabricante ni autoriza cambiar Ecomm-App."
                ),
            })

    return {
        "available": True,
        "mode": "REVIEW_ONLY_TN_BRAND_EVIDENCE",
        "activation_allowed": False,
        "summary": {name: counts[name] for name in (
            "missing_brand_unique_id",
            "candidate_unique_exact_sku",
            "combo_candidate",
            "api_sku_changed",
            "without_historical_sku",
            "ambiguous_ecomm_sku",
            "ambiguous_tn_sku",
            "no_exact_tn_sku",
            "tn_brand_empty",
        )},
        "candidates": proposals,
        "sampling_limit": SAMPLE_LIMIT,
        "policy": (
            "Comparación limitada a SKU idéntico (solo mayúsculas/minúsculas) "
            "y único en Tiendanube y Ecomm-App, con ID de variante único en ambas fuentes "
            "y sin cambio sustancial del SKU API. Una coincidencia es evidencia interna "
            "para revisar, NO valida automáticamente la marca del fabricante. "
            "No se aplica ninguna marca, GTIN, precio, costo ni vinculación a canales."
        ),
    }


class EcommTnBrandEvidenceService:
    def __init__(self, db):
        self.db = db

    def report(self) -> dict:
        stage = self.db.scalar(
            select(CatalogSnapshot).where(CatalogSnapshot.source == STAGE_SOURCE)
        )
        old = self.db.scalar(
            select(CatalogSnapshot).where(CatalogSnapshot.source == "ECOMM_APP")
        )
        tn = self.db.scalar(
            select(CatalogSnapshot).where(CatalogSnapshot.source == "TIENDANUBE")
        )
        stage_rows = stage.payload if stage else []
        old_rows = old.payload if old else []
        tn_rows = tn.payload if tn else []
        result = brand_evidence_report(stage_rows, old_rows, tn_rows)
        if result["available"]:
            result["indirect_diagnostics"] = diagnose_tn_brand_gaps(
                stage_rows, old_rows, tn_rows
            )
        return result
