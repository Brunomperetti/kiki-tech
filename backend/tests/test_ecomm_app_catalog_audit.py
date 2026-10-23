"""Paginated Ecomm inventory catalog audit, always read-only and bounded."""
import pytest

from app.integrations.ecomm_app.public_api import (
    EcommAppApiError, EcommAppInventoryClient,
)
from app.integrations.ecomm_app.catalog_audit import audit_catalog_pages


def _parent(index: int, *, combo=False, sku=None, vid=None):
    return {
        "code": f"P{index}",
        "is_combo": combo,
        "variants": [{
            "id": index if vid is None else vid,
            "sku": f"SKU{index}" if sku is None else sku,
            "is_combo": combo,
            "total_stock": 0 if index % 2 else 7,
            "warehouses": [{"id": 2210, "stock": 0}],
        }],
    }


def test_only_two_pages_of_50_and_not_persisted_or_writing():
    observed = []
    def fake_request(method, path, token, *, params=None, body=None):
        observed.append((method, path, params, body))
        return {
            "items": [_parent(i) for i in range((params["page"]-1)*50, params["page"]*50)],
            "paginacion": {"page": params["page"], "total": 3100, "per_page": 50},
        }

    client = EcommAppInventoryClient("fake-test-token", requester=fake_request)
    audit = client.catalog_audit()
    assert audit["mode"] == "READ_ONLY_AUDIT"
    assert audit["pages_read"] == 2
    assert audit["totals_in_this_batch"]["parents"] == 100
    assert audit["totals_in_this_batch"]["variants"] == 100
    assert audit["next_page_to_check"] == 3
    assert audit["pages"][0]["pagination"]["values"]["total"] == 3100
    assert audit["is_full_catalog"] is False
    assert all(method == "GET" and params["limit"] == 50 and body is None
               for method, _path, params, body in observed)
    assert [x[2]["page"] for x in observed] == [1, 2]


def test_last_short_page_stops_and_no_false_full_catalog_claim():
    seen = []
    def fetch(page):
        seen.append(page)
        return {"items": [_parent(i) for i in range(11)],
                "paginacion": {"current_page": page, "total_pages": 1}}
    result = audit_catalog_pages(fetch)
    assert seen == [1]
    assert result["pages_read"] == 1
    assert result["next_page_to_check"] is None
    assert result["is_full_catalog"] is False


def test_repeated_ids_and_skus_in_one_batch_are_reported_not_resolved():
    data = {"items": [
        _parent(1, sku="SHARED", vid=55),
        _parent(2, sku="SHARED", vid=55),
        {"code": "MISSING", "variants": [{"sku": "", "id": None}]},
    ]}
    report = audit_catalog_pages(lambda page: data)
    totals = report["totals_in_this_batch"]
    assert totals["parents"] == 3
    assert totals["repeated_variant_ids"] == 1
    assert totals["repeated_skus"] == 1
    assert totals["variants_without_id"] == 1
    assert totals["variants_without_sku"] == 1
    assert totals["variants_without_total_stock"] == 1


def test_unexpected_response_is_error_not_empty_catalog():
    with pytest.raises(EcommAppApiError) as e:
        audit_catalog_pages(lambda page: {"paginacion": {"total": 100}})
    assert e.value.code == "PAGINACION_DESCONOCIDA"


@pytest.mark.parametrize("start", [0, -1, 10001, True, "2"])
def test_reject_invalid_start_page_before_reading(start):
    seen = []
    with pytest.raises(ValueError):
        audit_catalog_pages(lambda page: seen.append(page), start_page=start)
    assert seen == []
