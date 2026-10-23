"""The preview must never rely on historical Excel or auto-approve matches."""
import pytest

from app.integrations.ecomm_app.api_ml_reconciliation_preview import (
    api_ml_reconciliation_preview,
)


def captured():
    return [{
        "total": 3, "total_pages": 1, "page": 1, "per_page": 50,
        "captured_at": "2026-10-23T12:00:00Z",
        "items": [
            {
                "code": "2500", "description": "Magnesio con Potasio 30 cápsulas",
                "variants": [{"id": 1, "sku": "2500", "is_combo": False,
                              "gtin": None, "total_stock": 2}],
            },
            {
                "code": "2500_m", "description": "Pack x2 Magnesio con Potasio 60 cápsulas",
                "variants": [{"id": 2, "sku": "2500400", "is_combo": True,
                              "gtin": None, "total_stock": 0}],
            },
            {
                "code": "5000", "description": "Chocolate 500 g",
                "variants": [{"id": 3, "sku": "5000", "is_combo": False,
                              "gtin": "7791234567895", "total_stock": 8}],
            },
        ],
    }]


def listing(external_id, variant_sku=None, title="Producto", ean=None, sku=None):
    return {
        "external_id": external_id, "variant_sku": variant_sku,
        "sku_effective": sku or variant_sku, "sku": sku or variant_sku,
        "title": title, "ean": ean,
    }


def test_exact_variant_sku_is_review_only_and_combo_remains_separate():
    report = api_ml_reconciliation_preview(captured(), [
        listing("MLA1#1", "2500400", "Pack x2 Magnesio con Potasio 60 cápsulas"),
        listing("MLA1#2", "2500", "Magnesio con Potasio 30 cápsulas"),
    ])
    assert report["summary"]["SKU_ONLY_REVIEW"] == 2
    rows = report["examples"]["SKU_ONLY_REVIEW"]
    assert {row["api_ecomm_id"] for row in rows} == {"1", "2"}
    assert {row["api_is_combo"] for row in rows} == {True, False}
    assert report["historical_decisions_applied"] is False
    assert report["external_writes_enabled"] is False


def test_parent_sku_cannot_auto_link_variant():
    report = api_ml_reconciliation_preview(captured(), [
        listing("MLA3", None, "Magnesio", sku="2500"),
    ])
    assert report["summary"]["PRODUCT_SKU_ONLY"] == 1
    assert report["examples"]["PRODUCT_SKU_ONLY"][0]["api_ecomm_id"] is None


def test_presentation_difference_blocks_even_with_exact_sku():
    report = api_ml_reconciliation_preview(captured(), [
        listing("MLA4", "2500400", "Pack x2 Magnesio 120 cápsulas"),
    ])
    assert report["summary"]["PRESENTATION_CONFLICT"] == 1


def test_ambiguous_sku_does_not_choose_an_id():
    pages = captured()
    pages[0]["items"][0]["variants"][0]["sku"] = "2500400"
    report = api_ml_reconciliation_preview(pages, [
        listing("MLA5", "2500400", "Pack x2 Magnesio 60 cápsulas"),
    ])
    assert report["summary"]["DUPLICATE_API_SKU"] == 1
    assert report["examples"]["DUPLICATE_API_SKU"][0]["api_ecomm_id"] is None


def test_missing_or_partial_snapshots_fail_closed():
    with pytest.raises(ValueError, match="Ecomm API"):
        api_ml_reconciliation_preview([], [listing("MLA1", "2500")])
    pages = captured()
    pages[0]["total_pages"] = 2
    with pytest.raises(ValueError, match="Ecomm API"):
        api_ml_reconciliation_preview(pages, [listing("MLA1", "2500")])
    with pytest.raises(ValueError, match="Mercado Libre API"):
        api_ml_reconciliation_preview(captured(), [])


def test_api_gtin_discrepancy_flagged_not_resolved():
    report = api_ml_reconciliation_preview(captured(), [
        listing("MLA6", "5000", "Chocolate 500 g", ean="7791234567896"),
    ])
    assert report["summary"]["INVALID_ML_GTIN"] == 1
