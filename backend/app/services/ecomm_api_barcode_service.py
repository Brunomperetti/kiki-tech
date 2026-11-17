"""API-only barcode projections from a completed Ecomm-App capture.

Never read historic XLSX/CSV records. A valid check digit is an identifier
quality signal, not an approval of manufacturer, product identity or claims.
"""
from collections import Counter

from .ecomm_api_product_workspace_service import (
    EcommApiProductWorkspace, _gtin_check_digit_valid,
)


def _value(raw):
    if raw is None or isinstance(raw, bool):
        return ""
    return str(raw).strip()


def _rows(pages):
    result = []
    seen = set()
    for page in pages:
        for parent in page.get("items") or []:
            if not isinstance(parent, dict):
                continue
            for variant in parent.get("variants") or []:
                if not isinstance(variant, dict) or variant.get("invalid"):
                    continue
                ident = _value(variant.get("id"))
                if not ident or ident in seen:
                    raise ValueError("Ecomm ID ausente o repetido en la captura API.")
                seen.add(ident)
                barcode = _value(variant.get("barcode"))
                gtin = _value(variant.get("gtin"))
                result.append({
                    "ecomm_id": ident,
                    "sku": _value(variant.get("sku")),
                    "name": _value(parent.get("description")),
                    "presentation": _value(
                        variant.get("variant_description") or variant.get("description")
                    ),
                    "barcode": barcode,
                    "gtin": gtin,
                    "code": barcode or gtin,
                    "combo": variant.get("is_combo") is True or parent.get("is_combo") is True,
                    "conflict": bool(barcode and gtin and barcode != gtin),
                    "captured_at": page.get("captured_at"),
                })
    return result


def _state(row, counts):
    code = row["code"]
    if row["conflict"]:
        return "API_BARCODE_GTIN_CONFLICT"
    if not code:
        return "API_CODE_MISSING"
    if not _gtin_check_digit_valid(code):
        return "API_CODE_INVALID"
    if counts[code] > 1:
        return "API_CODE_REPEATED"
    if row["combo"]:
        return "API_PACK_REVIEW"
    return "API_UNIQUE_CODE"


def api_candidates_for_pages(pages):
    """Eligible lookup *hints*, always derived from the API, never certified."""
    rows = _rows(pages)
    counts = Counter(row["code"] for row in rows if row["code"])
    sku_owners = Counter(row["sku"].casefold() for row in rows if row["sku"])
    return {
        row["ecomm_id"]: row["code"]
        for row in rows
        if row["sku"]
        and sku_owners[row["sku"].casefold()] == 1
        and _state(row, counts) == "API_UNIQUE_CODE"
    }


def api_summary(db):
    pages = EcommApiProductWorkspace(db)._source_pages()
    rows = _rows(pages)
    codes = Counter(row["code"] for row in rows if row["code"])
    states = Counter(_state(row, codes) for row in rows)
    return {
        "source": "ECOMM_APP_API_STAGE",
        "mode": "API_CAPTURE_READ_ONLY",
        "total_variants": len(rows),
        "barcode_present": sum(bool(row["barcode"]) for row in rows),
        "gtin_present": sum(bool(row["gtin"]) for row in rows),
        "without_api_code": states["API_CODE_MISSING"],
        "unique_non_pack_valid": states["API_UNIQUE_CODE"],
        "repeated": states["API_CODE_REPEATED"],
        "invalid": states["API_CODE_INVALID"],
        "pack_review": states["API_PACK_REVIEW"],
        "conflicts": states["API_BARCODE_GTIN_CONFLICT"],
        "source_captured_at": pages[-1].get("captured_at") if pages else None,
        "external_writes_enabled": False,
        "note": (
            "Datos exclusivos de la captura API de Ecomm-App. No se consulta "
            "ningún Excel ni CSV de Ecomm-App. Los códigos no quedan certificados "
            "por el fabricante, y no se publica nada automáticamente."
        ),
    }


def api_evidence(db, ecomm_id):
    pages = EcommApiProductWorkspace(db)._source_pages()
    rows = _rows(pages)
    found = next((row for row in rows if row["ecomm_id"] == str(ecomm_id)), None)
    if found is None:
        raise ValueError("La variante no está en la captura API completa.")
    counts = Counter(row["code"] for row in rows if row["code"])
    return {
        **found,
        "source": "ECOMM_APP_API_STAGE",
        "state": _state(found, counts),
        "mode": "API_CAPTURE_READ_ONLY",
        "manufacturer_verified": False,
        "external_writes_enabled": False,
    }
