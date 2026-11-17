"""An operator may archive *original* HTML, not submit fabricated citations.

The offline isolated reader identifies conservative name/size candidates from
HTML structures. It never runs scripts, follows resources, contacts websites
or approves a fact; the raw original is preserved by LocalDocuments.
"""
import base64

import pytest

from document_reader.parser import parse


URL = "https://naturalseed.com.ar/producto/mix-ensaladas-y-sopas/"


def saved_page(*, extra_rows="", extra_heads="", extra_html=""):
    return f"""<!doctype html><html lang="es">
    <head><title>Lo que no es el nombre de producto</title>
      <meta name="description" content="Sin TACC, dato NO verificado"/>
      <script>var text = "Nombre: PRODUCTO FALSO";</script>
      <style>.hidden{{ display: none; }}</style>
    </head>
    <body>
      <nav><h1>Otra marca de navegación</h1></nav>
      <section hidden><p>EAN: 9999999999999</p></section>
      <main>
        <h1 class="product_title entry-title"><span>Mix Ensaladas y Sopas</span></h1>
        {extra_heads}
        <div class="woocommerce-tabs">
          <h2>Descripción</h2>
          <p>Mix enriquecedor de ensaladas y sopas, contiene 3 frutos secos +
             3 semillas al oreganato.</p>
          <table class="woocommerce-product-attributes shop_attributes"><tbody>
            <tr><th class="woocommerce-product-attributes-item__label">
               Peso</th>
              <td class="woocommerce-product-attributes-item__value">
                <p>250 g</p></td>
            </tr>
            {extra_rows}
          </tbody></table>
          <img src="https://malicioso.invalid/descarga" onerror="alert(1)" alt="no copiar"/>
          {extra_html}
        </div>
      </main>
    </body></html>"""


def parsed(text, *, web=True):
    return parse(
        "fabricante-guardado.html", "text/html",
        base64.b64encode(text.encode("utf-8")).decode("ascii"),
        web_snapshot=web,
    )


def test_saved_realistic_manufacturer_html_extracts_only_literal_product_identity():
    doc = parsed(saved_page())
    assert doc["parse_status"] == "TEXT_EXTRACTED"
    assert doc["identity"]["name"] == "Mix Ensaladas y Sopas"
    assert doc["identity"]["presentation"] == "250 g"
    assert doc["identity"]["ean"] is None
    assert doc["identity"]["is_combo"] is None  # not inferred from a single unit
    name_evidence = doc["identity_evidence"]["name"]
    size_evidence = doc["identity_evidence"]["presentation"]
    assert name_evidence["value"] in doc["sections"][name_evidence["location"]]
    assert size_evidence["value"] in doc["sections"][size_evidence["location"]]
    assert size_evidence["location"].startswith("web/tabla/")
    fields = {claim["field"] for claim in doc["claims"]}
    assert "product_name" in fields and "presentation" in fields
    assert "characteristics" in fields
    characteristic = next(c for c in doc["claims"] if c["field"] == "characteristics")
    assert characteristic["value"] == "3 frutos secos + 3 semillas al oreganato"
    assert characteristic["location"].startswith("web/product/p/")
    assert characteristic["quote"] in doc["sections"][characteristic["location"]]
    assert characteristic["value"] in characteristic["quote"]
    assert not any(
        x in repr(doc).casefold()
        for x in ["producto falso", "9999999999999", "sin tacc", "alert(1)", "malicioso.invalid"]
    )
    # Free-form descriptions remain *visible as source text* but are not
    # converted to nutrition, certification or ingredients facts.
    assert "3 semillas al oreganato" in repr(doc["sections"])
    assert not {"certification", "nutrition.energy", "ingredients"} & fields
    assert URL.startswith("https://")


def test_ambiguous_page_names_or_sizes_fail_closed_without_identity_alias():
    double_name = parsed(saved_page(extra_heads="<h1>Mix distinto</h1>"))
    assert double_name["identity"]["name"] is None
    assert "name" not in double_name["identity_evidence"]

    contradictory_weight = parsed(saved_page(
        extra_rows="<tr><th>Peso</th><td>500 g</td></tr>"
    ))
    assert contradictory_weight["identity"]["presentation"] is None
    assert "presentation" not in contradictory_weight["identity_evidence"]
    assert contradictory_weight["parser_blockers"]


def test_web_mode_is_opt_in_and_passive_document_parser_remains_strict():
    with pytest.raises(ValueError, match="atributos|HTML activo"):
        parsed(saved_page(), web=False)
    # Unchanged passive HTML contract still works independently.
    passive = parsed("<html><body><p>Nombre: Mix</p></body></html>", web=False)
    assert passive["identity"]["name"] == "Mix"


def test_web_html_cannot_exceed_raw_payload_or_visible_text_bounds():
    # A large script is ignored (never treated as source data).
    doc = parsed(saved_page(extra_html="<script>" + "X" * 90000 + "</script>"))
    assert doc["identity"]["name"] == "Mix Ensaladas y Sopas"
    with pytest.raises(ValueError):
        parsed(saved_page(extra_html="<p>" + "X" * 66000 + "</p>"))


def test_untrusted_html_does_not_follow_urls_or_promote_alt_attributes():
    doc = parsed(saved_page(extra_html=(
        '<iframe src="https://internal.invalid/"></iframe>'
        '<form><input value="EAN: 7798180790097"/></form>'
        '<p style="display:none">Presentación: 100 kg</p>'
    )))
    assert doc["identity"]["presentation"] == "250 g"
    assert "7798180790097" not in repr(doc)
    assert "internal.invalid" not in repr(doc)
    assert "100 kg" not in repr(doc)


def test_unrelated_page_text_is_not_composition_evidence():
    outside = (
        "<p>Otro producto contiene 9 frutos secos + 7 semillas al oreganato.</p>"
        "<div class='other-card'>Otra ficha</div>"
    )
    html = saved_page().replace("<main>", outside + "<main>")
    claims = [f for f in parsed(html)["claims"] if f["field"] == "characteristics"]
    assert len(claims) == 1
    assert claims[0]["value"] == "3 frutos secos + 3 semillas al oreganato"


def test_hidden_description_does_not_create_extra_claim():
    html = saved_page(extra_html=(
        '<p class="sr-only">contiene 8 frutos secos + 9 semillas al oreganato</p>'
        '<p aria-hidden="true">contiene 2 frutos secos + 4 semillas al oreganato</p>'
    ))
    facts = [f for f in parsed(html)["claims"] if f["field"] == "characteristics"]
    assert len(facts) == 1
    assert facts[0]["value"].startswith("3 frutos secos")


def test_ambiguous_product_descriptions_block_automatic_composition_extraction():
    html = saved_page(extra_html=(
        "<p>Además contiene 5 frutos secos + 2 semillas al oreganato.</p>"
    ))
    result = parsed(html)
    assert not [f for f in result["claims"] if f["field"] == "characteristics"]
    assert any("declaración descriptiva" in e for e in result["parser_blockers"])
    assert not any(f["field"] == "ingredients" for f in result["claims"])



def test_geonat_style_page_extracts_package_count_without_health_claims():
    """The exact original remains the only authority; text is never approved."""
    html = """<!doctype html><html lang="es"><body><main>
        <h1>ESPIRULINA 500 (60 COMP) - GEONAT</h1>
        <p>🌊 ESPIRULINA 500 – GEONAT . Excelente fuente nutritiva.</p>
        <p>✨ Beneficios principales ✅ Vitamina B, Omega 6 y salud.</p>
        <p>📋 Información del producto Suplemento dietario | 60 comprimidos
           | Espirulina 500 mg | Apto vegano</p>
        <p>💊 Modo de uso 2 comprimidos diarios.</p>
        <p>⚠️ Consultar a un médico antes de consumir.</p>
    </main></body></html>"""
    result = parsed(html)
    assert result["identity"]["name"] == "ESPIRULINA 500 (60 COMP) - GEONAT"
    assert result["identity"]["presentation"] == "60 comprimidos"
    assert result["identity"]["ean"] is None
    presentation = next(
        item for item in result["claims"] if item["field"] == "presentation"
    )
    assert presentation["value"] == "60 comprimidos"
    assert presentation["location"].startswith("web/p/")
    assert presentation["quote"] in result["sections"][presentation["location"]]
    assert "60 comprimidos" in presentation["quote"]
    # The parser NEVER upgrades public marketing copy into a verified fact.
    fields = {item["field"] for item in result["claims"]}
    assert fields == {"product_name", "presentation"}
    assert not fields & {
        "nutrition.energy", "ingredients", "commercial_claim",
        "certification", "allergens", "characteristics",
    }


@pytest.mark.parametrize("title,info", [
    ("ESPIRULINA 500 (60 COMP)", "Información del producto 30 comprimidos"),
    ("ESPIRULINA 500 (60 COMP)", "Información del producto 60 comprimidos y 30 comprimidos"),
    ("ESPIRULINA 500 (60 COMP)", "Beneficios 60 comprimidos"),
    ("ESPIRULINA 500 (60 COMP)", "Información del producto 60 cápsulas"),
    ("ESPIRULINA 500 (60 COMP)", "Información del producto 500 mg"),
])
def test_manufacturer_pack_is_not_inferred_without_exact_corroborration(title, info):
    html = f"<html><main><h1>{title}</h1><p>{info}</p></main></html>"
    result = parsed(html)
    assert result["identity"]["presentation"] is None
    assert not [x for x in result["claims"] if x["field"] == "presentation"]


def test_hidden_or_unrelated_product_info_cannot_become_pack_claim():
    html = """<html><main>
        <h1>GEONAT ESPIRULINA 500 (60 COMP)</h1>
        <p aria-hidden="true">Información del producto 60 comprimidos</p>
        <p>Modo de uso: 60 comprimidos</p>
    </main></html>"""
    assert parsed(html)["identity"]["presentation"] is None
    hidden_sibling = """<html><main>
        <h1>GEONAT ESPIRULINA 500 (60 COMP)</h1>
        <p>Información del producto 60 comprimidos</p>
        <p>Información del producto 30 comprimidos de otro producto</p>
    </main></html>"""
    assert parsed(hidden_sibling)["identity"]["presentation"] is None
