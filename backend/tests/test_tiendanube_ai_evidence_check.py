from app.services.tiendanube_ai_evidence_check import audit_generated_copy


def test_warning_for_unsupported_numbers_and_benefits():
    facts = [{"field": "name", "value": "Avena 500 g"},
             {"field": "brand", "value": "Granix"}]
    result = audit_generated_copy("Granix Avena 500 g", "Aporta 25 vitaminas y cura el cansancio", facts)
    assert "25" in result["unsupported_numbers"]
    assert "cura" in result["unsupported_terms"]
    assert result["needs_review"] is True
    assert result["warnings"]


def test_draft_with_original_words_does_not_claim_external_verification():
    facts = [{"field": "name", "value": "Avena Granix 500 g"}]
    result = audit_generated_copy("Avena Granix 500 g", "Avena de Granix 500 g", facts)
    assert result["unsupported_numbers"] == []
    assert result["unsupported_terms"] == []
    assert result["needs_review"] is False
    assert "no demuestra autenticidad" in result["policy"]


def test_empty_description_is_explicitly_flagged():
    result = audit_generated_copy("Crema 100 g", "", [{"value": "Crema 100 g"}])
    assert result["needs_review"] is True
    assert any("Descripción pendiente" in warning for warning in result["warnings"])
