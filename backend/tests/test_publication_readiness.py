from app.services.publication_readiness_service import PublicationReadinessService


def result(
    status,
    *,
    stock=5,
    ean="7791234567890",
    brand="Marca Test",
    sku="2562",
    sku_product=None,
    sku_variant=None,
    sku_aliases=None,
    ean_aliases=None,
    issues=None,
    reason="",
):
    return {
        "status": status,
        "reason": reason,
        "product": {
            "sku": sku,
            "sku_effective": sku,
            "sku_product": sku_product,
            "sku_variant": sku_variant,
            "sku_aliases": sku_aliases or [sku],
            "ean": ean,
            "ean_aliases": ean_aliases or ([ean] if ean else []),
            "brand": brand,
            "name": "Producto de prueba",
            "price": 1000,
            "stock": stock,
        },
        "issues": issues or [],
    }


def test_candidate_with_core_data_is_ready_for_enrichment():
    status, reasons = PublicationReadinessService.classify(result("CANDIDATE_TO_PUBLISH"))
    assert status == "READY_CORE_DATA"
    assert "imágenes" in reasons[0]


def test_candidate_without_brand_requires_review():
    item = result("CANDIDATE_TO_PUBLISH", brand=None)
    status, reasons = PublicationReadinessService.classify(item)
    assert status == "REVIEW_REQUIRED"
    assert "marca" in reasons[0].lower()
    assert PublicationReadinessService.reason_codes(item, status) == ["BRAND_MISSING"]


def test_candidate_without_stock_is_no_stock():
    status, reasons = PublicationReadinessService.classify(
        result("CANDIDATE_TO_PUBLISH", stock=0)
    )
    assert status == "NO_STOCK"
    assert "stock" in reasons[0].lower()


def test_candidate_without_ean_requires_review():
    item = result(
        "CANDIDATE_TO_PUBLISH",
        ean=None,
        issues=[
            {
                "code": "EAN_MISSING",
                "message": "El producto no tiene EAN/GTIN.",
                "severity": "WARNING",
            }
        ],
    )
    status, reasons = PublicationReadinessService.classify(item)
    assert status == "REVIEW_REQUIRED"
    assert "EAN/GTIN" in reasons[0]
    assert PublicationReadinessService.reason_codes(item, status) == ["EAN_MISSING"]


def test_duplicate_is_blocked():
    item = result(
        "POSSIBLE_DUPLICATE",
        issues=[
            {
                "code": "SKU_DUPLICATE",
                "message": "El SKU está duplicado en Ecomm-App.",
                "severity": "ERROR",
            }
        ],
    )
    status, reasons = PublicationReadinessService.classify(item)
    assert status == "BLOCKED"
    assert "duplicado" in reasons[0]
    assert PublicationReadinessService.reason_codes(item, status) == ["SKU_DUPLICATE"]


def test_manual_reconciliation_review_gets_reason_code():
    item = result(
        "REVIEW_REQUIRED",
        reason="Coincidencia aproximada por título; requiere confirmación humana.",
    )
    status, _ = PublicationReadinessService.classify(item)
    assert status == "REVIEW_REQUIRED"
    assert PublicationReadinessService.reason_codes(item, status) == [
        "RECONCILIATION_REVIEW"
    ]


def test_already_published_is_excluded():
    item = result("ALREADY_PUBLISHED")
    status, reasons = PublicationReadinessService.classify(item)
    assert status == "ALREADY_PUBLISHED"
    assert "publicación" in reasons[0]
    assert PublicationReadinessService.reason_codes(item, status) == [
        "ALREADY_PUBLISHED"
    ]


def test_five_plus_digit_sku_with_unique_four_digit_base_is_excluded_from_bulk():
    items = [
        result("CANDIDATE_TO_PUBLISH", sku="2562"),
        result("CANDIDATE_TO_PUBLISH", sku="2562000"),
    ]
    rules = PublicationReadinessService._bulk_rules(items)

    assert rules[0] is None
    assert rules[1]["action"] == "EXCLUDE"
    assert rules[1]["base_sku"] == "2562"

    items[1]["bulk_rule"] = rules[1]
    status, reasons = PublicationReadinessService.classify(items[1])
    assert status == "EXCLUDED_BULK"
    assert "masivo" in reasons[0].lower()
    assert PublicationReadinessService.reason_codes(items[1], status) == [
        "ASSOCIATED_SKU_OUT_OF_BULK"
    ]


def test_five_plus_digit_sku_without_four_digit_base_requires_review():
    item = result("CANDIDATE_TO_PUBLISH", sku="2562000")
    rule = PublicationReadinessService._bulk_rules([item])[0]
    item["bulk_rule"] = rule

    assert rule["action"] == "REVIEW"
    assert rule["reason_code"] == "EAN_BASE_SKU_MISSING"
    status, reasons = PublicationReadinessService.classify(item)
    assert status == "REVIEW_REQUIRED"
    assert "4 dígitos" in reasons[0]


def test_multiple_four_digit_base_skus_for_same_ean_require_review():
    items = [
        result("CANDIDATE_TO_PUBLISH", sku="2562"),
        result("CANDIDATE_TO_PUBLISH", sku="3000"),
    ]
    rules = PublicationReadinessService._bulk_rules(items)

    assert rules[0]["action"] == "REVIEW"
    assert rules[0]["reason_code"] == "EAN_BASE_SKU_AMBIGUOUS"
    assert rules[1]["action"] == "REVIEW"


def test_no_stock_keeps_priority_over_current_bulk_rule():
    items = [
        result("CANDIDATE_TO_PUBLISH", sku="2562"),
        result("CANDIDATE_TO_PUBLISH", sku="2562000", stock=0),
    ]
    rules = PublicationReadinessService._bulk_rules(items)
    items[1]["bulk_rule"] = rules[1]

    status, _ = PublicationReadinessService.classify(items[1])
    assert status == "NO_STOCK"
