"""Quality flags derive codes from the API, not Ecomm spreadsheets."""
from types import SimpleNamespace

from app.services.ecomm_catalog_quality import identity_index, flags


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


def test_only_api_barcodes_are_used_for_quality():
    pages = api_page()
    variants = pages[0]["items"][0]["variants"]
    variants[0]["barcode"] = "7793396000039"
    variants[1]["barcode"] = "7793396000039"
    variants[2]["barcode"] = "3"
    index = identity_index(pages)
    rows = [
        flags({
            "ecomm_id": row["id"], "sku": row["sku"],
            "gtin_raw": None, "barcode": row["barcode"],
        }, None, index)
        for row in variants
    ]
    assert "ean_missing" not in rows[0] and "ean_missing" not in rows[1]
    assert "ean_repeated" in rows[0] and "ean_repeated" in rows[1]
    assert "ean_repeated" not in rows[2]
    assert "short_description_missing" not in rows[0]
    assert "commercial_incomplete" not in rows[0]


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


def test_historical_export_is_not_an_argument_to_quality():
    pages = api_page()
    index = identity_index(pages)
    assert all(
        "ean_missing" in flags(
            {"ecomm_id": row["id"], "sku": row["sku"], "barcode": None,
             "gtin_raw": None}, None, index,
        )
        for row in pages[0]["items"][0]["variants"]
    )


def test_source_quality_measures_real_api_fields_not_editorial_overlay():
    pages = api_page()
    index = identity_index(pages)
    source = {
        "ecomm_id": "101", "sku": "A-1", "gtin_raw": None, "barcode": None,
        "product_name": "Producto con nombre completo y detallado",
        "variant_description": "Presentación larga con suficientes caracteres",
    }
    complete = flags(source, None, index)
    assert "source_title_missing" not in complete
    assert "source_variant_missing" not in complete
    assert "source_title_short" not in complete
    assert "source_variant_short" not in complete
    assert "short_description_missing" not in complete

    title_short = flags({**source, "product_name": "Corto"}, None, index)
    assert "source_title_short" in title_short
    assert "source_variant_short" not in title_short

    variant_short = flags({**source, "variant_description": "50 g"}, None, index)
    assert "source_variant_short" in variant_short
    assert "source_title_short" not in variant_short

    absent = flags({**source, "product_name": None, "variant_description": ""}, None, index)
    assert "source_title_missing" in absent
    assert "source_variant_missing" in absent
    assert "source_title_short" not in absent
    assert "source_variant_short" not in absent


def test_source_quality_keeps_same_flags_when_editorial_fiche_is_started():
    pages = api_page()
    index = identity_index(pages)
    source = {
        "ecomm_id": "101", "sku": "A-1", "gtin_raw": None, "barcode": None,
        "product_name": "Producto breve",
        "variant_description": "750 g",
    }
    untouched = flags(source, None, index)
    started = flags(source, SimpleNamespace(fields={}), index)
    source_keys = {
        "source_title_short", "source_variant_short",
        "source_title_missing", "source_variant_missing",
    }
    assert set(untouched) & source_keys == set(started) & source_keys
    assert "commercial_incomplete" not in untouched
    assert "commercial_incomplete" in started
