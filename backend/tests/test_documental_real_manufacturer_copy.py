"""Real-world source regression without any API, file, model or customer writes.

This is an *offline editorial acceptance sample*: source facts are candidates
from the public manufacturer website, not database APPROVED events. The
Research approval/identity gate must still run before any product is saved.
"""
from app.services.documental.proposals import Proposals


MANUFACTURER_URL = "https://naturalseed.com.ar/producto/mix-ensaladas-y-sopas/"
RETAILER_URL = (
    "https://newgarden.com.ar/"
    "mix-ensaladas-y-sopas-natural-seed-x-250-g-sin-tacc.html"
)


def item(ident, field, value):
    return {
        "id": ident,
        "field": field,
        "value": value,
        "unit": None,
        "source_url": MANUFACTURER_URL,
        "status": "CANDIDATE_NOT_APPROVED",
    }


def test_official_manufacturer_minimal_copy_never_adds_unsubstantiated_claims():
    candidates = [
        item("manufacturer-name", "product_name", "Mix Ensaladas y Sopas"),
        item("manufacturer-size", "presentation", "250 g"),
        item("manufacturer-characteristics", "characteristics",
             "3 frutos secos + 3 semillas al oreganato"),
    ]
    # This calls a pure formatter to test output constraints only. In the
    # real workflow, Proposals.context() must obtain APPROVED current facts
    # from Research before any draft generation can be persisted.
    content, missing = Proposals.generate_fields(candidates)
    assert content["title"]["value"] == "Mix Ensaladas y Sopas · 250 g"
    assert content["short_title"]["value"] == "Mix Ensaladas y Sopas · 250 g"
    assert content["description"]["evidence_ids"] == [
        "manufacturer-name", "manufacturer-size", "manufacturer-characteristics"
    ]
    assert "3 frutos secos + 3 semillas al oreganato" in content["description"]["value"]
    assert all("sin tacc" not in str(row).casefold() for row in content.values())
    assert all("gluten" not in str(row).casefold() for row in content.values())
    assert all("colesterol" not in str(row).casefold() for row in content.values())
    assert all("7798180790097" not in str(row) for row in content.values())
    assert "category" not in content and "subcategory" not in content
    assert "media" not in content and "seo_keywords" not in content
    assert any("sin evidencia aprobada" in reason for reason in missing)
    assert MANUFACTURER_URL.startswith("https://")
    assert RETAILER_URL.startswith("https://")
