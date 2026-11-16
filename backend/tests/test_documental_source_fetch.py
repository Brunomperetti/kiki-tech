"""Single-source manufacturer fetch: no network in tests; fail-closed policy."""
from hashlib import sha256
from types import SimpleNamespace

import pytest
from sqlalchemy.orm import Session

from app.services.documental.source_fetch import (
    Result, allowed_hosts, fetch_html, target, vetted_ip,
)
from app.services.documental.contracts import ManufacturerFetch
from app.services.documental.storage import Document
from test_documental_complete_draft_flow import prepare
from test_documental_saved_page_html import saved_page


HOST = "naturalseed.com.ar"
URL = "https://naturalseed.com.ar/producto/mix-ensaladas-y-sopas/"
PUBLIC_IP = "93.184.216.34"
HTML = saved_page().encode("utf-8")


class Resolver:
    def __init__(self, addresses=None):
        self.addresses = [PUBLIC_IP] if addresses is None else addresses

    def resolve(self, host):
        assert host == HOST
        return self.addresses


class FakeTransport:
    def __init__(self, robots=b"User-agent: *\nDisallow: /privado/\n",
                 content=HTML, robots_status=200, page_status=200,
                 mime="text/html; charset=UTF-8", encoding="identity",
                 remote_ip=PUBLIC_IP, tag=""):
        self.robots = robots
        self.content = content
        self.robots_status = robots_status
        self.page_status = page_status
        self.mime = mime
        self.encoding = encoding
        self.remote_ip = remote_ip
        self.tag = tag
        self.requests = []

    def get(self, host, ip, path, byte_limit):
        self.requests.append((host, ip, path, byte_limit))
        assert host == HOST and ip == PUBLIC_IP
        if path == "/robots.txt":
            return Result(
                self.robots_status, "text/plain; charset=UTF-8", self.robots,
                self.remote_ip,
            )
        assert path == "/producto/mix-ensaladas-y-sopas/"
        return Result(
            self.page_status, self.mime, self.content, self.remote_ip,
            self.encoding, self.tag,
        )


def test_allowlisted_public_robots_permitted_page_yields_verifiable_original():
    transport = FakeTransport()
    raw, record = fetch_html(
        URL, HOST, resolver=Resolver(), transport=transport,
    )
    assert raw == HTML
    assert record["sha256"] == sha256(HTML).hexdigest()
    assert record["host"] == HOST
    assert record["simulated"] is False and record["network_enabled"] is True
    assert record["tls_hostname_verified"] is True
    assert record["robots_checked"] is True
    assert record["redirects_followed"] == 0
    assert len(transport.requests) == 2
    assert transport.requests[0][2] == "/robots.txt"
    assert transport.requests[1][2] == "/producto/mix-ensaladas-y-sopas/"


@pytest.mark.parametrize("url", [
    "http://naturalseed.com.ar/producto/mix-ensaladas-y-sopas/",
    "https://127.0.0.1/producto/",
    "https://naturalseed.com.ar.evil.invalid/producto/",
    "https://u:p@naturalseed.com.ar/producto/",
    "https://naturalseed.com.ar:8443/producto/",
    "https://naturalseed.com.ar/producto/?page=1",
    "https://naturalseed.com.ar/producto/#fragmento",
    "https://naturalseed.com.ar/%2e%2e/admin",
    "https://naturalseed.com.ar\\@host.invalid/producto/",
    "https://naturalseed.com.ar/producto/\nX-Header:evil",
])
def test_url_must_be_exact_https_allowed_host_without_url_tricks(url):
    with pytest.raises(ValueError, match="Fuente rechazada"):
        target(url, allowed_hosts(HOST))


def test_dns_must_have_only_routable_addresses():
    for addresses in (
        [], ["127.0.0.1"], [PUBLIC_IP, "169.254.169.254"],
        ["192.168.1.4"], ["::1"], ["fe80::1"],
        ["::ffff:127.0.0.1"], [PUBLIC_IP] * 9,
    ):
        with pytest.raises(ValueError, match="DNS"):
            vetted_ip(HOST, Resolver(addresses))


@pytest.mark.parametrize("robots,expect", [
    (b"User-agent: *\nDisallow: /producto/\n", "robots.txt no autoriza"),
    (b"", "No se pudo verificar robots.txt"),
    (b"<html>not robots</html>", "No se pudo verificar robots.txt"),
    (b"User-agent: *\nCrawl-delay: 5\n", "exige una espera"),
])
def test_robots_denied_or_unknown_never_requests_page(robots, expect):
    transport = FakeTransport(robots=robots)
    with pytest.raises(ValueError, match=expect):
        fetch_html(URL, HOST, resolver=Resolver(), transport=transport)
    assert len(transport.requests) == 1


@pytest.mark.parametrize("overrides,expect", [
    ({"page_status": 301}, "no entregó la página"),
    ({"page_status": 403}, "no entregó la página"),
    ({"mime": "application/pdf"}, "Respuesta no permitida"),
    ({"encoding": "gzip"}, "Respuesta no permitida"),
    ({"tag": "noarchive"}, "Respuesta no permitida"),
    ({"content": b"X" * 524289}, "Respuesta no permitida"),
    ({"content": b"<meta name='robots' content='noarchive'>"}, "Respuesta no permitida"),
    ({"content": b"\xff\xfe"}, "UTF-8"),
])
def test_response_policy_fail_closed(overrides, expect):
    transport = FakeTransport(**overrides)
    with pytest.raises(ValueError, match=expect):
        fetch_html(URL, HOST, resolver=Resolver(), transport=transport)


def test_pilot_route_enforces_flags_identity_source_and_daily_quota(tmp_path, monkeypatch):
    import app.api.routes.documental_workspace as route
    import app.services.documental.research as research_module
    from document_reader.parser import parse

    monkeypatch.setattr(
        research_module, "get_settings",
        lambda: SimpleNamespace(kiki_admin_username="test"),
    )
    engine, _ = prepare(tmp_path)
    config = SimpleNamespace(
        kiki_document_source_fetch_enabled=False,
        kiki_document_source_fetch_hosts=HOST,
        kiki_document_source_fetch_pilot_id="7518949",
        kiki_document_parser_kernel_required=True,
    )
    monkeypatch.setattr(route, "get_settings", lambda: config)
    monkeypatch.setattr(route, "reader_available", lambda: True)
    calls = []

    def fake_fetch(url, hosts):
        assert url == URL and hosts == HOST
        calls.append(url)
        return HTML, {
            "sha256": sha256(HTML).hexdigest(),
            "size": len(HTML), "host": HOST, "requested_url": URL,
            "final_url": URL, "robots_checked": True,
            "tls_hostname_verified": True,
            "simulated": False, "network_enabled": True,
        }

    monkeypatch.setattr(route, "fetch_html", fake_fetch)
    monkeypatch.setattr(
        route, "parse_local",
        lambda body: parse(
            body.filename, body.content_type, body.content_base64,
            web_snapshot=body.web_snapshot,
        ),
    )
    body = ManufacturerFetch(
        expected_version=0,
        reference_url=URL,
        provenance_note="Fuente pública solicitada por el operador para esta variante.",
        authorized_local_processing=True,
    )
    session = SimpleNamespace(id=1)
    from fastapi import HTTPException
    with Session(engine) as db:
        with pytest.raises(HTTPException) as off:
            route.fetch_manufacturer("7518949", body, db, session)
        assert off.value.status_code == 403
        assert calls == []

        config.kiki_document_source_fetch_enabled = True
        with pytest.raises(HTTPException) as bad_id:
            route.fetch_manufacturer("9999", body, db, session)
        assert bad_id.value.status_code == 403
        assert calls == []

        saved = route.fetch_manufacturer("7518949", body, db, session)
        assert len(calls) == 1
        doc_id = saved["incorporated_document_id"]
        doc = db.get(Document, doc_id)
        assert doc.body["source"]["review_state"] == "PENDING"
        assert doc.body["source"]["declared_official"] is False
        assert doc.body["source"]["capture_mode"] == "USER_SAVED_WEB_HTML"
        assert doc.body["original"]["sha256"] == sha256(HTML).hexdigest()
        assert doc.body["retrieval"]["tls_hostname_verified"] is True
        assert doc.body["retrieval"]["network_enabled"] is True
        assert not saved["facts"]
        # No second retrieval today, even with a fresh dossier version.
        body.expected_version = saved["version"]
        with pytest.raises(HTTPException, match="consulta automática diaria"):
            route.fetch_manufacturer("7518949", body, db, session)
        assert len(calls) == 1


def test_pilot_route_rejects_no_reader_before_network(tmp_path, monkeypatch):
    import app.api.routes.documental_workspace as route
    import app.services.documental.research as research_module
    from fastapi import HTTPException

    monkeypatch.setattr(
        research_module, "get_settings",
        lambda: SimpleNamespace(kiki_admin_username="test"),
    )
    engine, _ = prepare(tmp_path)
    monkeypatch.setattr(route, "get_settings", lambda: SimpleNamespace(
        kiki_document_source_fetch_enabled=True,
        kiki_document_source_fetch_hosts=HOST,
        kiki_document_source_fetch_pilot_id="7518949",
        kiki_document_parser_kernel_required=True,
    ))
    monkeypatch.setattr(route, "reader_available", lambda: False)
    monkeypatch.setattr(route, "fetch_html",
                        lambda *_args: pytest.fail("Network must not run"))
    body = ManufacturerFetch(
        expected_version=0, reference_url=URL,
        provenance_note="Fuente pública del fabricante pendiente de revisar.",
        authorized_local_processing=True,
    )
    with Session(engine) as db:
        with pytest.raises(HTTPException, match="Lector documental aislado"):
            route.fetch_manufacturer("7518949", body, db, SimpleNamespace(id=1))
