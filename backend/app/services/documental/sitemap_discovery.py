"""Bounded discovery of *candidate* product URLs from an authorized manufacturer sitemap.

Read-only: no publication, provider writes, document ingestion, AI, background
workers or source certification. The operator must authorize a manufacturer host
and one exact sitemap URL. The same pinned-TLS/robots restrictions as the
single-source pilot apply. Unsupported sitemaps fail closed.
"""
from __future__ import annotations

import hashlib
import ipaddress
import re
import unicodedata
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser
from xml.etree import ElementTree

from app.services.editorial_batches.context import sources
from .source_fetch import (
    DNSResolver,
    HTTPSFetcher,
    MAX_ROBOTS_BYTES,
    ROBOT_AGENT,
    allowed_hosts,
    target,
    vetted_ip,
)

MAX_SITEMAP_BYTES = 262_144
MAX_SITEMAP_URLS = 1500
MAX_VARIANTS = 20
MAX_MATCHES_PER_VARIANT = 5
PRODUCT_PREFIXES = ("/producto/", "/productos/", "/product/", "/products/")
STOPWORDS = frozenset({
    "para", "con", "sin", "los", "las", "del", "por", "uno", "una",
    "producto", "suplemento", "natural", "comp", "comprimidos", "caps",
    "capsulas", "cápsulas", "unidad", "unidades", "gr", "x",
})


def _same_ip(result, ip):
    try:
        return ipaddress.ip_address(result.remote_ip) == ipaddress.ip_address(ip)
    except (TypeError, ValueError):
        return False


def fetch_sitemap(url, configured_hosts, *, resolver=None, transport=None):
    """Exactly two bounded GETs: robots.txt and a named XML sitemap. No crawling."""
    hosts = allowed_hosts(configured_hosts)
    host, path = target(url, hosts)
    if not path.endswith(".xml") or "sitemap" not in path.lower():
        raise ValueError("Se requiere una URL exacta de sitemap XML del fabricante.")
    resolver = resolver if resolver is not None else DNSResolver()
    transport = transport if transport is not None else HTTPSFetcher()
    ip = vetted_ip(host, resolver)
    robots = transport.get(host, ip, "/robots.txt", MAX_ROBOTS_BYTES)
    if (
        robots.status != 200 or not _same_ip(robots, ip)
        or not robots.body or len(robots.body) > MAX_ROBOTS_BYTES
        or not robots.content_type.lower().startswith("text/plain")
        or robots.encoding.lower() != "identity"
    ):
        raise ValueError("No se pudo verificar robots.txt del fabricante.")
    try:
        rules = robots.body.decode("utf-8-sig")
    except UnicodeError:
        raise ValueError("robots.txt requiere UTF-8.") from None
    if not re.search(r"(?im)^\s*user-agent\s*:", rules):
        raise ValueError("robots.txt carece de reglas verificables.")
    robot = RobotFileParser()
    robot.parse(rules.splitlines())
    if not robot.can_fetch(ROBOT_AGENT, url):
        raise ValueError("robots.txt prohíbe consultar este sitemap.")
    if (robot.crawl_delay(ROBOT_AGENT) or 0) > 0:
        raise ValueError("El fabricante exige una pausa; sitemap no consultado.")

    result = transport.get(host, ip, path, MAX_SITEMAP_BYTES)
    if (
        result.status != 200 or not _same_ip(result, ip)
        or not result.body or len(result.body) > MAX_SITEMAP_BYTES
        or result.encoding.lower() != "identity"
        or result.content_type.lower().split(";", 1)[0].strip()
            not in {"application/xml", "text/xml", "application/rss+xml"}
        or "noarchive" in result.robots_tag.lower()
    ):
        raise ValueError("El fabricante no entregó un sitemap XML aceptable.")
    urls = parse_sitemap(result.body, host)
    return urls, {
        "sitemap_url": url,
        "sitemap_sha256": hashlib.sha256(result.body).hexdigest(),
        "urls_inspected": len(urls),
        "robots_checked": True,
        "pinned_tls": True,
        "network_get_requests": 2,
    }


def parse_sitemap(raw, host):
    """XML must be a single URL set. No DTD, entities, sitemap-index recursion."""
    if not raw or len(raw) > MAX_SITEMAP_BYTES:
        raise ValueError("Sitemap vacío o demasiado grande.")
    lowered = raw.lower()
    if any(marker in lowered for marker in (b"<!doctype", b"<!entity", b"<?xml-stylesheet")):
        raise ValueError("Sitemap con entidades o instrucciones no permitidas.")
    try:
        root = ElementTree.fromstring(raw)
    except ElementTree.ParseError:
        raise ValueError("Sitemap XML inválido.") from None

    def local(tag):
        return tag.rsplit("}", 1)[-1]

    if local(root.tag) != "urlset":
        raise ValueError("Se admite un sitemap de productos; no índices recursivos.")
    result = []
    seen = set()
    children = list(root)
    if len(children) > MAX_SITEMAP_URLS:
        raise ValueError("Sitemap con demasiadas URLs.")
    for entry in children:
        if local(entry.tag) != "url":
            raise ValueError("Sitemap con estructura inesperada.")
        locations = [
            (item.text or "").strip()
            for item in entry
            if local(item.tag) == "loc"
        ]
        if len(locations) != 1:
            continue
        url = locations[0]
        try:
            found_host, path = target(url, frozenset({host}))
        except ValueError:
            continue
        if (
            found_host != host
            or not path.lower().startswith(PRODUCT_PREFIXES)
            or url in seen
        ):
            continue
        seen.add(url)
        result.append(url)
    return result


def _tokens(value):
    ascii_text = unicodedata.normalize("NFKD", str(value or "")).encode(
        "ascii", "ignore"
    ).decode().lower()
    return [
        token for token in re.findall(r"[a-z0-9]+", ascii_text)
        if len(token) > 2 and token not in STOPWORDS
    ]


def _product_match(row, url):
    source = _tokens(row.get("product_name"))
    slug = set(_tokens(urlsplit(url).path.replace("/", " ")))
    words = {x for x in source if not x.isdigit()}
    numbers = {x for x in source if x.isdigit()}
    # Refuse number-only, generic and mismatched strength/pack candidates.
    matched = sorted(words & slug)
    if not matched or (numbers and not numbers.issubset(slug)):
        return None
    # Prefer multiple descriptive tokens, but one distinctive token remains
    # a candidate only, never an identity approval or verified manufacturer.
    if len(matched) == 1 and len(matched[0]) < 5:
        return None
    description_numbers = {
        token for token in _tokens(row.get("variant_description"))
        if token.isdigit()
    }
    if description_numbers and not description_numbers.issubset(slug):
        return None
    return {
        "url": url,
        "matched_tokens": matched[:10],
        "matching_only": True,
        "verified": False,
        "review_required": True,
        "score_hint": len(matched),
    }


def preview_candidates(db, ids, sitemap_url, configured_hosts, *, resolver=None, transport=None):
    """Cross one official product sitemap with at most 20 stable Ecomm identities."""
    if not ids or len(ids) > MAX_VARIANTS or len(ids) != len(set(ids)):
        raise ValueError("Seleccioná entre 1 y 20 Ecomm IDs únicos.")
    catalogue = sources(db)
    rows = {}
    for ident in ids:
        if not isinstance(ident, str) or not ident.isdecimal() or ident not in catalogue:
            raise ValueError("Variante ausente de la captura Ecomm vigente.")
        rows[ident] = catalogue[ident]
    urls, receipt = fetch_sitemap(
        sitemap_url, configured_hosts, resolver=resolver, transport=transport,
    )
    items = []
    for ident in ids:
        row = rows[ident]
        reasons = []
        if not row.get("sku"):
            reasons.append("SKU sin identidad estable.")
        if not row.get("product_name"):
            reasons.append("Falta nombre de producto en Ecomm.")
        if row.get("is_combo") is not False:
            reasons.append("Pack o tipo de venta no confirmado; revisión manual.")
        candidates = []
        if not reasons:
            for url in urls:
                match = _product_match(row, url)
                if match:
                    candidates.append(match)
            candidates.sort(key=lambda c: (-c["score_hint"], c["url"]))
        overflow = len(candidates) > MAX_MATCHES_PER_VARIANT
        items.append({
            "ecomm_id": ident,
            "sku": row.get("sku"),
            "name": row.get("product_name"),
            "state": "BLOCKED" if reasons else "CANDIDATES" if candidates else "NOT_FOUND",
            "reasons": reasons,
            "ambiguous": overflow or len(candidates) != 1,
            "candidates": candidates[:MAX_MATCHES_PER_VARIANT],
            "candidate_count": len(candidates),
        })
    return {
        "mode": "READ_ONLY_MANUFACTURER_SITEMAP_PREVIEW",
        "receipt": receipt,
        "items": items,
        "external_catalogue_writes": 0,
        "source_downloads": 0,
        "ai_requests": 0,
        "claims_approved": 0,
        "policy": (
            "Coincidencias de URL no prueban identidad, procedencia ni EAN. "
            "Cada producto requiere contraste documental antes de extraer y "
            "aprobar hechos; no se publica ni modifica ningún canal."
        ),
    }
