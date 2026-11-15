"""The Ecomm export is only supplemental retrieval evidence for channel matching."""
from types import SimpleNamespace

from app.services.ecomm_gtin_export_service import safe_gtin_candidates_for_pages
from app.services.ecomm_channel_coverage_service import _candidate_index, _find_candidates


CODE = "7793396000039"


class FakeDB:
    def __init__(self, rows):
        self.record = SimpleNamespace(payload=[{"version": 1, "variants": len(rows), "rows": rows}])
    def scalar(self, query):
        return self.record


def page(*, sku="6317", is_combo=False, ident="9913710", code=""):
    return [{"items": [{"is_combo": is_combo, "variants": [
        {"id": ident, "sku": sku, "is_combo": is_combo, "gtin": code, "barcode": None}
    ]}]}]


def row(*, sku="6317", status="VALID_UNIQUE", combo=False, code=CODE, ident="9913710"):
    return {"ecomm_id": ident, "sku": sku, "gtin": code,
            "status": status, "is_combo": combo}


def test_unique_export_code_usable_as_candidate_without_promoting_to_api():
    values = safe_gtin_candidates_for_pages(FakeDB([row()]), page())
    assert values == {"9913710": CODE}
    valid, index = _candidate_index("ml", [{
        "external_id": "MLA123",
        "sku_product": "UNRELATED",
        "ean_raw": CODE,
        "title": "Dulce de membrillo",
        "brand": "Pizarro",
    }])
    identity = {
        "gtin": None, "sku": "6317", "identity_blockers": [],
        "product_name": "Dulce de membrillo",
        "variant_description": "454 g",
        "brand": "Pizarro",
    }
    matches, signals, positions = _find_candidates(
        identity, valid, index, export_gtin=values["9913710"]
    )
    assert len(matches) == 1
    assert "EXPORT_GTIN_CANDIDATE_REVIEW" in signals[id(matches[0])]
    assert "VALID_GTIN_EXACT" not in signals[id(matches[0])]


def test_export_rejected_if_any_id_or_sku_changed():
    assert safe_gtin_candidates_for_pages(FakeDB([row()]), page(sku="NEW")) == {}
    assert safe_gtin_candidates_for_pages(FakeDB([row()]), page(ident="9999999")) == {}


def test_repeated_and_combo_codes_never_used_to_match_channel():
    assert safe_gtin_candidates_for_pages(
        FakeDB([row(status="VALID_REPEATED")]), page()
    ) == {}
    assert safe_gtin_candidates_for_pages(
        FakeDB([row(status="PACK_REVIEW", combo=True)]), page(is_combo=True)
    ) == {}


def test_api_gtin_remains_authoritative():
    assert safe_gtin_candidates_for_pages(
        FakeDB([row()]), page(code="7793396000039")
    ) == {}


def test_invalid_export_codes_not_candidate():
    assert safe_gtin_candidates_for_pages(
        FakeDB([row(code="3", status="INVALID")]), page()
    ) == {}
