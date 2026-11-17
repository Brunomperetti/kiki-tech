"""Offline regression: bounded sitemap discovery never certifies a source.

The manufacturer sitemap and DNS/HTTPS transport are synthetic. No external
requests, real supplier data changes, IA spending or Ecomm writes.
"""
import pytest

from app.services.documental import sitemap_discovery as discovery
from app.services.documental.source_fetch import Result

HOST = "geonat.com.ar"
URL = "https://geonat.com.ar/product-sitemap.xml"
IP = "93.184.216.34"


class Resolver:
    def resolve(self, host):
        assert host == HOST
        return [IP]


class Transport:
    def __init__(self, *, deny=False, sitemap=None):
        self.calls = []
        self.deny = deny
        self.sitemap = sitemap or b"""<?xml version="1.0"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
          <url><loc>https://geonat.com.ar/productos/espirulina-500-60-comp-geonat/</loc></url>
          <url><loc>https://geonat.com.ar/productos/espirulina-500-120-comp-geonat/</loc></url>
          <url><loc>https://geonat.com.ar/productos/valeriana-50g-geonat/</loc></url>
          <url><loc>https://malicioso.invalid/productos/espirulina-500-60-comp-geonat/</loc></url>
          <url><loc>http://geonat.com.ar/productos/espirulina-500-60-comp-geonat/</loc></url>
          <url><loc>https://geonat.com.ar/categoria/espirulina-500-60-comp-geonat/</loc></url>
        </urlset>"""

    def get(self, host, ip, path, byte_limit):
        self.calls.append((host, ip, path, byte_limit))
        if path == "/robots.txt":
            return Result(
                200, "text/plain", b"User-agent: *\nDisallow: /private\n"
                if not self.deny else b"User-agent: *\nDisallow: /",
                IP,
            )
        assert path == "/product-sitemap.xml"
        return Result(200, "application/xml; charset=UTF-8", self.sitemap, IP)


def test_official_sitemap_matches_correct_variant_without_confusing_pack(monkeypatch):
    monkeypatch.setattr(discovery, "sources", lambda db: {
        "6856453": {
            "sku": "ABC123",
            "product_name": "Geonat Espirulina 500 X 60 Comp.",
            "variant_description": "60 comprimidos",
            "is_combo": False,
        },
        "other": {},
    })
    transport = Transport()
    result = discovery.preview_candidates(
        object(), ["6856453"], URL, HOST, resolver=Resolver(), transport=transport,
    )
    item = result["items"][0]
    assert item["state"] == "CANDIDATES"
    assert item["candidate_count"] == 1
    assert item["candidates"][0]["url"].endswith("espirulina-500-60-comp-geonat/")
    assert item["candidates"][0]["verified"] is False
    assert item["candidates"][0]["review_required"] is True
    assert result["claims_approved"] == 0
    assert result["external_catalogue_writes"] == 0
    assert result["source_downloads"] == 0
    assert len(transport.calls) == 2
    assert [path for _, _, path, _ in transport.calls] == [
        "/robots.txt", "/product-sitemap.xml",
    ]


def test_blocks_unknown_combo_and_missing_sku_without_product_fetch(monkeypatch):
    monkeypatch.setattr(discovery, "sources", lambda db: {
        "123": {"sku": "", "product_name": "Espirulina", "is_combo": False},
        "124": {"sku": "X", "product_name": "Espirulina", "is_combo": None},
    })
    result = discovery.preview_candidates(
        object(), ["123", "124"], URL, HOST, resolver=Resolver(), transport=Transport(),
    )
    assert all(item["state"] == "BLOCKED" for item in result["items"])
    assert all(not item["candidates"] for item in result["items"])


def test_robots_denial_never_requests_sitemap():
    transport = Transport(deny=True)
    with pytest.raises(ValueError, match="prohíbe"):
        discovery.fetch_sitemap(URL, HOST, resolver=Resolver(), transport=transport)
    assert len(transport.calls) == 1


def test_rejects_other_hosts_queries_and_unsupported_sitemap_shape():
    with pytest.raises(ValueError):
        discovery.fetch_sitemap("https://malicioso.invalid/product-sitemap.xml", HOST)
    with pytest.raises(ValueError):
        discovery.fetch_sitemap(URL + "?search=espirulina", HOST)
    with pytest.raises(ValueError, match="índices"):
        discovery.parse_sitemap(b"<sitemapindex/>", HOST)
    with pytest.raises(ValueError, match="entidades"):
        discovery.parse_sitemap(b"<!DOCTYPE test [<!ENTITY x 'evil'>]><urlset/>", HOST)
    with pytest.raises(ValueError, match="demasiado"):
        discovery.parse_sitemap(b"x" * (discovery.MAX_SITEMAP_BYTES + 1), HOST)


def test_fails_closed_on_ambiguous_same_product_variants():
    row = {
        "product_name": "Geonat Espirulina 500 X 60 Comp.",
        "variant_description": "60 comprimidos",
        "is_combo": False,
        "sku": "ABC123",
    }
    first = "https://geonat.com.ar/productos/espirulina-500-60-comp-geonat/"
    second = "https://geonat.com.ar/productos/espirulina-500-60-comp-geonat-extra/"
    assert discovery._product_match(row, first)
    assert discovery._product_match(row, second)
    different_pack = "https://geonat.com.ar/productos/espirulina-500-120-comp-geonat/"
    assert discovery._product_match(row, different_pack) is None
