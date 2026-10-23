import json
from io import BytesIO
from unittest.mock import patch
from urllib.error import HTTPError

import pytest

from app.integrations.ecomm_app.public_api import (
    API_PREFIX, BASE_URL, EcommAppApiError, EcommAppInventoryClient,
    _fetch, _preview_items,
)


def _client_fake():
    calls = []

    def requester(method, path, token, *, params=None, body=None):
        calls.append((method, path, token, params, body))
        if path.endswith("/depositos"):
            return [{"id": 1, "name": "Córdoba"}]
        if path.endswith("/productos/consulta"):
            return {"products": [{
                "code": "VITANERAL",
                "variants": [
                    {"sku": "VITANERALVAINILLA", "total_stock": 32,
                     "warehouses": [{"warehouse_id": 1, "stock": 32}]},
                    {"sku": "VITANERALCHOCOLATE", "total_stock": 28,
                     "warehouses": [{"warehouse_id": 1, "stock": 28}]},
                ],
            }]}
        return {
            "items": [{
                "code": "5028",
                "description": "Multi Magnesio",
                "variants": [{"sku": "5028000", "total_stock": 0}],
            }],
            "page": 1,
        }

    return EcommAppInventoryClient("private-test-token", requester=requester), calls


def test_preview_reads_only_first_three_and_never_writes():
    client, calls = _client_fake()
    result = client.preview()
    assert result["mode"] == "READ_ONLY_PREVIEW"
    assert result["warehouse_preview"]["samples"][0]["id"] == 1
    assert result["product_preview"]["samples"][0]["variants"][0]["sku"] == "5028000"
    assert [call[0] for call in calls] == ["GET", "GET"]
    assert calls[1][3] == {"page": 1, "limit": 3}
    assert all(call[2] == "private-test-token" for call in calls)
    assert "private-test-token" not in json.dumps(result)


def test_lookup_preserves_complex_skus_and_uses_documented_read_only_post():
    client, calls = _client_fake()
    skus = ["REM/001 M", "A+B#2", "VITANERALVAINILLA"]
    result = client.lookup(skus)
    assert result["mode"] == "READ_ONLY_SKU_LOOKUP"
    assert result["product_preview"]["samples"][0]["variants"][0]["sku"] == "VITANERALVAINILLA"
    assert calls == [(
        "POST", f"{API_PREFIX}/productos/consulta", "private-test-token", None,
        {"skus": skus},
    )]


@pytest.mark.parametrize("bad", [[], ["SKU"] * 4, ["", "ABC"], ["A" * 129], ["ABC", "ABC"]])
def test_lookup_rejects_unbounded_invalid_and_duplicate_skus(bad):
    client, calls = _client_fake()
    with pytest.raises(ValueError):
        client.lookup(bad)
    assert calls == []


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self, *_):
        return json.dumps(self.body).encode()


def test_http_auth_is_server_side_and_unwraps_data():
    observed = []
    def fake_open(request, timeout=0):
        observed.append((request.full_url, request.get_header("Authorization"), request.get_method(), timeout))
        return FakeResponse({"data": {"items": [{"code": "5028"}]}})

    with patch("app.integrations.ecomm_app.public_api.urlopen", fake_open):
        data = _fetch("GET", f"{API_PREFIX}/productos", "supersecret", params={"page": 1, "limit": 3})
    assert data == {"items": [{"code": "5028"}]}
    assert observed == [
        (f"{BASE_URL}{API_PREFIX}/productos?page=1&limit=3", "Bearer supersecret", "GET", 12)
    ]


def test_external_error_codes_do_not_echo_remote_sensitive_messages():
    error_body = BytesIO(json.dumps({
        "error": {"code": "SCOPE_INSUFICIENTE", "message": "Bearersupersecret"}
    }).encode())
    def fake_open(_request, timeout=0):
        raise HTTPError("test", 403, "Forbidden", {}, error_body)

    with patch("app.integrations.ecomm_app.public_api.urlopen", fake_open):
        with pytest.raises(EcommAppApiError) as caught:
            _fetch("GET", f"{API_PREFIX}/productos", "supersecret")
    assert caught.value.status_code == 403
    assert caught.value.code == "SCOPE_INSUFICIENTE"
    assert "inventario:leer" in caught.value.message
    assert "supersecret" not in str(caught.value)


def test_unexpected_schema_is_not_silently_reported_as_empty_inventory():
    preview = _preview_items({"paginacion": {"page": 1}}, kind="products")
    assert preview["shape_recognized"] is False
    assert preview["count"] is None
    assert preview["warning"]


def test_zero_stock_is_not_treated_as_missing():
    preview = _preview_items({
        "items": [{
            "code": "5028", "variants": [{
                "sku": "5028000", "total_stock": 0,
                "warehouses": [{"id": 5, "stock": 0}],
            }],
        }],
    }, kind="products")
    row = preview["samples"][0]["variants"][0]
    assert row["total_stock"] == 0
    assert row["warehouse_sample"] == [{"id": 5, "stock": 0}]


def test_token_required_and_transport_whitelisted():
    with pytest.raises(ValueError, match="ECOMM_APP_API_TOKEN"):
        EcommAppInventoryClient("")
    with pytest.raises(ValueError, match="admitida"):
        _fetch("DELETE", f"{API_PREFIX}/productos", "secret")
    with pytest.raises(ValueError, match="admitida"):
        _fetch("POST", f"{API_PREFIX}/depositos", "secret", body={"x": 1})
