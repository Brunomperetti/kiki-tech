from app.services.enrichment_service import EnrichmentService


def item(
    *,
    sku,
    stock,
    ean=None,
    brand=None,
    name=None,
    status="REVIEW_REQUIRED",
):
    return {
        "product": {
            "sku": sku,
            "name": name or f"Producto {sku}",
            "stock": stock,
            "price": 1000,
            "ean": ean,
            "brand": brand,
        },
        "readiness_status": status,
        "reason_codes": [],
    }


def report(items):
    return {
        "reconciliation_run_id": 7,
        "mercadolibre_source": "MERCADOLIBRE",
        "items": items,
    }


def test_enrichment_pilot_only_uses_review_items_with_positive_stock_and_missing_data():
    result = EnrichmentService.build_report(
        report(
            [
                item(sku="A", stock=5, ean=None, brand=None),
                item(sku="B", stock=2, ean="7791234567890", brand=None),
                item(sku="C", stock=0, ean=None, brand=None),
                item(sku="D", stock=9, ean=None, brand=None, status="BLOCKED"),
                item(sku="E", stock=4, ean="7791234567891", brand="Marca"),
            ]
        ),
        limit=20,
    )

    assert result["summary"]["total_eligible"] == 2
    assert result["summary"]["missing_ean"] == 1
    assert result["summary"]["missing_brand"] == 2
    assert result["summary"]["missing_both"] == 1
    assert [entry["product"]["sku"] for entry in result["items"]] == ["A", "B"]


def test_enrichment_pilot_prioritizes_both_missing_then_higher_stock():
    result = EnrichmentService.build_report(
        report(
            [
                item(sku="EAN", stock=100, ean=None, brand="Marca"),
                item(sku="BOTH-LOW", stock=3, ean=None, brand=None),
                item(sku="BOTH-HIGH", stock=20, ean=None, brand=None),
            ]
        ),
        limit=2,
    )

    assert [entry["product"]["sku"] for entry in result["items"]] == [
        "BOTH-HIGH",
        "BOTH-LOW",
    ]
    assert result["summary"]["pilot_size"] == 2


def test_enrichment_pilot_has_blank_proposal_and_read_only_policy():
    result = EnrichmentService.build_report(
        report([item(sku="A", stock=5, ean=None, brand=None)]),
        limit=20,
    )

    entry = result["items"][0]
    assert entry["research_status"] == "PENDING_RESEARCH"
    assert entry["proposal"]["ean"] is None
    assert entry["proposal"]["source_url"] is None
    assert result["policy"]["mode"] == "READ_ONLY_RESEARCH_PILOT"


def test_product_nature_detects_pack_without_reusing_unit_gtin():
    nature, basis = EnrichmentService.classify_nature(
        {"name": "Pack X 10 Yerba Mate Orgánica Pampa 1/2 Kg", "brand": None, "ean": None}
    )
    assert nature == "PACK_OR_KIT"
    assert "pack" in basis.lower()


def test_product_nature_detects_bulk_and_artisanal():
    bulk, _ = EnrichmentService.classify_nature(
        {"name": "MANZANILLA FLOR SUELTA X 25 GRS", "brand": None, "ean": None}
    )
    artisan, _ = EnrichmentService.classify_nature(
        {"name": "GALLETAS DE AVENA CASERAS X 250", "brand": None, "ean": None}
    )
    assert bulk == "BULK_OR_FRACTIONED"
    assert artisan == "ARTISANAL"


def test_product_nature_detects_standard_unit_and_ambiguous_generic():
    standard, _ = EnrichmentService.classify_nature(
        {
            "name": "Valeriana Sedante Natural Natufarma X 40 Cápsulas",
            "brand": None,
            "ean": None,
        }
    )
    ambiguous, _ = EnrichmentService.classify_nature(
        {"name": "NUEZ PECAN X 100 GRS", "brand": None, "ean": None}
    )
    assert standard == "STANDARD_UNIT"
    assert ambiguous == "AMBIGUOUS_GENERIC"


def test_report_exposes_classification_summary_and_strategy():
    result = EnrichmentService.build_report(
        report(
            [
                item(
                    sku="PACK",
                    stock=5,
                    name="Pack X 2 Valeriana Natufarma X 40 Cápsulas",
                ),
                item(
                    sku="UNIT",
                    stock=4,
                    name="Alfajor Blanco Felices las Vacas",
                ),
                item(
                    sku="GENERIC",
                    stock=3,
                    name="NUEZ PECAN X 100 GRS",
                ),
            ]
        )
    )

    counts = {entry["code"]: entry["count"] for entry in result["classification_summary"]}
    assert counts["PACK_OR_KIT"] == 1
    assert counts["STANDARD_UNIT"] == 1
    assert counts["AMBIGUOUS_GENERIC"] == 1
    assert result["items"][0]["research_strategy"]
