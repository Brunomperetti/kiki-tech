"""Regression for inert product pages wrapped in a page-level form."""
import base64

import pytest

from document_reader.parser import parse


def product_page(title="Spaghetti de Harina de Arroz", weight="500 g",
                 extra="", after="", before=""):
    return f"""<!doctype html><html><head><title>Catálogo</title></head>
    <body><form id="form1" method="post" action="https://example.invalid">
    <input type="hidden" value="EAN: 9999999999999"/>
    <nav><h2>Otro producto 200 g</h2></nav>
    <div class="container">
      {before}
      <h2>{title} <span>{weight}</span><a href="/back">volver</a></h2>
      <div class="row"><img src="local/product.jpg"/>
        <img src="local/nutrition.jpg" alt="Energía: 100 kcal"/></div>
      <div class="row"><div class="col-md-6">
        <p><strong>Pastas secas de harina de arroz con huevo</strong></p>
        <p>Ingredientes: Harina de arroz, agua, huevo y colorante: betacaroteno</p>
        <p><strong>Preparación:</strong><br>Verter en abundante agua.</p>
        {extra}
      </div></div>
    </div><footer><p>Ingredientes: FALSO</p></footer></form>
    {after}
    <div id="extension"><template><h2>Inyección 90 g</h2>
    <p>Ingredientes: FALSO</p></template></div></body></html>"""


def parsed(html):
    return parse(
        "fabricante.html", "text/html",
        base64.b64encode(html.encode()).decode(), web_snapshot=True,
    )


def test_page_form_h2_recovers_literal_candidates_without_network_or_ean():
    result = parsed(product_page(extra=(
        '<script>Ingredientes: FALSO</script>'
        '<p hidden>Ingredientes: FALSO</p>'
        '<form><p>Ingredientes: FALSO</p></form>'
        '<input value="Ingredientes: FALSO"/>'
    )))
    assert result["parse_status"] == "TEXT_EXTRACTED"
    assert result["identity"]["name"] == "Spaghetti de Harina de Arroz 500 g"
    assert result["identity"]["presentation"] == "500 g"
    assert result["identity"]["ean"] is None
    assert result["identity"]["is_combo"] is None
    assert result["identity"]["manufacturer"] is None
    claims = {claim["field"]: claim for claim in result["claims"]}
    assert set(claims) == {"product_name", "presentation", "ingredients"}
    assert claims["ingredients"]["value"] == (
        "Harina de arroz, agua, huevo y colorante: betacaroteno"
    )
    for claim in claims.values():
        assert claim["quote"] == result["sections"][claim["location"]]
        assert claim["value"] in claim["quote"]
    assert "FALSO" not in repr(result)
    assert "9999999999999" not in repr(result)
    assert "volver" not in repr(result)


@pytest.mark.parametrize("title,weight", [
    ("Pack de arroz", "500 g"),
    ("Arroz 2 x", "500 g"),
    ("Arroz 250 g", "500 g"),
    ("Arroz", ""),
])
def test_ambiguous_h2_identity_is_not_promoted(title, weight):
    result = parsed(product_page(title=title, weight=weight))
    assert result["identity"]["name"] is None
    assert result["identity"]["presentation"] is None


def test_multiple_headings_or_forms_do_not_rescue_identity():
    for html in (
        product_page(extra="<h2>Otro producto 500 g</h2>"),
        product_page(after="<form><p>Contacto</p></form>"),
        product_page(before="<h1>Otra identidad</h1>"),
    ):
        assert parsed(html)["identity"]["presentation"] is None


def test_conflicting_ingredient_candidates_remain_blocked():
    result = parsed(product_page(extra="<p>Ingredientes: Otro ingrediente</p>"))
    assert not any(c["field"] == "ingredients" for c in result["claims"])
    assert result["parser_blockers"]


def test_ingredients_outside_product_scope_are_not_claims():
    result = parsed(product_page(after=(
        '<div class="container"><p>Ingredientes: FALSO</p></div>'
    )))
    assert "FALSO" not in repr(result)
