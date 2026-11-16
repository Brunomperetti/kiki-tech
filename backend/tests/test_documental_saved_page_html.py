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
