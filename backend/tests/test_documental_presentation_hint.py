"""Public catalogue naming differences are research hints, not approvals."""
import pytest

from app.services.documental.presentation_hint import candidate
from app.services.documental.research import identity_digest, Research


def origin(**changes):
    return {
        "product_name": "Mix Semillas P/ Ensaladas Sopas Natural Seed X 250gr",
        "variant_description": "Mix Semillas P/ Ensaladas Sopas Natural Seed X 250gr",
        "is_combo": False,
        "parent_is_combo": False,
        **changes,
    }


def test_naturalseed_api_source_can_suggest_250g_without_rewriting_raw_identity():
    src = origin()
    original = dict(src)
    assert candidate(src) == "250 g"
    assert src == original  # no normalization of source fields


@pytest.mark.parametrize("change", [
    {"is_combo": True},
    {"parent_is_combo": True},
    {"is_combo": None},
    {"variant_description": "Pack x2 Mix x 250gr"},
    {"variant_description": "Mix 250 g + 100 g"},
    {"variant_description": "Caja x 6 Mix 250 g"},
    {"variant_description": "Sin presentación"},
    {"variant_description": "Mix 250 grs y otra presentación 500 ml"},
])
def test_packs_ambiguity_and_unknown_sale_type_are_not_inferred(change):
    src = {**origin(), **change}
    assert candidate(src) is None


def test_display_only_hint_cannot_change_documental_identity_fingerprint():
    reference = {
        "ecomm_id": "7518949",
        "name": "Mix Semillas P/ Ensaladas Sopas Natural Seed X 250gr",
        "presentation": "Mix Semillas P/ Ensaladas Sopas Natural Seed X 250gr",
        "sku": "9995",
        "is_combo": False,
        "editorial_presentation": None,
    }
    original = identity_digest(reference)
    with_hint = {
        **reference,
        "presentation_lookup_hint": "250 g",
        "provenance": {"presentation_lookup_hint": "solo pista"},
    }
    assert identity_digest(with_hint) == original
    manufacturer = {
        "identity": {
            "name": "Mix Ensaladas y Sopas",
            "presentation": "250 g",
            "ean": None,
            "is_combo": None,
        },
        "associated_ecomm_id": "7518949",
    }
    blockers = Research.identity_issues(with_hint, manufacturer)
    assert any("Nombre" in item for item in blockers)
    assert any("Presentación" in item for item in blockers)
    assert with_hint["presentation"] == reference["presentation"]
