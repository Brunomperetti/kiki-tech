"""Evidence-locked AI copy tests: no network, no paid requests or real data."""
import json
from unittest.mock import patch
from urllib.error import HTTPError
import pytest
from app.services.documental.evidence_ai import (
    validate, tokens, COPY_FIELDS, EvidenceAIError, call_openai,
    validate_partial,
)


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


def test_partial_model_response_keeps_only_evidence_supported_copy():
    facts = approved()
    title = selection(
        "title", "Mix Ensaladas y Sopas de 250 g",
        facts[0]["id"], facts[1]["id"],
    )
    title["description"] = {
        "text": "Saludable Mix de 250 g para deportistas",
        "evidence_ids": [facts[0]["id"], facts[1]["id"]],
    }
    good, bad = validate_partial(title, facts)
    assert list(good) == ["title"]
    assert bad == ["description"]
    assert good["title"]["evidence_ids"] == ["a" * 24, "b" * 24]


def test_model_response_without_supported_fields_fails_closed():
    with pytest.raises(EvidenceAIError) as exc:
        validate_partial(
            selection("title", "Cura cualquier enfermedad", "a" * 24),
            approved(),
        )
    assert exc.value.code == "REJECTED_EVIDENCE"


def test_provider_http_error_category_is_safe_and_specific():
    http_error = HTTPError(
        "https://api.openai.com/v1/chat/completions",
        401, "Unauthorized", None, None,
    )
    with patch("app.services.documental.evidence_ai.urlopen", side_effect=http_error):
        with pytest.raises(EvidenceAIError) as exc:
            call_openai(approved(), "test-model", "secret-not-in-error")
    assert exc.value.code == "OPENAI_HTTP_401"
    assert "HTTP 401" in str(exc.value)
    assert "secret-not-in-error" not in str(exc.value)


def test_provider_partial_success_reports_rejected_fields_without_new_facts():
    facts = approved()
    output = {
        "choices": [{"message": {"content": json.dumps({"fields": {
            "short_title": {
                "text": "Mix Ensaladas y Sopas",
                "evidence_ids": [facts[0]["id"]],
            },
            "description": {
                "text": "Mix saludable ideal para niños",
                "evidence_ids": [facts[0]["id"]],
            },
        }})}}],
        "usage": {"prompt_tokens": 144, "completion_tokens": 82},
    }

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self, _):
            return json.dumps(output).encode()

    with patch("app.services.documental.evidence_ai.urlopen", return_value=FakeResponse()):
        fields, usage = call_openai(facts, "test-model", "synthetic-key")
    assert list(fields) == ["short_title"]
    assert usage["rejected_fields"] == ["description"]
    assert usage["completion_tokens"] == 82
