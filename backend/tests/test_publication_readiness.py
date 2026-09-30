from app.services.publication_readiness_service import PublicationReadinessService


def result(status, *, stock=5, ean="7791234567890", issues=None, reason=""):
    return {
        "status": status,
        "reason": reason,
        "product": {
            "sku": "ABC-1",
            "ean": ean,
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


def test_candidate_without_stock_is_no_stock():
    status, reasons = PublicationReadinessService.classify(
        result("CANDIDATE_TO_PUBLISH", stock=0)
    )
    assert status == "NO_STOCK"
    assert "stock" in reasons[0].lower()


def test_candidate_without_ean_requires_review():
    status, reasons = PublicationReadinessService.classify(
        result(
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
    )
    assert status == "REVIEW_REQUIRED"
    assert "EAN/GTIN" in reasons[0]


def test_duplicate_is_blocked():
    status, reasons = PublicationReadinessService.classify(
        result(
            "POSSIBLE_DUPLICATE",
            issues=[
                {
                    "code": "SKU_DUPLICATE",
                    "message": "El SKU está duplicado en Ecomm-App.",
                    "severity": "ERROR",
                }
            ],
        )
    )
    assert status == "BLOCKED"
    assert "duplicado" in reasons[0]


def test_already_published_is_excluded():
    status, reasons = PublicationReadinessService.classify(result("ALREADY_PUBLISHED"))
    assert status == "ALREADY_PUBLISHED"
    assert "publicación" in reasons[0]
