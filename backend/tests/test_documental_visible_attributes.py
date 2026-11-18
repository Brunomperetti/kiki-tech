"""Visible WooCommerce product attributes are unapproved, cited candidates only.

No external requests, provider access, approvals or product edits. Synthetic
HTML isolates common manufacturer tables from banners/related-product cards.
"""
import base64

import pytest

from document_reader.parser import parse


def read(extra="", *, title="Producto de ensayo 250 g", table=True):
    rows = """
        <tr><th>Marca</th><td>Marca de ensayo</td></tr>
        <tr><th>Fabricante</th><td>Fabricante de ensayo</td></tr>
        <tr><th>Ingredientes</th><td>Semillas de girasol y sésamo</td></tr>
        <tr><th>Conservación</th><td>Guardar en lugar fresco y seco</td></tr>
        <tr><th>Categoría</th><td>Semillas y granos</td></tr>
        <tr><th>Subcategoría</th><td>Mix de semillas</td></tr>
        <tr><th>Peso</th><td>250 g</td></tr>
        """
    own = (
        '<table class="woocommerce-product-attributes shop_attributes">'
        '<tbody>' + rows + '</tbody></table>'
        if table else ""
    )
    html = f"""<!doctype html><html><head>
        <meta name="description" content="Certificación orgánica NO COMPROBADA">
        <script>var falseIngredient = "Ingredientes: sustancias ficticias";</script>
        </head><body>
        <nav><table><tr><th>Ingredientes</th><td>Aceite de soja falso</td></tr></table></nav>
        <main><h1>{title}</h1>
        <div class="woocommerce-tabs">
        {own}{extra}
        </div></main></body></html>"""
    return parse(
        "fabricante-ejemplo.html", "text/html",
        base64.b64encode(html.encode()).decode(), web_snapshot=True,
    )


def test_visible_woo_table_supplies_individual_cited_candidates():
    result = read()
    by_field = {claim["field"]: claim for claim in result["claims"]}
    assert set(by_field) == {
        "product_name", "brand", "manufacturer", "ingredients",
        "storage_conditions", "category", "subcategory", "presentation",
    }
    assert by_field["ingredients"]["value"] == "Semillas de girasol y sésamo"
    assert by_field["category"]["value"] == "Semillas y granos"
    assert by_field["presentation"]["value"] == "250 g"
    assert result["identity"]["brand"] == "Marca de ensayo"
    assert result["identity"]["manufacturer"] == "Fabricante de ensayo"
    for field in (
        "brand", "manufacturer", "ingredients", "storage_conditions",
        "category", "subcategory", "presentation",
    ):
        claim = by_field[field]
        assert claim["location"].startswith("web/tabla/fila/")
        assert result["sections"][claim["location"]] == claim["quote"]
        assert claim["value"] in claim["quote"]
    assert not {
        "nutrition.energy", "certification", "allergens",
        "commercial_claim", "ean",
    } & set(by_field)
    assert "Aceite de soja falso" not in repr(result)
    assert "sustancias ficticias" not in repr(result)
    assert "Certificación orgánica NO COMPROBADA" not in repr(result)
    # Original HTML content is only a candidate. No state=APPROVED anywhere.
    assert all(claim.get("state") != "APPROVED" for claim in result["claims"])


def test_unrelated_page_table_is_never_evidence():
    result = read(
        '<table><tr><th>Ingredientes</th><td>Una mezcla falsa</td></tr></table>'
    )
    assert result["identity"]["name"] == "Producto de ensayo 250 g"
    assert result["identity"]["presentation"] == "250 g"
    assert not any(
        x["value"] == "Una mezcla falsa" for x in result["claims"]
    )


def test_related_product_woocommerce_table_outside_product_scope_is_not_evidence():
    result = read("", table=False)
    assert not any(
        claim["field"] in {"ingredients", "category", "manufacturer"}
        for claim in result["claims"]
    )


@pytest.mark.parametrize("fragment", [
    '<tr hidden><th>Ingredientes</th><td>Ingrediente oculto</td></tr>',
    '<tr aria-hidden="true"><th>Ingredientes</th><td>Ingrediente oculto</td></tr>',
    '<tr><th>Ingredientes</th><td style="display:none">Ingrediente oculto</td></tr>',
])
def test_hidden_rows_and_cells_never_create_claims(fragment):
    result = read(
        '<table class="woocommerce-product-attributes">' + fragment + '</table>',
        table=False,
    )
    assert not any(x["field"] == "ingredients" for x in result["claims"])


def test_conflicting_ingredient_rows_block_approval_instead_of_choosing_one():
    result = read("""
      <table class="woocommerce-product-attributes">
        <tr><th>Ingredientes</th><td>Una composición incompatible</td></tr>
      </table>
    """)
    assert "ingredients" not in {x["field"] for x in result["claims"]}
    assert any(
        "ingredients" in text for text in result["parser_blockers"]
    )
    # Conflicting source is NOT silently treated as verified.
    assert result["identity"]["name"] == "Producto de ensayo 250 g"


def test_two_h1_blocks_product_attributes_and_name():
    result = read(
        '<h1>Producto distinto</h1>'
    )
    assert result["identity"]["name"] is None
    assert not any(
        item["location"].startswith("web/tabla/") for item in result["claims"]
    )


def test_suspicious_unlabelled_text_is_not_promoted_to_facts():
    result = read("""
      <p>¡Previene enfermedades, orgánico y sin gluten!</p>
      <p>Composición no certificada: 100% promesas.</p>
      <p>Ingredientes de otra variante: sustancias inventadas.</p>
    """, table=False)
    assert result["claims"][0]["field"] == "product_name"
    assert len(result["claims"]) == 1
