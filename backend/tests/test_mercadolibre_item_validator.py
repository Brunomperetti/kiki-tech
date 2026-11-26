import json
from types import SimpleNamespace

import pytest

from app.integrations.mercadolibre.client import MercadoLibreClient
from app.integrations.mercadolibre.transport import MercadoLibreHTTPError, Response


class FakeTransport:
    def __init__(self, status):
        self.status = status
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return Response(self.status, None)


def client(transport):
    return MercadoLibreClient(SimpleNamespace(ml_api_url="https://api.mercadolibre.com"),
                              "synthetic-token", transport=transport)


def test_validate_uses_only_validation_endpoint():
    transport = FakeTransport(204)
    payload = {"title": "Synthetic"}
    assert client(transport).validate_item(payload) == {
        "validated": True, "status_code": 204, "publication_created": False,
    }
    assert len(transport.calls) == 1
    method, url, kwargs = transport.calls[0]
    assert method == "POST"
    assert url == "https://api.mercadolibre.com/items/validate"
    assert json.loads(kwargs["data"]) == payload


def test_non_204_is_not_a_clean_validation():
    transport = FakeTransport(200)
    with pytest.raises(MercadoLibreHTTPError):
        client(transport).validate_item({"title": "Synthetic"})
    assert len(transport.calls) == 1


def test_empty_payload_does_not_call_provider():
    transport = FakeTransport(204)
    with pytest.raises(ValueError):
        client(transport).validate_item({})
    assert not transport.calls
