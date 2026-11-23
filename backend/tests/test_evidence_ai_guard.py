"""Evidence-locked AI copy tests: no network, no paid requests or real data."""
import pytest
from app.services.documental.evidence_ai import validate, tokens, COPY_FIELDS


def approved():
    return [
        {
            "id": "a" * 24, "state": "APPROVED", "verified": True,
            "field": "product_name", "value": "Mix Ensaladas y Sopas",
            "unit": None, "document_id": "local-" + "a" * 32,
            "document_version": 3, "quote": "Mix Ensaladas y Sopas",
        },
        {
            "id": "b" * 24, "state": "APPROVED", "verified": True,
            "field": "presentation", "value": "250 g",
            "unit": None, "document_id": "local-" + "a" * 32,
            "document_version": 3, "quote": "250 g",
        },
        {
            "id": "c" * 24, "state": "APPROVED", "verified": True,
            "field": "characteristics", "value": "3 frutos secos + 3 semillas al oreganato",
            "unit": None, "document_id": "local-" + "a" * 32,
            "document_version": 3, "quote": "3 frutos secos + 3 semillas al oreganato",
        },
    ]


def selection(key, text, *ids):
    return {key: {"text": text, "evidence_ids": list(ids)}}


def test_valid_ai_copy_has_true_citations_and_is_never_editor_write():
    f = approved()
    result = validate(
        selection("title", "Mix Ensaladas y Sopas de 250 g", f[0]["id"], f[1]["id"]), f
    )
    assert result["title"]["value"] == "Mix Ensaladas y Sopas de 250 g"
    assert result["title"]["evidence_ids"] == ["a" * 24, "b" * 24]
    assert result["title"]["clauses"] == ["Mix Ensaladas y Sopas de 250 g"]
    assert "media" not in COPY_FIELDS


@pytest.mark.parametrize("key,text,ids", [
    ("title", "Mix Ensaladas y Sopas de 999 g", ["a" * 24, "b" * 24]),
    ("title", "Mix Ensaladas y Sopas cura enfermedades", ["a" * 24]),
    ("title", "Mix Ensaladas y Sopas de 250 g", ["a" * 24]),
    ("short_title", "Mix Ensaladas y Sopas", ["b" * 24]),
    ("description", "Saludable mix de 250 g", ["b" * 24]),
    ("media", "https://example.org/a.jpg", ["a" * 24]),
    ("manufacturer", "Natural Seed", ["a" * 24]),
])
def test_rejects_unsourced_fields_numbers_and_claims(key, text, ids):
    with pytest.raises(ValueError, match="IA documental"):
        validate(selection(key, text, *ids), approved())


def test_rejects_invalid_fact_state_missing_or_fake_citations():
    f = approved()
    with pytest.raises(ValueError, match="IA documental"):
        validate(selection("title", "Mix Ensaladas y Sopas", "z" * 24), f)
    with pytest.raises(ValueError, match="IA documental"):
        validate(selection("title", "Mix Ensaladas y Sopas"), f)
    f[0]["verified"] = False
    with pytest.raises(ValueError, match="IA documental"):
        validate(selection("title", "Mix Ensaladas y Sopas", "a" * 24), f)


def test_independent_resource_and_taxonomy_permissions_remain_unavailable():
    assert not {"category", "subcategory", "manufacturer", "brand",
                "proposed_gtin", "sources", "media"} & COPY_FIELDS
    assert tokens("Ensaladas y Sopas 250 g") == [
        "ensaladas", "y", "sopas", "250", "g"
    ]
