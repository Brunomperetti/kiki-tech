from app.services.tiendanube_seo_guideline_audit import audit_seo_fields


def test_seo_guide_recommendations_are_advisory_not_hard_limits():
    result = audit_seo_fields(
        product_name="Jabón Vegetal 100 g",
        seo_title="Jabón" * 15,
        meta_description="a" * 151,
        description="Jabón vegetal verificado.",
        alt_text="a" * 61,
    )
    assert result["status"] == "ADVISORY_ONLY"
    assert {x["field"] for x in result["alerts"]} == {
        "seo_title", "meta_description", "description", "alt_text"
    }
    assert result["description_words"] == 3


def test_missing_fields_are_requested_not_fabricated():
    result = audit_seo_fields(product_name="Avena 500 g")
    assert result["alerts"] == []
    assert "description" in result["missing"]
    assert "seo_title" in result["missing"]
    assert "product_name" not in result["missing"]
    assert result["description_words"] == 0


def test_complete_fields_in_guide_ranges_have_no_alerts():
    result = audit_seo_fields(
        product_name="Avena Granix 500 g", seo_title="Avena Granix 500 g",
        meta_description="Avena Granix 500 g.", alt_text="Paquete de avena Granix",
        description=" ".join(["producto"] * 120),
    )
    assert result["alerts"] == []
    assert result["missing"] == []
