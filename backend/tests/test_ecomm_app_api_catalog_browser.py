import pytest

from app.integrations.ecomm_app.catalog_stage import STAGE_SOURCE
from app.integrations.ecomm_app.api_catalog_browser import api_catalog_rows


def page():
    return [{
        "page": 1, "total": 2, "total_pages": 1, "per_page": 50,
        "captured_at": "2026-10-23T12:00:00+00:00",
        "items": [
            {
                "code": "2500", "description": "Magnesio con Potasio",
                "is_combo": False,
                "variants": [{
                    "id": 101, "sku": "2500", "description": "30 cápsulas",
                    "is_combo": False, "gtin": "7790001",
                    "total_stock": 8, "warehouses": [{"id": 7, "stock": 8}]
                }]
            },
            {
                "code": "2500_m", "description": "Pack x2 Magnesio",
                "is_combo": True,
                "variants": [{
                    "id": 102, "sku": "2500400", "description": "60 cápsulas",
                    "is_combo": True, "barcode": "7790001",
                    "total_stock": 1, "warehouses": [{"id": 7, "stock": 1}]
                }]
            },
        ],
    }]


def test_api_catalog_uses_only_variant_ids_and_keeps_pack_separate():
    result = api_catalog_rows(page(), query="2500")
    assert result["source"] == STAGE_SOURCE
    assert result["total_matches"] == 2
    assert result["total_variants_in_capture"] == 2
    assert [x["ecomm_id"] for x in result["items"]] == ["101", "102"]
    assert [x["sku"] for x in result["items"]] == ["2500", "2500400"]
    assert [x["is_combo"] for x in result["items"]] == [False, True]
    assert result["external_writes_enabled"] is False
    assert result["operational_source_activated"] is False


def test_lookup_id_and_pagination_are_from_api_only():
    found = api_catalog_rows(page(), query="102", page=1, limit=1)
    assert found["total_matches"] == 1
    assert found["items"][0]["sku"] == "2500400"
    second = api_catalog_rows(page(), page=2, limit=1)
    assert second["items"][0]["ecomm_id"] == "102"


def test_empty_and_partial_captures_never_return_a_partial_catalog():
    with pytest.raises(ValueError, match="no está completa"):
        api_catalog_rows([])
    incomplete = page()
    incomplete[0]["total_pages"] = 2
    with pytest.raises(ValueError, match="no está completa"):
        api_catalog_rows(incomplete)


def test_missing_gtin_stock_are_not_invented():
    data = page()
    data[0]["items"][0]["variants"][0]["gtin"] = None
    data[0]["items"][0]["variants"][0]["total_stock"] = None
    result = api_catalog_rows(data, query="101")
    assert result["items"][0]["gtin"] is None
    assert result["items"][0]["stock_at_capture"] is None


def test_no_family_inference_and_bounded_query():
    result = api_catalog_rows(page(), query="7790001")
    assert len(result["items"]) == 2
    assert "component" not in result["items"][1]
    with pytest.raises(ValueError, match="80"):
        api_catalog_rows(page(), query="x" * 81)
