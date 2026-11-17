"""Channel reconciliation must never use Ecomm XLSX barcode hints."""

from app.services.ecomm_channel_coverage_service import (
    _candidate_index, _find_candidates,
)

CODE = "7793396000039"


def source(*, api_code=None):
    return {
        "sku": "6317",
        "gtin": api_code,
        "identity_blockers": [],
        "product_name": "Otro producto",
        "variant_description": "250 g",
        "brand": None,
    }


def channel():
    return _candidate_index("ml", [{
        "external_id": "MLA123",
        "sku_product": "SKU-DIFERENTE",
        "ean_raw": CODE,
        "title": "Dulce de membrillo",
        "brand": "Pizarro",
    }])


def test_no_ecomm_excel_fallback_when_api_code_missing():
    valid, index = channel()
    matches, signals, positions = _find_candidates(source(), valid, index)
    assert matches == []
    assert signals == {}
    assert positions == []


def test_api_barcode_matches_as_candidate_not_verified_identity():
    valid, index = channel()
    matches, signals, positions = _find_candidates(
        source(api_code=CODE), valid, index,
    )
    assert len(matches) == 1
    assert positions == [0]
    assert "VALID_GTIN_EXACT" in signals[id(matches[0])]
    assert "EXPORT_GTIN_CANDIDATE_REVIEW" not in signals[id(matches[0])]


def test_api_barcode_conflict_blocks_ean_matching():
    valid, index = channel()
    conflicting = source(api_code=CODE)
    conflicting["identity_blockers"] = ["BARCODE_GTIN_CONFLICT"]
    assert _find_candidates(conflicting, valid, index)[0] == []
