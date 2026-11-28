"""Actual editor limits: synthetic offline boundary cases, no provider calls."""

import pytest

from app.services.documental.seo_validation import field_limits, matches_documented_copy
from app.services.ecomm_api_product_workspace_service import ARRAY_LIMITS, TEXT_LIMITS


@pytest.mark.parametrize("field,maximum", list(TEXT_LIMITS.items()))
def test_text_boundaries_match_existing_editor(field, maximum):
    exact = field_limits(field, "á" * maximum)
    assert exact["valid"] and exact["length"] == maximum
    assert exact["maximum"] == maximum and exact["unit"] == "characters"
    assert not field_limits(field, "á" * (maximum + 1))["valid"]
    assert not field_limits(field, None)["valid"]


@pytest.mark.parametrize("field,maximum", list(ARRAY_LIMITS.items()))
def test_array_limits_match_editor(field, maximum):
    assert field_limits(field, [{}] * maximum)["valid"]
    assert not field_limits(field, [{}] * (maximum + 1))["valid"]
    assert not field_limits(field, [None])["valid"]


@pytest.mark.parametrize(
    "field,key,size",
    [
        ("attributes", "name", 90),
        ("attributes", "value", 450),
        ("media", "alt", 180),
        ("media", "url", 1000),
        ("sources", "name", 180),
        ("sources", "note", 500),
    ],
)
def test_nested_resource_and_attribute_limits(field, key, size):
    assert field_limits(field, [{key: "x" * size}])["valid"]
    assert not field_limits(field, [{key: "x" * (size + 1)}])["valid"]


def test_seo_presence_or_uncited_copy_does_not_prove_backing():
    assert not matches_documented_copy("seo_title", "Texto SEO", None)
    assert not matches_documented_copy(
        "seo_title", "Texto SEO", {"value": "Texto SEO", "evidence_ids": []}
    )
    proposed = {
        "value": "Producto · 250 g",
        "evidence_ids": ["synthetic-fact"],
        "clauses": ["Producto", "250 g"],
    }
    assert matches_documented_copy("seo_title", "Producto · 250 g", proposed)
    assert not matches_documented_copy(
        "seo_title", "Producto saludable sin gluten", proposed
    )
