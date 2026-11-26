import pytest

from app.integrations.tiendanube.client import TiendanubeClient, TiendanubeError


def client(transport, enabled=False):
    return TiendanubeClient("123", "synthetic-token", user_agent="KIKI (test@example.com)",
                            writes_enabled=enabled, transport=transport)


def test_writes_disabled_by_default():
    def forbidden(*args, **kwargs):
        pytest.fail("Unexpected network request")
    with pytest.raises(PermissionError):
        client(forbidden).create_hidden_product(name="Test", description="Test", sku="123")


def test_hidden_creation_never_sends_price_or_stock():
    calls = []
    def fake(method, url, **kwargs):
        calls.append((method, url, kwargs))
        return {"id": 987, "visibility": "hidden", "published": False}
    result = client(fake, True).create_hidden_product(name="Test", description="Description", sku="123")
    assert result["id"] == 987
    assert len(calls) == 1
    method, url, kwargs = calls[0]
    assert method == "POST"
    assert url == "https://api.tiendanube.com/2025-03/123/products"
    assert kwargs["payload"] == {"name": {"es": "Test"},
                                "description": {"es": "Description"},
                                "visibility": "hidden", "variants": [{"sku": "123"}]}


def test_unknown_result_is_not_retried():
    calls = []
    def fake(*args, **kwargs):
        calls.append(1)
        return {"id": 987, "published": True, "visibility": "visible"}
    with pytest.raises(TiendanubeError) as exc:
        client(fake, True).create_hidden_product(name="Test", description="Test", sku="123")
    assert exc.value.outcome_unknown
    assert len(calls) == 1


def test_read_search_and_invalid_id():
    calls = []
    def fake(method, url, **kwargs):
        calls.append((method, url))
        return []
    assert client(fake).list_products(query="A&B") == []
    assert calls == [("GET", "https://api.tiendanube.com/2025-03/123/products?page=1&per_page=30&q=A%26B")]
    with pytest.raises(ValueError):
        client(fake).get_product("../orders")
    assert len(calls) == 1
