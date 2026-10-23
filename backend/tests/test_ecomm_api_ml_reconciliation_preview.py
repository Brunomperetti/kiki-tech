"""Regression tests: product-level SKU on simple ML offers vs variation SKU."""
import pytest

from app.integrations.ecomm_app.api_ml_reconciliation_preview import (
    STATUSES, api_ml_reconciliation_preview,
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
        "sku_product": sku or variant_sku,
        "title": title, "ean": ean,
        "sku_source": "variant" if variant_sku else "product",
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
    assert all(row["match_basis"] == "VARIANT_SKU" for row in rows)
    assert report["historical_decisions_applied"] is False
    assert report["external_writes_enabled"] is False


def test_simple_ml_product_sku_matches_unique_api_variant_for_review():
    report = api_ml_reconciliation_preview(captured(), [
        listing("MLA3", None, "Magnesio con Potasio 30 cápsulas", sku="2500"),
    ])
    assert report["summary"]["PRODUCT_SKU_ONLY"] == 1
    assert report["summary"]["exact_simple_product_sku_candidates"] == 1
    row = report["examples"]["PRODUCT_SKU_ONLY"][0]
    assert row["api_ecomm_id"] == "1"
    assert row["match_basis"] == "SIMPLE_PRODUCT_SKU"
    assert report["operational_reconciliation_activated"] is False


def test_simple_ml_pack_is_its_own_id_not_the_base_unit():
    report = api_ml_reconciliation_preview(captured(), [
        listing("MLA100", title="Pack x2 Magnesio con Potasio 60 cápsulas",
                sku="2500400"),
        listing("MLA101", title="Magnesio con Potasio 30 cápsulas", sku="2500"),
    ])
    assert report["summary"]["PRODUCT_SKU_ONLY"] == 2
    assert {
        row["api_ecomm_id"] for row in report["examples"]["PRODUCT_SKU_ONLY"]
    } == {"1", "2"}


def test_variation_without_own_sku_cannot_borrow_parent_sku():
    report = api_ml_reconciliation_preview(captured(), [
        listing("MLA3#987", None, "Magnesio", sku="2500"),
    ])
    assert report["summary"]["NO_EXPLICIT_VARIANT_SKU"] == 1
    assert report["summary"]["exact_simple_product_sku_candidates"] == 0
    row = report["examples"]["NO_EXPLICIT_VARIANT_SKU"][0]
    assert row["api_ecomm_id"] is None
    assert row["match_basis"] == "MISSING_VARIANT_SKU"


def test_simple_listing_without_sku_is_separate_problem():
    report = api_ml_reconciliation_preview(captured(), [listing("MLA3")])
    assert report["summary"]["NO_ML_SKU"] == 1
    assert report["summary"]["NO_EXPLICIT_VARIANT_SKU"] == 0


def test_presentation_difference_blocks_even_with_exact_product_sku():
    report = api_ml_reconciliation_preview(captured(), [
        listing("MLA4", title="Pack x2 Magnesio 120 cápsulas", sku="2500400"),
    ])
    assert report["summary"]["PRESENTATION_CONFLICT"] == 1


def test_ambiguous_simple_sku_does_not_choose_an_id():
    pages = captured()
    pages[0]["items"][0]["variants"][0]["sku"] = "2500400"
    report = api_ml_reconciliation_preview(pages, [
        listing("MLA5", title="Pack x2 Magnesio 60 cápsulas", sku="2500400"),
    ])
    assert report["summary"]["DUPLICATE_API_SKU"] == 1
    assert report["examples"]["DUPLICATE_API_SKU"][0]["api_ecomm_id"] is None


def test_missing_or_partial_snapshots_fail_closed():
    with pytest.raises(ValueError, match="Ecomm API"):
        api_ml_reconciliation_preview([], [listing("MLA1", sku="2500")])
    pages = captured()
    pages[0]["total_pages"] = 2
    with pytest.raises(ValueError, match="Ecomm API"):
        api_ml_reconciliation_preview(pages, [listing("MLA1", sku="2500")])
    with pytest.raises(ValueError, match="Mercado Libre API"):
        api_ml_reconciliation_preview(captured(), [])


def test_api_gtin_discrepancy_flagged_not_resolved():
    report = api_ml_reconciliation_preview(captured(), [
        listing("MLA6", title="Chocolate 500 g", sku="5000",
                ean="7791234567896"),
    ])
    assert report["summary"]["INVALID_ML_GTIN"] == 1


def test_all_ml_rows_classified_once_without_data_writes():
    cases = [
        listing("MLA6", title="Magnesio con Potasio 30 cápsulas", sku="2500"),
        listing("MLA7#1", title="Magnesio con Potasio 30 cápsulas", sku="2500"),
        listing("MLA8#1", title="Magnesio"),
        listing("MLA9", title="Sin SKU"),
    ]
    report = api_ml_reconciliation_preview(captured(), cases)
    assert sum(report["summary"][key] for key in STATUSES) == len(cases)
    assert report["summary"]["ml_simple_rows"] == 2
    assert report["summary"]["ml_variation_rows"] == 2
    # The variation with a parent SKU but no variant SKU is intentionally NOT matched.
    assert report["summary"]["exact_unique_sku_candidates"] == 1
    assert report["summary"]["NO_EXPLICIT_VARIANT_SKU"] == 2
    assert report["historical_decisions_applied"] is False


def test_pack_unit_total_arithmetic_is_a_review_not_an_approval():
    pages = captured()
    parent = pages[0]["items"][1]
    parent["description"] = "Pack X12 Magnesio Con Potasio Vitamin Way 360 Capsulas"
    parent["variants"][0]["description"] = "360 Capsulas"
    result = api_ml_reconciliation_preview(pages, [
        listing(
            "MLA500", sku="2500400",
            title="Pack X12 Magnesio Con Potasio Vitamin Way X 30 Capsulas",
        ),
    ])
    assert result["summary"]["PACK_QUANTITY_EQUIVALENCE_REVIEW"] == 1
    row = result["examples"]["PACK_QUANTITY_EQUIVALENCE_REVIEW"][0]
    assert row["api_ecomm_id"] == "2"
    assert "360" in row["reason"] and "30" in row["reason"]
    assert result["external_writes_enabled"] is False
    assert result["operational_reconciliation_activated"] is False


def test_same_pack_arithmetic_but_different_ingredient_remains_conflict():
    pages = captured()
    parent = pages[0]["items"][1]
    parent["description"] = "Pack X3 Vinagre Sidra De Manzana Natier 150 Capsulas"
    result = api_ml_reconciliation_preview(pages, [
        listing(
            "MLA501", sku="2500400",
            title="Suplemento Vitamina B12 Vegana Natier 50 Capsulas Pack X3",
        ),
    ])
    assert result["summary"]["PRESENTATION_CONFLICT"] == 1
    assert result["summary"]["PACK_QUANTITY_EQUIVALENCE_REVIEW"] == 0


def test_pack_unit_total_with_different_pack_multipliers_still_conflicts():
    pages = captured()
    pages[0]["items"][1]["description"] = (
        "Pack X12 Magnesio Con Potasio Vitamin Way 360 Capsulas"
    )
    result = api_ml_reconciliation_preview(pages, [
        listing(
            "MLA502", sku="2500400",
            title="Pack X4 Magnesio Con Potasio Vitamin Way 30 Capsulas",
        ),
    ])
    assert result["summary"]["PRESENTATION_CONFLICT"] == 1
    assert result["summary"]["PACK_QUANTITY_EQUIVALENCE_REVIEW"] == 0
