from app.services.enrichment_service import EnrichmentService


def item(*, sku, stock, ean=None, brand=None, status="REVIEW_REQUIRED"):
    return {
        "product": {
            "sku": sku,
            "name": f"Producto {sku}",
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
