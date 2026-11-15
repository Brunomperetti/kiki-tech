"""Quality flags must combine the exact Ecomm ID export and actual editorial work."""
from types import SimpleNamespace

from app.services.ecomm_catalog_quality import identity_index, flags
from app.services.ecomm_gtin_export_service import export_quality_for_pages


def api_page():
    return [{
        "items": [{
            "description": "Producto del inventario Ecomm",
            "is_combo": False,
            "variants": [
                {"id": "101", "sku": "A-1", "variant_description": "Presentación A", "gtin": None, "barcode": None},
                {"id": "102", "sku": "A-2", "variant_description": "Presentación B", "gtin": None, "barcode": None},
                {"id": "103", "sku": "A-3", "variant_description": "Presentación C", "gtin": None, "barcode": None},
            ],
        }],
    }]


def test_excel_codes_are_used_for_quality_without_changing_api_fields():
    pages = api_page()
    snapshot = SimpleNamespace(payload=[{
        "version": 1, "variants": 3,
        "rows": [
            {"ecomm_id": "101", "sku": "A-1", "gtin": "7793396000039", "status": "VALID_REPEATED"},
            {"ecomm_id": "102", "sku": "A-2", "gtin": "7793396000039", "status": "VALID_REPEATED"},
            {"ecomm_id": "103", "sku": "A-3", "gtin": "3", "status": "INVALID"},
        ],
    }])
    evidence = export_quality_for_pages(pages, snapshot)
    assert evidence == {"101": "7793396000039", "102": "7793396000039", "103": ""}
    index = identity_index(pages, evidence)
    rows = [flags({"ecomm_id": ident, "sku": sku, "gtin_raw": None, "barcode": None}, None, index)
            for ident, sku in [("101", "A-1"), ("102", "A-2"), ("103", "A-3")]]
    assert "ean_missing" not in rows[0] and "ean_missing" not in rows[1]
    assert "ean_missing" in rows[2]
    assert "ean_repeated" in rows[0] and "ean_repeated" in rows[1]
    assert "ean_repeated" not in rows[2]
    assert "short_description_missing" not in rows[0]
    assert "commercial_incomplete" not in rows[0]
    assert pages[0]["items"][0]["variants"][0]["gtin"] is None


def test_started_editor_has_pendings_without_marking_untouched_products():
    pages = api_page()
    index = identity_index(pages)
    source = {"ecomm_id": "101", "sku": "A-1", "gtin_raw": None, "barcode": None}
    before = flags(source, None, index)
    started = flags(source, SimpleNamespace(fields={"title": ""}), index)
    assert "ean_missing" in before and "ean_missing" in started
    assert "commercial_title_missing" not in before
    assert "commercial_title_missing" in started
    assert "images_missing" not in before
    assert "images_missing" in started
    assert "commercial_incomplete" not in before
    assert "commercial_incomplete" in started


def test_mismatched_export_never_changes_quality():
    snapshot = SimpleNamespace(payload=[{
        "version": 1, "variants": 1,
        "rows": [{"ecomm_id": "101", "sku": "OLD", "gtin": "7793396000039"}],
    }])
    assert export_quality_for_pages(api_page(), snapshot) == {}
