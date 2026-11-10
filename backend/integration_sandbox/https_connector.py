"""Dormant HTTPS adapter for a separately authorized collector; no app/DB imports.

Not wired to the 2H runtime. The release lock is checked BEFORE DNS or sockets.
Tests inject DNS and wire simulators, including fake TLS sockets for the real codec.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import http.client
import io
import ipaddress
import json
import socket
import ssl
import time
from queue import Queue, Empty
from threading import Lock, Thread
from urllib.parse import urljoin
from .pilot_policy import PilotPlan, checked_url
from . import pilot_policy

MAX_BYTES = 524288
MIMES = {
    "application/pdf": "pdf",
    "text/plain": "txt",
    "text/html": "html",
    "application/json": "json",
}


class ConnectorError(ValueError):
    """Only fixed error codes may cross the audit boundary."""


def remaining(deadline, clock=time.monotonic):
    value = deadline - clock()
    if value <= 0:
        raise ConnectorError("TIME_LIMIT")
    return min(value, 3.0)


class DeadlineReader(io.RawIOBase):
    def __init__(self, channel, deadline, clock):
        self.channel, self.deadline, self.clock = channel, deadline, clock

    def readable(self):
        return True

    def readinto(self, buffer):
        self.channel.settimeout(remaining(self.deadline, self.clock))
        data = self.channel.recv(len(buffer))
        buffer[: len(data)] = data
        return len(data)


@dataclass(frozen=True)
class WireResponse:
    status: int
    body: bytes
    content_type: str
    peer: str
    location: str | None = None


class SystemDNS:
    simulated = False

    def __init__(self):
        self.lock = Lock()

    def resolve(self, host, deadline=None):
        if not pilot_policy.REAL_NETWORK_ENABLED:
            raise ConnectorError("REAL_NETWORK_DISABLED")
        # One daemon resolver at most; a hung OS lookup never blocks the deadline
        # or creates unbounded threads. Current runtime independently denies DNS.
        if not self.lock.acquire(blocking=False):
            raise ConnectorError("DNS_BUSY")
        result = Queue(maxsize=1)

        def lookup():
            try:
                result.put(
                    list(
                        dict.fromkeys(
                            row[4][0]
                            for row in socket.getaddrinfo(
                                host, 443, type=socket.SOCK_STREAM
                            )
                        )
                    )
                )
            except Exception:
                result.put(None)
            finally:
                self.lock.release()

        Thread(target=lookup, daemon=True).start()
        try:
            addresses = result.get(timeout=remaining(deadline or time.monotonic() + 3))
        except Empty:
            raise ConnectorError("DNS_TIMEOUT") from None
        if addresses is None:
            raise ConnectorError("DNS_REJECTED")
        return addresses


class PinnedHTTPSWire:
    simulated = False

    def __init__(self, *, socket_factory=None, context=None, clock=time.monotonic):
        self.socket_factory = socket_factory or socket.socket
        if context is None:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            # Fixed OS trust, never SSL_CERT_FILE/.env or an unverified context.
            context.load_verify_locations(cafile="/etc/ssl/certs/ca-certificates.crt")
        if (
            not context.check_hostname
            or context.verify_mode != ssl.CERT_REQUIRED
            or context.minimum_version < ssl.TLSVersion.TLSv1_2
        ):
            raise ConnectorError("TLS_POLICY")
        self.context, self.clock = context, clock

    def get(self, url, pinned_ip, deadline):
        if not pilot_policy.REAL_NETWORK_ENABLED:
            raise ConnectorError("REAL_NETWORK_DISABLED")
        return self._exchange(url, pinned_ip, deadline)

    def _exchange(self, url, pinned_ip, deadline):
        # Private codec seam for offline fake-socket tests, never an RPC method.
        p = checked_url(url)
        channel = self.socket_factory(
            socket.AF_INET6 if ":" in pinned_ip else socket.AF_INET, socket.SOCK_STREAM
        )
        tls = None
        response = None
        try:
            channel.settimeout(remaining(deadline, self.clock))
            channel.connect(
                (pinned_ip, 443)
            )  # numeric IP only; NO second hostname resolution
            if channel.getpeername()[0] != pinned_ip:
                raise ConnectorError("PEER_CHANGED")
            channel.settimeout(remaining(deadline, self.clock))
            tls = self.context.wrap_socket(channel, server_hostname=p.hostname)
            if tls.getpeername()[0] != pinned_ip:
                raise ConnectorError("PEER_CHANGED")
            tls.settimeout(remaining(deadline, self.clock))
            tls.sendall(
                (
                    f"GET {p.path or '/'} HTTP/1.1\r\nHost: {p.hostname}\r\nUser-Agent: KIKI-Document-Pilot/1\r\nAccept: application/pdf, text/plain, text/html, application/json\r\nAccept-Encoding: identity\r\nConnection: close\r\n\r\n"
                ).encode("ascii")
            )
            reader = io.BufferedReader(DeadlineReader(tls, deadline, self.clock), 4096)

            class ResponseSocket:
                def makefile(self, mode):
                    return reader

            response = http.client.HTTPResponse(ResponseSocket())
            response.begin()
            headers = response.headers
            if sum(len(k) + len(v) for k, v in headers.items()) > 16384:
                raise ConnectorError("HEADERS_LIMIT")
            for key in (
                "Content-Type",
                "Content-Length",
                "Location",
                "Content-Encoding",
                "Transfer-Encoding",
            ):
                if len(headers.get_all(key, [])) > 1:
                    raise ConnectorError("AMBIGUOUS_HEADERS")
            encoding = headers.get("Content-Encoding", "identity").lower()
            transfer = headers.get("Transfer-Encoding", "").lower()
            length = headers.get("Content-Length")
            if (
                encoding != "identity"
                or transfer not in {"", "chunked"}
                or (transfer and length)
            ):
                raise ConnectorError("CONTENT_ENCODING")
            if length is not None and (
                not length.isdecimal() or int(length) > MAX_BYTES
            ):
                raise ConnectorError("SIZE_LIMIT")
            mime = headers.get_content_type()
            if response.status == 200 and not headers.get("Content-Type"):
                raise ConnectorError("MIME_REQUIRED")
            # Redirect/error bodies never get downloaded. No cookie jar, retries or auth.
            chunks, size = [], 0
            if response.status == 200:
                if mime not in MIMES:
                    raise ConnectorError("MIME_UNSUPPORTED")
                while True:
                    chunk = response.read1(min(4096, MAX_BYTES + 1 - size))
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > MAX_BYTES:
                        raise ConnectorError("SIZE_LIMIT")
                    chunks.append(chunk)
                if length is not None and size != int(length):
                    raise ConnectorError("CONTENT_LENGTH")
            remaining(deadline, self.clock)
            return WireResponse(
                response.status,
                b"".join(chunks),
                mime,
                pinned_ip,
                headers.get("Location"),
            )
        except (ssl.SSLError, ssl.CertificateError):
            raise ConnectorError("TLS_FAILED") from None
        except (OSError, http.client.HTTPException, UnicodeError):
            raise ConnectorError("TRANSPORT_FAILED") from None
        finally:
            if response is not None:
                response.close()
            if tls is not None:
                tls.close()
            channel.close()


def public_addresses(addresses):
    if not addresses or len(addresses) > 8:
        raise ConnectorError("DNS_REJECTED")
    for value in addresses:
        try:
            ip = ipaddress.ip_address(value)
            if not ip.is_global or ip.is_multicast or ip.is_unspecified:
                raise ValueError
            if "%" in value or (
                ip.version == 6 and (ip.ipv4_mapped or ip.sixtofour or ip.teredo)
            ):
                raise ValueError
        except ValueError:
            raise ConnectorError("DNS_REJECTED") from None
    return tuple(addresses)


def content_check(body, mime):
    if not body or len(body) > MAX_BYTES:
        raise ConnectorError("SIZE_LIMIT")
    if mime not in MIMES:
        raise ConnectorError("MIME_UNSUPPORTED")
    if mime == "application/pdf":
        if not body.startswith(b"%PDF-") or b"%%EOF" not in body[-1024:]:
            raise ConnectorError("CONTENT_SIGNATURE")
    else:
        try:
            value = body.decode("utf-8-sig")
            if "\x00" in value or body.startswith((b"MZ", b"PK\x03\x04", b"%PDF-")):
                raise ValueError
            if mime == "application/json":
                if not isinstance(json.loads(value), dict):
                    raise ValueError
            if mime == "text/html":
                if (
                    not value.lstrip()
                    .lower()
                    .startswith(("<!doctype html", "<html", "<body", "<p", "<table"))
                ):
                    raise ValueError
            if mime == "text/plain" and value.lstrip().startswith(("<", "{", "[")):
                raise ValueError
        except (ValueError, UnicodeError):
            raise ConnectorError("CONTENT_SIGNATURE") from None
    # Full 2G parser validation remains mandatory after transfer, never render original HTML.


class HTTPSConnector:
    def __init__(self, plan=None, *, wire=None, dns=None, clock=time.monotonic):
        self.plan = plan or PilotPlan()
        self.wire, self.dns = wire or PinnedHTTPSWire(), dns or SystemDNS()
        self.clock = clock
        self.requests, self.documents, self.bytes = 0, 0, 0
        self.started = clock()
        self.audit = []
        self.sequence = 0

    def fetch(self, ident, url):
        self.sequence += 1
        request_id = f"request-{self.sequence}"
        # No raw URL, request/response headers, content or exception strings in logs.
        record = {
            "request_id": request_id,
            "at": datetime.now(timezone.utc).isoformat(),
            "method": "GET",
            "result": "PENDING",
            "requests": 0,
        }
        self.audit.append(record)
        del self.audit[:-100]
        try:
            simulated = self.wire.simulated is True and self.dns.simulated is True
            if not simulated and (
                not pilot_policy.REAL_NETWORK_ENABLED or not self.plan.network_enabled
            ):
                raise ConnectorError("REAL_NETWORK_DISABLED")
            if self.documents >= 3 or self.clock() - self.started > 30:
                raise ConnectorError("SESSION_LIMIT")
            deadline, current, seen, hops = (
                min(self.clock() + 5, self.started + 30),
                url,
                set(),
                [],
            )
            for _ in range(3):
                source = self.plan.source_for(ident, current)
                p = checked_url(current)
                if current in seen:
                    raise ConnectorError("REDIRECT_LOOP")
                seen.add(current)
                if self.requests >= 9:
                    raise ConnectorError("REQUEST_LIMIT")
                # DNS is resolved once per hop; numeric connection and strict TLS hostname bind it.
                self.requests += 1
                record["requests"] += 1
                addresses = public_addresses(self.dns.resolve(p.hostname, deadline))
                remaining(deadline, self.clock)
                reply = self.wire.get(current, addresses[0], deadline)
                self.bytes += len(reply.body)
                if self.bytes > 3 * MAX_BYTES:
                    raise ConnectorError("SESSION_BYTES")
                if reply.peer != addresses[0]:
                    raise ConnectorError("PEER_CHANGED")
                remaining(deadline, self.clock)
                hops.append(
                    {"url": current, "peer": reply.peer, "status": reply.status}
                )
                if reply.status in {301, 302, 303, 307, 308}:
                    if not reply.location:
                        raise ConnectorError("REDIRECT_REJECTED")
                    current = urljoin(current, reply.location)
                    continue
                if reply.status != 200:
                    raise ConnectorError("ACCESS_RESTRICTED")
                content_check(reply.body, reply.content_type)
                self.documents += 1
                record.update(result="OK", domain=p.hostname, bytes=len(reply.body))
                return reply.body, {
                    "requested_url": url,
                    "final_url": current,
                    "hops": hops,
                    "sha256": hashlib.sha256(reply.body).hexdigest(),
                    "size": len(reply.body),
                    "content_type": reply.content_type,
                    "consulted_at": record["at"],
                    "manufacturer": source.manufacturer,
                    "approval_reference": source.approval_reference,
                    "declared_official": True,
                    "review_state": "PENDING",
                    "simulated": simulated,
                    "network_enabled": not simulated,
                    "request_id": request_id,
                }
            raise ConnectorError("REDIRECT_LIMIT")
        except ConnectorError as exc:
            record["result"] = str(exc)
            raise
        except Exception:
            record["result"] = "SOURCE_REJECTED"
            raise ConnectorError("SOURCE_REJECTED") from None
