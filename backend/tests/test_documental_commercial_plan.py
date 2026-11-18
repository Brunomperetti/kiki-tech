"""Evidence-backed commercial planning never invents content or writes channels.

Pure unit tests cover the decision tree and the minimal two-fact copy path.
All data are synthetic. No network, real product records, AI or provider writes.
"""
from types import SimpleNamespace

import pytest

from app.services.documental.commercial_plan import (
    commercial_plan, summarize_inspections, task_for,
)
from app.services.documental.proposals import Proposals


def fact(field, value, ident):
    return {
        "field": field,
        "value": value,
        "id": ident,
        "unit": None,
    }


def test_only_two_approved_identity_facts_generate_basic_commercial_copy():
    facts = [
        fact("product_name", "Producto Sintético de Ejemplo", "f1"),
        fact("presentation", "60 comprimidos", "f2"),
    ]
    fields, missing = Proposals.generate_fields(facts)
    for key in (
        "title", "short_title", "seo_title", "seo_keywords",
        "description", "short_description", "seo_description",
        "presentation",
    ):
        assert key in fields, key
        assert fields[key]["evidence_ids"]
    assert fields["description"]["value"] == (
        "Producto Sintético de Ejemplo · 60 comprimidos."
    )
    assert fields["short_description"]["value"] == fields["description"]["value"]
    assert fields["seo_description"]["value"] == fields["description"]["value"]
    assert "ingredients" not in fields
    assert "attributes" not in fields
    assert "details" not in fields
    assert "category" not in fields
    assert "subcategory" not in fields
    assert "media" not in fields
    assert "sources" not in fields
    assert "proposed_gtin" not in fields
    assert any("básica" in line for line in missing)
    # Arbitrary advertising/medical claims cannot be inserted.
    with pytest.raises(ValueError, match="sin respaldo"):
        Proposals.validate_edit(
            "description",
            "Elimina el cansancio y cura enfermedades.",
            fields["description"],
        )


def test_name_without_approved_presentation_cannot_generate_seo_or_description():
    fields, missing = Proposals.generate_fields([
        fact("product_name", "Ejemplo sin presentación", "one"),
    ])
    for key in ("title", "description", "seo_title", "seo_description"):
        assert key not in fields
    assert any("falta nombre o presentación" in text for text in missing)


def inspection(**overrides):
    base = {
        "conflicts": False, "no_documentation": False, "stale": False,
        "sufficient_evidence": True, "eligible": True,
        "approved_fact_count": 2,
        "supported_proposal_fields": ["title", "description", "seo_title"],
        "fields_without_support": ["category", "subcategory", "media"],
        "review_schedule": {"review_due": False},
        "name": "Producto de prueba", "presentation": "60 comprimidos",
        "reasons": [],
    }
    return {**base, **overrides}


@pytest.mark.parametrize("overrides,expected", [
    ({"conflicts": True, "no_documentation": True}, "REVIEW_IDENTITY"),
    ({"no_documentation": True}, "FIND_SOURCE"),
    ({"stale": True}, "REVALIDATE"),
    ({"sufficient_evidence": False}, "APPROVE_FACTS"),
    ({}, "GENERATE"),
    ({"eligible": False}, "REVIEW_EDITORIAL"),
])
def test_plan_classification_is_fail_closed_and_prioritizes_blockers(overrides, expected):
    assert task_for(inspection(**overrides)) == expected


def test_result_reports_exact_support_and_zero_writes():
    report = summarize_inspections([
        ("101", inspection()),
        ("102", inspection(no_documentation=True, approved_fact_count=0,
                           supported_proposal_fields=[], eligible=False)),
    ])
    assert report["total"] == 2
    assert report["counts"]["GENERATE"] == 1
    assert report["counts"]["FIND_SOURCE"] == 1
    assert report["items"][0]["human_review_required"] is True
    assert report["items"][0]["fields_supported"] == [
        "title", "description", "seo_title"
    ]
    assert report["external_writes_enabled"] is False
    assert report["facts_approved"] == 0
    assert report["automatic_publications"] == 0
    assert report["ai_requests"] == 0
    assert report["provider_calls"] == 0


def test_selection_limits_and_missing_api_variant_block_before_context():
    class ForbiddenContext:
        def __init__(self, *_args, **_kwargs):
            pytest.fail("Context must not be constructed for bad selection")

    def source_loader(_db):
        return {"101": {"sku": "SKU-A"}}

    for ids in ([], ["101", "101"], ["not-id"], [str(i) for i in range(1, 22)],
                ["101", "102"]):
        with pytest.raises(ValueError):
            commercial_plan(
                object(), SimpleNamespace(id=1), ids,
                source_loader=source_loader, context_type=ForbiddenContext,
            )


def test_success_is_read_only_and_releases_context():
    calls = []
    class SyntheticContext:
        def __init__(self, db, ids, source_map, byte_limit):
            assert ids == ["101"]
            assert "101" in source_map and byte_limit >= 65536
            calls.append("constructed")

        def inspect(self, db, session, ident):
            calls.append("inspected")
            return inspection()

        def release(self):
            calls.append("released")

    result = commercial_plan(
        object(), SimpleNamespace(id=1), ["101"],
        source_loader=lambda db: {"101": {"sku": "SKU-A"}},
        context_type=SyntheticContext,
    )
    assert result["counts"]["GENERATE"] == 1
    assert calls == ["constructed", "inspected", "released"]


def test_context_released_even_when_one_variant_inspection_fails():
    calls = []
    class FailingContext:
        def __init__(self, db, ids, source_map, byte_limit):
            pass

        def inspect(self, db, session, ident):
            raise ValueError("Evidencia revocada")

        def release(self):
            calls.append("released")

    with pytest.raises(ValueError, match="Evidencia"):
        commercial_plan(
            object(), SimpleNamespace(id=1), ["101"],
            source_loader=lambda db: {"101": {"sku": "SKU-A"}},
            context_type=FailingContext,
        )
    assert calls == ["released"]
