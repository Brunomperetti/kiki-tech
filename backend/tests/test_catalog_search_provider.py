"""Offline transport and DNS only; no vendor costs or credentials."""
import json
from dataclasses import replace

import pytest

from app.services.documental.search_provider import SearchConfig, SearchProvider
from app.services.documental.source_fetch import Result


class DNS:
    def resolve(self, host):
        return ["93.184.216.34"]


class Transport:
    def __init__(self, result=None):
        self.calls = 0
        self.result = result or Result(200, "application/json", json.dumps({"web": {"results": [{"url": "https://official.invalid/product/one", "title": "Source"}]}}).encode(), "93.184.216.34")

    def get(self, *args, **kwargs):
        self.calls += 1
        assert kwargs["token"] == "synthetic-test-token"
        return self.result


def item():
    return {"ecomm_id": "9439612", "sku": "108", "name": "Fideos arroz", "presentation": "500 g", "barcode": "7730114100015"}


def config(**kw):
    return replace(SearchConfig(enabled=True, api_key="synthetic-test-token", official_hosts=("official.invalid",)), **kw)


def test_search_candidate_is_not_official_proof_or_approval():
    transport = Transport()
    response = SearchProvider(config(), resolver=DNS(), transport=transport).search(item())
    assert response["results"][0]["source_kind"] == "OFFICIAL_CANDIDATE"
    assert response["results"][0]["official_verified"] is False
    assert response["automatic_approvals"] == 0
    assert "7730114100015" in response["query"]
    assert "synthetic-test-token" not in repr(config())


@pytest.mark.parametrize("overrides", [{"enabled": False}, {"api_key": ""}])
def test_disabled_configuration_never_connects(overrides):
    transport = Transport()
    with pytest.raises(ValueError):
        SearchProvider(config(**overrides), resolver=DNS(), transport=transport).search(item())
    assert transport.calls == 0


@pytest.mark.parametrize("status", [301,302,307,401,429,500])
def test_errors_redirects_and_retries_are_blocked(status):
    transport = Transport(Result(status, "", b"secret body", "93.184.216.34"))
    provider = SearchProvider(config(max_requests=1), resolver=DNS(), transport=transport)
    with pytest.raises(ValueError, match="HTTP"):
        provider.search(item())
    with pytest.raises(ValueError, match="Límite"):
        provider.search(item())
    assert transport.calls == 1


def test_conflicting_identity_never_calls_search():
    transport = Transport()
    with pytest.raises(ValueError):
        SearchProvider(config(), resolver=DNS(), transport=transport).search({**item(), "gtin": "other"})
    assert transport.calls == 0

@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "::1", "::ffff:127.0.0.1"])
def test_private_or_rebound_dns_never_receives_credentials(address):
    class UnsafeDNS:
        def resolve(self, host):
            return ["93.184.216.34", address]
    transport = Transport()
    with pytest.raises(ValueError, match="DNS"):
        SearchProvider(config(), resolver=UnsafeDNS(), transport=transport).search(item())
    assert transport.calls == 0

@pytest.mark.parametrize("result", [
    Result(200, "text/html", b"not json", "93.184.216.34"),
    Result(200, "application/json", b"{}", "127.0.0.1"),
    Result(200, "application/json", b"x" * 262145, "93.184.216.34"),
    Result(200, "application/json", b"{broken", "93.184.216.34"),
])
def test_invalid_contents_or_peer_are_rejected(result):
    with pytest.raises(ValueError):
        SearchProvider(config(), resolver=DNS(), transport=Transport(result)).search(item())


def test_tls_failure_no_retry_or_secret_exception_leak():
    class BrokenTLS(Transport):
        def get(self, *args, **kwargs):
            self.calls += 1
            raise RuntimeError("synthetic-test-token private error")
    transport = BrokenTLS()
    with pytest.raises(ValueError) as caught:
        SearchProvider(config(), resolver=DNS(), transport=transport).search(item())
    assert "synthetic-test-token" not in str(caught.value)
    assert transport.calls == 1
