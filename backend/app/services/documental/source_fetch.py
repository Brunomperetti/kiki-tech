"""Strictly opt-in *single-source pilot* fetch of public manufacturer HTML.

No search engine, general crawler, credentials, cookies, proxy, redirects,
third-party services, or database changes. DNS is validated and its selected
public IP is pinned to the TLS-verified connection. Every source still requires
manual provenance and fact review before generating commercial copy.

Only call this behind the documentary feature flag, exact domain allowlist
and exact pilot Ecomm ID gate. Tests use injected non-network fakes.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import http.client
import ipaddress
import re
import socket
import ssl
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

MAX_SOURCE_BYTES = 524_288
MAX_ROBOTS_BYTES = 65_536
MAX_URL = 1000
USER_AGENT = "KIKI-Catalog-Research/0.1"
HOST_PATTERN = re.compile(r"[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?$")
ROBOT_AGENT = "KIKI-Catalog-Research"


def allowed_hosts(csv_value):
    hosts = {v.strip().lower() for v in (csv_value or "").split(",") if v.strip()}
    if any(not HOST_PATTERN.fullmatch(h) or ".." in h for h in hosts):
        raise ValueError("Dominio de fabricante autorizado mal configurado.")
    return frozenset(hosts)


def target(url, hosts):
    """No hostname wildcards or IP literals, query, fragments or alternate ports."""
    try:
        parsed = urlsplit(url)
        host = parsed.hostname or ""
        if (
            len(url) > MAX_URL or parsed.scheme != "https"
            or not HOST_PATTERN.fullmatch(host) or ".." in host
            or host not in hosts or parsed.username or parsed.password
            or parsed.port not in (None, 443)
            or parsed.query or parsed.fragment
            or "%" in url or "\\" in url
            or any(ord(ch) <= 32 or ord(ch) >= 127 for ch in url)
            or not parsed.path.startswith("/")
            or host.replace(".", "").isdigit()
        ):
            raise ValueError
    except (ValueError, TypeError):
        raise ValueError(
            "Fuente rechazada: solo HTTPS y URL exacta de fabricante autorizado, "
            "sin consultas, credenciales ni redirecciones."
        ) from None
    return host, parsed.path


class DNSResolver:
    def resolve(self, hostname):
        infos = socket.getaddrinfo(
            hostname, 443, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP
        )
        return sorted({row[4][0] for row in infos})


def vetted_ip(hostname, resolver):
    try:
        addresses = resolver.resolve(hostname)
        if not addresses or len(addresses) > 8:
            raise ValueError
        for address in addresses:
            ip = ipaddress.ip_address(address)
            if not ip.is_global or ip.is_multicast or ip.is_unspecified:
                raise ValueError
            if ip.version == 6 and ip.ipv4_mapped is not None:
                raise ValueError
        return addresses[0]
    except (ValueError, TypeError, OSError, socket.gaierror):
        raise ValueError(
            "DNS del fabricante no confiable o con direcciones privadas; "
            "no se realizó la descarga."
        ) from None


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host, ip):
        # SNI + certificate verification use the *original* allowed hostname.
        super().__init__(
            host, 443, timeout=4, context=ssl.create_default_context()
        )
        self._pinned_ip = ip

    def connect(self):
        raw = socket.create_connection((self._pinned_ip, 443), timeout=self.timeout)
        try:
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
        except Exception:
            raw.close()
            raise


@dataclass(frozen=True)
class Result:
    status: int
    content_type: str
    body: bytes
    remote_ip: str
    encoding: str = "identity"
    robots_tag: str = ""


class HTTPSFetcher:
    def get(self, hostname, ip, path, byte_limit):
        connection = _PinnedHTTPSConnection(hostname, ip)
        try:
            connection.request(
                "GET", path,
                headers={
                    "Host": hostname,
                    "User-Agent": USER_AGENT,
                    "Accept": "text/html,text/plain" if path == "/robots.txt" else "text/html",
                    "Accept-Encoding": "identity",
                    "Connection": "close",
                },
            )
            result = connection.getresponse()
            remote = connection.sock.getpeername()[0]
            if ipaddress.ip_address(remote) != ipaddress.ip_address(ip):
                raise ValueError("Conexión no corresponde a la IP validada.")
            if result.status != 200:
                return Result(result.status, "", b"", remote)
            declared = result.getheader("Content-Length")
            if declared and (not declared.isdigit() or int(declared) > byte_limit):
                raise ValueError("La fuente supera el límite máximo permitido.")
            encoding = result.getheader("Content-Encoding", "identity")
            if encoding.casefold() != "identity":
                raise ValueError("Contenido comprimido o codificado no admitido.")
            body = result.read(byte_limit + 1)
            if not body or len(body) > byte_limit:
                raise ValueError("Respuesta vacía o superior al límite permitido.")
            return Result(
                status=result.status,
                content_type=result.getheader("Content-Type", ""),
                body=body,
                remote_ip=remote,
                encoding=encoding,
                robots_tag=result.getheader("X-Robots-Tag", ""),
            )
        finally:
            connection.close()


def fetch_html(url, configured_hosts, *, resolver=None, transport=None):
    """Fetch only after exact domain, public DNS, robots and TLS checks."""
    host, path = target(url, allowed_hosts(configured_hosts))
    resolver = resolver if resolver is not None else DNSResolver()
    transport = transport if transport is not None else HTTPSFetcher()
    ip = vetted_ip(host, resolver)

    robots = transport.get(host, ip, "/robots.txt", MAX_ROBOTS_BYTES)
    if (
        robots.status != 200
        or ipaddress.ip_address(robots.remote_ip) != ipaddress.ip_address(ip)
        or len(robots.body) > MAX_ROBOTS_BYTES
        or not robots.body
        or not robots.content_type.lower().startswith("text/plain")
        or robots.encoding.lower() != "identity"
    ):
        raise ValueError(
            "No se pudo verificar robots.txt; la fuente no se descargó. "
            "Usá el archivo original proporcionado por el fabricante."
        )
    try:
        rules = robots.body.decode("utf-8-sig")
        if not re.search(r"(?im)^\s*user-agent\s*:", rules):
            raise ValueError
        robot = RobotFileParser()
        robot.parse(rules.splitlines())
        if not robot.can_fetch(ROBOT_AGENT, url):
            raise ValueError("robots.txt no autoriza el acceso a este producto.")
        delay = robot.crawl_delay(ROBOT_AGENT)
        if delay and delay > 0:
            raise ValueError(
                "El fabricante exige una espera entre consultas. "
                "No se realizará una petición inmediata."
            )
    except UnicodeError:
        raise ValueError("robots.txt requiere texto UTF-8 válido.") from None

    result = transport.get(host, ip, path, MAX_SOURCE_BYTES)
    if result.status != 200:
        raise ValueError(
            "El fabricante no entregó la página HTML pública. "
            "No se siguen redirecciones ni se eluden restricciones."
        )
    if (
        ipaddress.ip_address(result.remote_ip) != ipaddress.ip_address(ip)
        or result.encoding.lower() != "identity"
        or not result.content_type.lower().startswith("text/html")
        or not result.body or len(result.body) > MAX_SOURCE_BYTES
        or "noarchive" in result.robots_tag.lower()
        or b"noarchive" in result.body.lower()
    ):
        raise ValueError(
            "Respuesta no permitida: tipo, tamaño, IP o política de archivo."
        )
    try:
        result.body.decode("utf-8-sig")
    except UnicodeError:
        raise ValueError("Página HTML sin codificación UTF-8 válida.") from None
    return result.body, {
        "requested_url": url,
        "final_url": url,
        "method": "GET",
        "host": host,
        "pinned_public_ip": ip,
        "content_type": "text/html",
        "size": len(result.body),
        "sha256": hashlib.sha256(result.body).hexdigest(),
        "robots_checked": True,
        "tls_hostname_verified": True,
        "redirects_followed": 0,
        "simulated": False,
        "network_enabled": True,
        "acquired_at": datetime.now(timezone.utc).isoformat(),
        "mode": "ALLOWLISTED_SINGLE_PILOT",
    }
