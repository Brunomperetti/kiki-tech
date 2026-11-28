"""Bounded official-source discovery. Search snippets are never evidence.

Disabled unless an operator configures the existing deployment explicitly.
No environment files, DB, logging of credentials, redirects or automatic retry.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
import ipaddress
import json
from urllib.parse import urlencode, urlsplit

from .source_fetch import DNSResolver, vetted_ip, _PinnedHTTPSConnection, Result

HOST = "api.search.brave.com"
LIMIT = 262144


@dataclass(frozen=True)
class SearchConfig:
    enabled: bool = False
    provider: str = "BRAVE"
    api_key: str = field(default="", repr=False)
    max_requests: int = 20
    timeout_seconds: int = 8
    max_results: int = 5
    official_hosts: tuple[str, ...] = ()


class SearchTransport:
    def get(self, host, ip, path, *, token, timeout):
        connection = _PinnedHTTPSConnection(host, ip)
        connection.timeout = timeout
        try:
            connection.connect()
            remote = connection.sock.getpeername()[0]
            if ipaddress.ip_address(remote) != ipaddress.ip_address(ip):
                raise ValueError("El destino de búsqueda no corresponde al DNS validado.")
            connection.request("GET", path, headers={
                "Host": HOST, "Accept": "application/json", "Accept-Encoding": "identity",
                "X-Subscription-Token": token, "Connection": "close",
            })
            response = connection.getresponse()
            if response.status != 200:
                # Do not expose body, query, key, Location or exception details.
                return Result(response.status, "", b"", remote)
            size = response.getheader("Content-Length")
            encoding = response.getheader("Content-Encoding", "identity")
            if (size and (not size.isdigit() or int(size) > LIMIT)) or encoding != "identity":
                raise ValueError("Respuesta de búsqueda fuera de límites.")
            return Result(200, response.getheader("Content-Type", ""), response.read(LIMIT+1), remote)
        finally:
            connection.close()


class SearchProvider:
    def __init__(self, config, *, resolver=None, transport=None):
        self.config = config
        self.resolver = resolver or DNSResolver()
        self.transport = transport or SearchTransport()
        self.requests = 0
        if (config.provider != "BRAVE" or type(config.max_requests) is not int
                or not 1 <= config.max_requests <= 20 or not 1 <= config.max_results <= 10
                or not 1 <= config.timeout_seconds <= 15):
            raise ValueError("Configuración de búsqueda no admitida.")

    def search(self, identity):
        config = self.config
        if not config.enabled or not config.api_key.strip():
            raise ValueError("Búsqueda externa deshabilitada o proveedor sin configurar; no se consultó Internet.")
        if self.requests >= config.max_requests:
            raise ValueError("Límite de consultas alcanzado; se requiere una nueva operación autorizada.")
        from app.integrations.ecomm_app.api_catalog_browser import valid_variant_id
        if (not isinstance(identity.get("ecomm_id"), str)
                or not valid_variant_id(identity["ecomm_id"])
                or identity.get("identity_blockers")):
            raise ValueError("Identidad incompleta o contradictoria; búsqueda bloqueada.")
        codes = {str(identity[key]) for key in ("barcode", "gtin") if identity.get(key)}
        if len(codes) > 1:
            raise ValueError("Los códigos de la variante se contradicen.")
        name = identity.get("name") or identity.get("product_name")
        presentation = identity.get("presentation") or identity.get("variant_description")
        if not isinstance(name, str) or not name.strip() or not presentation:
            raise ValueError("Falta nombre y presentación de la variante API.")
        terms = [name, str(presentation), str(identity.get("sku") or ""), *sorted(codes), "fabricante producto oficial"]
        query = " ".join(" ".join(terms).split())[:500]
        if any(ord(c) < 32 for c in query):
            raise ValueError("Consulta inválida.")
        ip = vetted_ip(HOST, self.resolver)
        self.requests += 1  # attempt counts even when transport fails
        try:
            result = self.transport.get(HOST, ip, "/res/v1/web/search?"+urlencode({"q": query, "count": config.max_results}), token=config.api_key, timeout=config.timeout_seconds)
        except Exception:
            raise ValueError("La búsqueda no pudo completarse; sin reintentos automáticos.") from None
        if result.status != 200:
            raise ValueError(f"Proveedor de búsqueda HTTP {result.status}; redirecciones y reintentos deshabilitados.")
        if (ipaddress.ip_address(result.remote_ip) != ipaddress.ip_address(ip)
                or result.content_type.split(";", 1)[0].strip().lower() != "application/json"
                or not 0 < len(result.body) <= LIMIT or result.encoding != "identity"):
            raise ValueError("Respuesta de búsqueda inválida.")
        try:
            payload = json.loads(result.body)
            rows = payload.get("web", {}).get("results", [])
        except (ValueError, TypeError, AttributeError):
            raise ValueError("Formato de búsqueda inválido.") from None
        if not isinstance(rows, list) or len(rows) > 100:
            raise ValueError("Resultados de búsqueda fuera de límites.")
        output, seen = [], set()
        for row in rows[:config.max_results]:
            if not isinstance(row, dict):
                continue
            url = row.get("url")
            if not isinstance(url, str) or len(url) > 1000:
                continue
            try:
                parsed = urlsplit(url)
                if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None,443) or parsed.fragment:
                    continue
                try:
                    ipaddress.ip_address(parsed.hostname)
                    continue
                except ValueError:
                    pass
            except ValueError:
                continue
            if url in seen:
                continue
            seen.add(url)
            output.append({"url": url, "title": str(row.get("title") or "")[:300],
                           "snippet": str(row.get("description") or "")[:1000],
                           "source_kind": "OFFICIAL_CANDIDATE" if parsed.hostname in config.official_hosts else "SECONDARY",
                           "official_verified": False, "evidence_approved": False})
        return {"query": query, "queried_at": datetime.now(timezone.utc).isoformat(),
                "results": output, "requests": 1, "cost_known": False,
                "provider": config.provider, "automatic_approvals": 0}
