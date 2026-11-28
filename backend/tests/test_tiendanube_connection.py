from app.core.config import Settings
from app.integrations.tiendanube.client import TiendanubeError
from app.services.tiendanube_connection import check_connection


def config(**kwargs):
    return Settings(_env_file=None, **kwargs)


def test_disabled_and_missing_credentials_do_not_call_provider():
    def forbidden(*args, **kwargs):
        raise AssertionError("Unexpected provider request")

    assert check_connection(config(kiki_tiendanube_read_enabled=False),
                            transport=forbidden)["state"] == "DISABLED"
    settings = config(kiki_tiendanube_read_enabled=True,
                      tiendanube_store_id="", tiendanube_access_token="")
    assert check_connection(settings, transport=forbidden)["state"] == "NOT_CONFIGURED"


def test_connection_reads_one_product_and_does_not_leak_secret():
    calls = []

    def fake(method, url, **kwargs):
        calls.append((method, url))
        assert kwargs["headers"]["Authorization"] == "Bearer synthetic-secret"
        return [{"id": 123, "name": "Synthetic"}]

    result = check_connection(config(
        kiki_tiendanube_read_enabled=True, tiendanube_store_id="123",
        tiendanube_access_token="synthetic-secret",
    ), transport=fake)
    assert result == {
        "external_writes_enabled": False, "provider_calls": 1,
        "state": "CONNECTED_READ_ONLY", "store_id": "123", "sample_count": 1,
    }
    assert calls == [("GET", "https://api.tiendanube.com/2025-03/123/products?page=1&per_page=1")]


def test_provider_auth_failure_is_not_connection_success():
    def fake(*args, **kwargs):
        raise TiendanubeError(401)

    result = check_connection(config(
        kiki_tiendanube_read_enabled=True, tiendanube_store_id="123",
        tiendanube_access_token="synthetic-secret",
    ), transport=fake)
    assert result["state"] == "PROVIDER_ERROR"
    assert result["http_status"] == 401
    assert result["external_writes_enabled"] is False
