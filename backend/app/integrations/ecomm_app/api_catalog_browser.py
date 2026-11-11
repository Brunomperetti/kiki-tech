"""API-only, read-only catalog browser backed by the completed Ecomm-App stage.

The historical XLSX snapshot is NEVER read. This is a captured API copy, not
live stock and not an operational reconciliation or publishing source.
"""
from .catalog_stage import stage_status
import re


def valid_variant_id(value) -> bool:
    if type(value) is int:
        return value > 0 and len(str(value)) <= 120
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,120}", value):
        return False
    if value.casefold() in {"none", "null", "undefined", "nan", "inf", "infinity"}:
        return False
    if value.lstrip("-").isdigit():
        return value.isascii() and value.isdigit() and not value.startswith("0")
    return True


def api_variant_row(parent, variant, captured_at):
    ident = variant.get("id")
    if not valid_variant_id(ident):
        raise ValueError("La captura contiene un ID de variante inválido; no se sustituye por SKU.")
    barcode, gtin = variant.get("barcode"), variant.get("gtin")
    blockers = []
    if barcode and gtin and barcode != gtin:
        blockers.append("BARCODE_GTIN_CONFLICT")
    return {
        "ecomm_id": str(ident), "sku": variant.get("sku"),
        "product_name": parent.get("description"), "parent_code": parent.get("code"),
        "variant_description": variant.get("variant_description") or variant.get("description"),
        "is_combo": variant.get("is_combo"), "parent_is_combo": parent.get("is_combo"),
        # Keep the legacy combined value for existing clients, plus BOTH raw fields.
        "gtin": gtin or barcode, "gtin_raw": gtin, "barcode": barcode,
        "identity_blockers": blockers,
        "stock_at_capture": variant.get("total_stock"),
        "warehouses": variant.get("warehouses"), "captured_at": captured_at,
    }


def api_catalog_rows(pages: list[dict] | None, *, query: str = "",
                     page: int = 1, limit: int = 25) -> dict:
    status = stage_status(pages)
    if not status["complete"]:
        raise ValueError(
            "La copia API Ecomm-App no está completa. No se muestra un catálogo parcial."
        )
    if not 1 <= page <= 100000 or not 1 <= limit <= 50:
        raise ValueError("Paginación fuera de los límites permitidos.")
    term = query.strip().casefold()
    if len(term) > 80:
        raise ValueError("La búsqueda admite hasta 80 caracteres.")

    rows: list[dict] = []
    for snapshot_page in pages or []:
        captured_at = snapshot_page.get("captured_at")
        for parent in snapshot_page.get("items") or []:
            if not isinstance(parent, dict):
                continue
            for variant in parent.get("variants") or []:
                if not isinstance(variant, dict) or variant.get("invalid"):
                    continue
                row = api_variant_row(parent, variant, captured_at)
                if term and not any(
                    term in str(value or "").casefold()
                    for value in (
                        row["ecomm_id"], row["sku"], row["product_name"],
                        row["parent_code"], row["variant_description"], row["gtin"]
                    )
                ):
                    continue
                rows.append(row)
    total = len(rows)
    offset = (page - 1) * limit
    return {
        "mode": "API_CAPTURE_READ_ONLY",
        "source": status["source"],
        "operational_source_activated": False,
        "external_writes_enabled": False,
        "capture_first_at": (pages or [{}])[0].get("captured_at"),
        "capture_last_at": (pages or [{}])[-1].get("captured_at"),
        "total_variants_in_capture": status["quality"]["variants"],
        "quality": status["quality"],
        "query": query.strip(),
        "total_matches": total,
        "page": page,
        "page_size": limit,
        "items": rows[offset:offset + limit],
        "warning": (
            "Datos obtenidos SOLO de la copia Ecomm-App por API. "
            "El stock corresponde al momento de captura, NO está en vivo. "
            "La API inventario:leer no acredita precios, costos ni vínculos ML/TN. "
            "Todavía no se habilitó conciliación, decisiones ni publicación desde esta fuente."
        ),
    }
