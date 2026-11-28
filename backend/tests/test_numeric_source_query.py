"""Authorized numeric product query compatibility; entirely simulated network.

The Coopar URL is an operator-supplied candidate, not a downloaded/approved
manufacturer document. Fake payloads below do not verify any actual product.
"""

import ssl

import pytest

from app.services.documental.source_fetch import (
    MAX_ROBOTS_BYTES,
    MAX_SOURCE_BYTES,
    Result,
    SourceFetchError,
    SourceTransportError,
    allowed_hosts,
    fetch_html,
    target,
)

HOST = "www.coopar.com.uy"
URL = "https://www.coopar.com.uy/Producto.aspx?id=21"
IP = "93.184.216.34"


class DNS:
    def __init__(self, ip=IP):
        self.ip = ip

    def resolve(self, host):
        assert host == HOST
        return [self.ip]


class HTTP:
    def __init__(
        self,
        *,
        robots=b"User-agent: *\nDisallow: /privado/\n",
        status=200,
        mime="text/html",
        encoding="identity",
        remote=IP,
        error=None,
        body=b"<html><body>Documento SINTETICO</body></html>",
    ):
        self.robots, self.status, self.mime = robots, status, mime
        self.encoding, self.remote, self.error, self.body = (
            encoding,
            remote,
            error,
            body,
        )
        self.calls = []

    def get(self, host, ip, path, limit):
        assert host == HOST and ip == IP
        self.calls.append((host, ip, path, limit))
        if self.error:
            raise self.error
        if path == "/robots.txt":
            return Result(200, "text/plain", self.robots, self.remote)
        assert path in {"/Producto.aspx?id=21", "/Producto.aspx?id=22"}
        return Result(self.status, self.mime, self.body, self.remote, self.encoding)


def test_exact_authorized_numeric_aspx_url_preserves_query_and_distinct_identity():
    host, path = target(URL, allowed_hosts(HOST))
    assert (host, path) == (HOST, "/Producto.aspx?id=21")
    other = URL.replace("id=21", "id=22")
    assert target(other, allowed_hosts(HOST))[1] == "/Producto.aspx?id=22"
    assert target(other, allowed_hosts(HOST)) != (host, path)
    assert target(URL.replace("id=21", "id=9999999999"), allowed_hosts(HOST))[
        1
    ].endswith("id=9999999999")


@pytest.mark.parametrize(
    "url",
    [
        URL.replace("id=21", "x=1"),
        URL.replace("id=21", "ID=21"),
        URL.replace("id=21", "id=0"),
        URL.replace("id=21", "id=01"),
        URL.replace("id=21", "id=-21"),
        URL.replace("id=21", "id=+21"),
        URL.replace("id=21", "id=10000000000"),
        URL.replace("id=21", "id="),
        URL + "&id=22",
        URL + "&x=1",
        URL + ";x=1",
        URL + "?id=22",
        URL + "#seccion",
        URL + "#",
        URL + "%26x=1",
        URL.replace("id=21", "id=%32%31"),
        URL.replace("id=21", "%69d=21"),
        URL.replace("id=21", "id=https://127.0.0.1"),
        URL.replace("id=21", "url=https://host.invalid"),
        URL.replace("Producto.aspx", "producto.html"),
        URL.replace("Producto.aspx", "buscar"),
        URL.replace(HOST, HOST + ":443"),
        URL.replace(HOST, HOST + ":8443"),
        URL.replace("https:", "http:"),
        URL.replace(HOST, "usuario:clave@" + HOST),
        URL.replace(HOST, HOST + ".evil.invalid"),
        URL.replace(HOST, "127.0.0.1"),
        URL.replace("id=21", ""),
        URL + "\n",
        URL.replace("Producto.aspx", "Producto.aspx\\"),
    ],
)
def test_general_queries_and_url_tricks_stay_rejected(url):
    with pytest.raises(ValueError, match="Fuente rechazada"):
        target(url, allowed_hosts(HOST))


def test_numeric_query_does_not_authorize_unlisted_manufacturer():
    with pytest.raises(ValueError, match="Fuente rechazada"):
        target(URL, allowed_hosts("otro-fabricante.invalid"))


def test_fetch_uses_literal_query_after_robots_and_records_exact_reference():
    transport = HTTP()
    raw, receipt = fetch_html(URL, HOST, resolver=DNS(), transport=transport)
    assert raw == transport.body
    assert transport.calls == [
        (HOST, IP, "/robots.txt", MAX_ROBOTS_BYTES),
        (HOST, IP, "/Producto.aspx?id=21", MAX_SOURCE_BYTES),
    ]
    assert receipt["requested_url"] == receipt["final_url"] == URL
    assert receipt["robots_checked"] and receipt["tls_hostname_verified"]
    assert receipt["redirects_followed"] == 0 and receipt["request_count"] == 2
    second = HTTP()
    _, other = fetch_html(
        URL.replace("id=21", "id=22"), HOST, resolver=DNS(), transport=second
    )
    assert second.calls[1][2] == "/Producto.aspx?id=22"
    assert other["requested_url"] != receipt["requested_url"]


def test_robots_policy_applies_to_exact_numeric_query_not_only_the_aspx_path():
    transport = HTTP(robots=b"User-agent: *\nDisallow: /Producto.aspx?id=21\n")
    with pytest.raises(ValueError, match="robots.txt no autoriza"):
        fetch_html(URL, HOST, resolver=DNS(), transport=transport)
    assert len(transport.calls) == 1
    other = HTTP(robots=transport.robots)
    fetch_html(URL.replace("id=21", "id=22"), HOST, resolver=DNS(), transport=other)
    assert len(other.calls) == 2


@pytest.mark.parametrize(
    "kwargs,error",
    [
        ({"status": 302}, SourceFetchError),
        ({"status": 403}, SourceFetchError),
        ({"mime": "application/pdf"}, ValueError),
        ({"encoding": "gzip"}, ValueError),
        ({"remote": "127.0.0.1"}, ValueError),
        ({"body": b"x" * (MAX_SOURCE_BYTES + 1)}, ValueError),
        ({"error": ssl.SSLError("Synthetic TLS failure")}, SourceTransportError),
    ],
)
def test_numeric_query_retains_tls_redirect_mime_size_and_peer_guards(kwargs, error):
    with pytest.raises(error):
        fetch_html(URL, HOST, resolver=DNS(), transport=HTTP(**kwargs))


def test_private_dns_is_rejected_before_any_http():
    transport = HTTP()
    with pytest.raises(ValueError, match="DNS"):
        fetch_html(URL, HOST, resolver=DNS("127.0.0.1"), transport=transport)
    assert transport.calls == []
