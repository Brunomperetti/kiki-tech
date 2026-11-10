"""Deny-by-default retrieval policy, with ONLY an in-memory simulated transport.

There is no live HTTP client, DNS resolver, network switch or provider credential.
Future networking requires a separately reviewed adapter and a new authorization.
"""

from dataclasses import dataclass, field
import hashlib
import ipaddress
import time
from urllib.parse import urljoin, urlsplit

ALLOWED_HOSTS = frozenset(
    {"fabricante-prueba.invalid", "documentos-prueba.invalid", "pista-publica.invalid"}
)
CONTENT_TYPES = frozenset(
    {"application/pdf", "text/plain", "text/html", "application/json"}
)
MAX_BYTES = 524_288


def destination(url, resolver):
    try:
        parsed = urlsplit(url)
        host = parsed.hostname or ""
        if (
            parsed.scheme != "https"
            or host not in ALLOWED_HOSTS
            or not host.isascii()
            or parsed.username
            or parsed.password
            or parsed.port not in {None, 443}
            or parsed.fragment
            or parsed.query
            or "%" in url
            or "\\" in url
            or any(ord(c) < 33 for c in url)
        ):
            raise ValueError
        addresses = resolver.resolve(host)
        if not addresses or len(addresses) > 8:
            raise ValueError
        for address in addresses:
            ip = ipaddress.ip_address(address)
            if not ip.is_global or ip.is_multicast or ip.is_unspecified:
                raise ValueError
            if ip.version == 6 and ip.ipv4_mapped and not ip.ipv4_mapped.is_global:
                raise ValueError
    except (ValueError, TypeError):
        raise ValueError(
            "Destino/DNS no autorizado: HTTPS, dominio exacto y direcciones públicas requeridos."
        ) from None
    return tuple(addresses)


@dataclass(frozen=True)
class Response:
    status: int
    body: bytes = b""
    content_type: str = "text/plain"
    location: str | None = None
    content_encoding: str = "identity"
    declared_length: int | None = None
    elapsed_ms: int = 1
    remote_ip: str = "93.184.215.14"


@dataclass
class SyntheticDNS:
    records: dict = field(
        default_factory=lambda: {host: ["93.184.215.14"] for host in ALLOWED_HOSTS}
    )

    def resolve(self, host):
        return self.records.get(host, [])


@dataclass
class SimulatedHTTP:
    responses: dict
    requests: list = field(default_factory=list)

    def get(self, url, *, pinned_ip, headers):
        if (
            set(headers) != {"Accept", "User-Agent"}
            or headers["User-Agent"] != "KIKI-Simulation-Only"
        ):
            raise ValueError(
                "No se permiten credenciales, cookies ni cabeceras arbitrarias."
            )
        self.requests.append({"method": "GET", "url": url, "pinned_ip": pinned_ip})
        return self.responses.get(url, Response(404))


def retrieve(url, transport, resolver):
    if type(transport) is not SimulatedHTTP or type(resolver) is not SyntheticDNS:
        raise ValueError("Sólo transporte y DNS simulados. Acceso real deshabilitado.")
    started, elapsed, hops, seen = time.monotonic(), 0, [], set()
    current = url
    for _ in range(3):
        if current in seen:
            raise ValueError("Bucle de redirecciones rechazado.")
        seen.add(current)
        addresses = destination(current, resolver)
        response = transport.get(
            current,
            pinned_ip=addresses[0],
            headers={
                "Accept": ", ".join(sorted(CONTENT_TYPES)),
                "User-Agent": "KIKI-Simulation-Only",
            },
        )
        if response.remote_ip not in addresses:
            raise ValueError("Destino final no coincide con el DNS validado y fijado.")
        elapsed += response.elapsed_ms
        if response.elapsed_ms < 0 or elapsed > 5000 or time.monotonic() - started > 5:
            raise ValueError("Tiempo de obtención excedido.")
        hops.append(
            {
                "url": current,
                "addresses": list(addresses),
                "remote_ip": response.remote_ip,
                "status": response.status,
            }
        )
        if response.status in {301, 302, 303, 307, 308}:
            if not response.location:
                raise ValueError("Redirección sin destino.")
            current = urljoin(current, response.location)
            continue
        if response.status != 200:
            raise ValueError(
                "Fuente no disponible o restringida; no se elude su restricción."
            )
        if (
            response.content_type not in CONTENT_TYPES
            or response.content_encoding != "identity"
        ):
            raise ValueError("Tipo o compresión HTTP no admitidos.")
        if (
            len(response.body) > MAX_BYTES
            or not response.body
            or (
                response.declared_length is not None
                and response.declared_length != len(response.body)
            )
        ):
            raise ValueError("Tamaño o longitud HTTP fuera de límite.")
        return response.body, {
            "requested_url": url,
            "final_url": current,
            "hops": hops,
            "content_type": response.content_type,
            "size": len(response.body),
            "sha256": hashlib.sha256(response.body).hexdigest(),
            "elapsed_ms": elapsed,
            "simulated": True,
            "network_enabled": False,
            "method": "GET",
            "access_policy": "Fixture sintético autorizado; no hay acceso a sitios reales.",
        }
    raise ValueError("Máximo dos redirecciones; no se siguió otro destino.")
