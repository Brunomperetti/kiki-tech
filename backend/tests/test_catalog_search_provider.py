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


class TavilyTransport:
    def __init__(self, result=None):
        self.calls = []
        self.result = result or Result(
            200, "application/json",
            json.dumps({"results": [
                {"url": "https://official.invalid/product", "title": "Fabricante", "content": "Candidato"},
                {"url": "https://shop.invalid/item", "title": "Comercio", "content": "Referencia"},
                {"url": "http://official.invalid/unsafe"},
                {"url": "https://127.0.0.1/internal"},
                {"url": "https://official.invalid/product"},
            ], "usage": {"credits": 1}}).encode(), "93.184.216.34",
        )

    def post(self, host, ip, path, **kwargs):
        self.calls.append((host, ip, path, kwargs))
        return self.result


def test_tavily_basic_search_uses_single_credit_parameters_and_public_identity():
    transport = TavilyTransport()
    identity = {**item(), "sku": "PRIVATE-SKU"}
    result = SearchProvider(config(provider="TAVILY"), resolver=DNS(), transport=transport).search(identity)
    assert result["provider"] == "TAVILY"
    assert result["requests"] == 1
    assert result["automatic_approvals"] == 0
    assert len(result["results"]) == 2
    assert result["results"][0]["snippet"] == "Candidato"
    assert result["results"][0]["source_kind"] == "OFFICIAL_CANDIDATE"
    assert result["results"][1]["source_kind"] == "SECONDARY"
    assert all(not row["evidence_approved"] and not row["official_verified"] for row in result["results"])
    host, ip, path, kwargs = transport.calls[0]
    assert (host, ip, path) == ("api.tavily.com", "93.184.216.34", "/search")
    assert kwargs["token"] == "synthetic-test-token"
    assert kwargs["payload"] == {
        "query": result["query"], "search_depth": "basic", "topic": "general",
        "max_results": 5, "auto_parameters": False, "include_answer": False,
        "include_raw_content": False, "include_images": False, "include_usage": True,
    }
    assert result["query"].startswith("7730114100015")
    assert "PRIVATE-SKU" not in result["query"] and "9439612" not in result["query"]


@pytest.mark.parametrize("status", [301, 401, 429, 432, 433, 500])
def test_tavily_errors_consume_attempt_without_retry(status):
    transport = TavilyTransport(Result(status, "", b"private response", "93.184.216.34"))
    provider = SearchProvider(config(provider="TAVILY", max_requests=1), resolver=DNS(), transport=transport)
    with pytest.raises(ValueError, match="HTTP") as error:
        provider.search(item())
    assert "private response" not in str(error.value)
    with pytest.raises(ValueError, match="Límite"):
        provider.search(item())
    assert len(transport.calls) == 1


def test_tavily_disabled_and_private_dns_never_send_key():
    transport = TavilyTransport()
    with pytest.raises(ValueError):
        SearchProvider(config(provider="TAVILY", enabled=False), resolver=DNS(), transport=transport).search(item())

    class PrivateDNS:
        def resolve(self, host):
            return ["127.0.0.1"]

    with pytest.raises(ValueError):
        SearchProvider(config(provider="TAVILY"), resolver=PrivateDNS(), transport=transport).search(item())
    assert transport.calls == []


def test_tavily_malformed_response_is_not_empty_success():
    transport = TavilyTransport(Result(200, "application/json", b"{}", "93.184.216.34"))
    with pytest.raises(ValueError, match="Formato"):
        SearchProvider(config(provider="TAVILY"), resolver=DNS(), transport=transport).search(item())
