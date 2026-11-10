"""Offline HTTPS tests: fake sockets/DNS, real TLS MemoryBIO, no Internet probes."""

from datetime import datetime, timedelta, timezone
from io import BytesIO
from unittest.mock import patch
import json
import socket
import ssl
import tempfile
import unittest
from pathlib import Path
from .https_connector import (
    HTTPSConnector,
    PinnedHTTPSWire,
    SystemDNS,
    WireResponse,
    ConnectorError,
    public_addresses,
    content_check,
    DeadlineReader,
)
from .pilot_policy import PilotPlan, pilot_status

URL = "https://fabricante-prueba.invalid/ficha"
FINAL = "https://documentos-prueba.invalid/ficha"
IP = "93.184.215.14"


def plan(urls=(URL, FINAL)):
    return PilotPlan.model_validate(
        {
            "products": [
                {
                    "ecomm_id": "900004",
                    "name": "Producto SINTÉTICO para pruebas",
                    "manufacturer": "Fabricante SINTÉTICO",
                    "presentation": "1 kg",
                    "authorization_reference": "Autorización ficticia de prueba",
                }
            ],
            "sources": [
                {
                    "domain": host,
                    "urls": [u for u in urls if u.split("/")[2] == host],
                    "ecomm_ids": ["900004"],
                    "manufacturer": "Fabricante SINTÉTICO",
                    "ownership_evidence": "Evidencia ficticia sólo para probar el contrato, no un fabricante auténtico.",
                    "conditions_review": "Permiso de acceso exclusivamente a respuestas sintéticas de pruebas.",
                    "automated_access_permitted": True,
                    "reviewed_by": "Operador de prueba",
                    "approval_reference": "Autorización ficticia de prueba",
                    "expires_at": (
                        datetime.now(timezone.utc) + timedelta(hours=1)
                    ).isoformat(),
                }
                for host in dict.fromkeys(u.split("/")[2] for u in urls)
            ],
        }
    )


class DNS:
    simulated = True

    def __init__(self, ips=None):
        self.ips, self.calls = ips or [IP], []

    def resolve(self, host, deadline=None):
        self.calls.append(host)
        return self.ips


class Wire:
    simulated = True

    def __init__(self, replies=None):
        self.replies = replies or {
            URL: WireResponse(
                200, "Nombre: Prueba sintética".encode(), "text/plain", IP
            )
        }
        self.calls = []

    def get(self, url, pinned_ip, deadline):
        self.calls.append((url, pinned_ip))
        return self.replies[url]


class FakeSocket:
    def __init__(self, raw, peer=IP):
        self.body, self.peer = BytesIO(raw), peer
        self.addresses, self.sent, self.timeouts, self.closed = [], [], [], False

    def connect(self, address):
        self.addresses.append(address)

    def getpeername(self):
        return self.peer, 443

    def settimeout(self, timeout):
        self.timeouts.append(timeout)

    def sendall(self, data):
        self.sent.append(data)

    def recv(self, size):
        return self.body.read(size)

    def close(self):
        self.closed = True


class FakeTLS:
    check_hostname = True
    verify_mode = ssl.CERT_REQUIRED
    minimum_version = ssl.TLSVersion.TLSv1_2

    def __init__(self, error=None):
        self.error, self.hosts = error, []

    def wrap_socket(self, sock, server_hostname):
        self.hosts.append(server_hostname)
        if self.error:
            raise self.error
        return sock


def codec(raw, **kwargs):
    sock, context = FakeSocket(raw), FakeTLS()
    wire = PinnedHTTPSWire(socket_factory=lambda *args: sock, context=context, **kwargs)
    return wire, sock, context


class ConnectorTests(unittest.TestCase):
    def test_release_lock_before_dns_socket_even_with_environment_switch(self):
        with (
            patch.dict(
                "os.environ",
                {
                    "KIKI_REAL_NETWORK_ENABLED": "true",
                    "HTTPS_PROXY": "https://credential:secret@production.invalid",
                },
            ),
            patch.object(socket, "getaddrinfo", side_effect=AssertionError("NO DNS")),
            patch.object(socket, "socket", side_effect=AssertionError("NO SOCKET")),
        ):
            connector = HTTPSConnector(plan())
            with self.assertRaisesRegex(ConnectorError, "REAL_NETWORK_DISABLED"):
                connector.fetch("900004", URL)
            with self.assertRaisesRegex(ConnectorError, "REAL_NETWORK_DISABLED"):
                connector.wire.get(URL, IP, 10)
            injected = PinnedHTTPSWire(
                socket_factory=lambda *args: self.fail("NO SOCKET"), context=FakeTLS()
            )
            with self.assertRaisesRegex(ConnectorError, "REAL_NETWORK_DISABLED"):
                injected.get(URL, IP, 10)
            with self.assertRaisesRegex(ConnectorError, "REAL_NETWORK_DISABLED"):
                SystemDNS().resolve("fabricante-prueba.invalid")
            self.assertFalse(pilot_status()["network_enabled"])
            self.assertEqual(pilot_status()["authorized_products"], [])

    def test_empty_plan_scope_expiry_and_no_self_enable(self):
        for data in [
            {"network_enabled": True},
            {"sources": [plan().sources[0].model_dump(mode="json")]},
            {"products": plan().products * 4},
            {"api_key": "secret"},
        ]:
            with self.assertRaises(ValueError):
                PilotPlan.model_validate(data)
        for ident, url in [
            ("900001", URL),
            ("900004", URL + "/otro"),
            ("900004", "https://fabricante-prueba.invalid.evil.invalid/ficha"),
        ]:
            with self.assertRaises(ValueError):
                plan().source_for(ident, url)
        with self.assertRaises(ValueError):
            plan().source_for(
                "900004", URL, at=datetime.now(timezone.utc) + timedelta(days=2)
            )
        with self.assertRaises(ValueError):
            PilotPlan().source_for("900004", URL)

    def test_domains_urls_ownership_terms_manufacturer_required(self):
        for change in [
            {"domain": "*.fabricante-prueba.invalid"},
            {"urls": [URL + "?token=secret"]},
            {"urls": ["https://usuario:secret@fabricante-prueba.invalid/ficha"]},
            {"urls": ["http://fabricante-prueba.invalid/ficha"]},
            {"urls": [URL + "/%2e%2e/admin"]},
            {"urls": [URL + "/../../admin"]},
            {"automated_access_permitted": False},
            {"ownership_evidence": "Menciona marca"},
            {"conditions_review": ""},
            {"manufacturer": "Otro fabricante"},
            {"expires_at": "2026-01-01T12:00:00"},
        ]:
            data = plan().model_dump(mode="json")
            data["sources"][0].update(change)
            with self.assertRaises(ValueError):
                PilotPlan.model_validate(data)

    def test_private_mixed_and_ipv6_transition_addresses(self):
        for ips in [
            ["127.0.0.1"],
            ["10.0.0.1"],
            ["169.254.169.254"],
            ["100.64.0.1"],
            ["::1"],
            ["::ffff:8.8.8.8"],
            ["2002:7f00:0001::"],
            ["ff02::1"],
            [IP, "192.168.1.1"],
            ["not-an-ip"],
            ["fe80::1%eth0"],
        ]:
            with self.assertRaises(ConnectorError):
                public_addresses(ips)
        self.assertEqual(public_addresses([IP]), (IP,))

    def test_numeric_connection_strict_tls_sni_and_fixed_headers(self):
        raw = b"HTTP/1.1 200 OK\r\nContent-Type: text/plain; charset=utf-8\r\nContent-Length: 7\r\n\r\nfixture"
        wire, sock, context = codec(raw)
        reply = wire._exchange(URL, IP, wire.clock() + 5)
        self.assertEqual(reply.body, b"fixture")
        self.assertEqual(sock.addresses, [(IP, 443)])
        self.assertEqual(context.hosts, ["fabricante-prueba.invalid"])
        sent = b"".join(sock.sent)
        self.assertIn(b"GET /ficha HTTP/1.1", sent)
        self.assertIn(b"Host: fabricante-prueba.invalid", sent)
        for prohibited in [b"Authorization:", b"Cookie:", b"Proxy-Authorization:"]:
            self.assertNotIn(prohibited, sent)
        self.assertTrue(sock.closed)
        self.assertTrue(all(0 < t <= 3 for t in sock.timeouts))

    def test_redirect_codec_requires_no_body_and_still_pins_tls(self):
        wire, sock, context = codec(
            b"HTTP/1.1 302 Found\r\nLocation: https://documentos-prueba.invalid/ficha\r\n\r\n"
        )
        response = wire._exchange(URL, IP, wire.clock() + 5)
        self.assertEqual(response.status, 302)
        self.assertEqual(response.location, FINAL)
        self.assertEqual(response.body, b"")
        self.assertEqual(context.hosts, ["fabricante-prueba.invalid"])
        self.assertTrue(sock.closed)

    def test_tls_insecure_context_and_handshake_error(self):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        with self.assertRaisesRegex(ConnectorError, "TLS_POLICY"):
            PinnedHTTPSWire(context=context)
        sock = FakeSocket(b"")
        wire = PinnedHTTPSWire(
            socket_factory=lambda *args: sock,
            context=FakeTLS(ssl.SSLCertVerificationError("secret certificate detail")),
        )
        with self.assertRaisesRegex(ConnectorError, "^TLS_FAILED$"):
            wire._exchange(URL, IP, wire.clock() + 5)
        self.assertTrue(sock.closed)

    def test_rebinding_peer_changed_and_dns_pinned_per_hop(self):
        dns = DNS()
        wire = Wire({URL: WireResponse(302, b"", "text/plain", IP, "/siguiente")})

        def change_dns(url, ip, deadline):
            dns.ips = ["127.0.0.1"]
            return wire.get(url, ip, deadline)

        scripted = Wire()
        scripted.get = change_dns
        connector = HTTPSConnector(
            plan((URL, URL.replace("/ficha", "/siguiente"))), wire=scripted, dns=dns
        )
        with self.assertRaisesRegex(ConnectorError, "DNS_REJECTED"):
            connector.fetch("900004", URL)
        self.assertEqual(len(wire.calls), 1)
        connector = HTTPSConnector(
            plan(),
            wire=Wire({URL: WireResponse(200, b"fixture", "text/plain", "127.0.0.1")}),
            dns=DNS(),
        )
        with self.assertRaisesRegex(ConnectorError, "PEER_CHANGED"):
            connector.fetch("900004", URL)

    def test_redirects_must_be_exactly_authorized_and_all_hops_recorded(self):
        wire = Wire(
            {
                URL: WireResponse(302, b"", "text/plain", IP, FINAL),
                FINAL: WireResponse(200, b"fixture", "text/plain", IP),
            }
        )
        body, trace = HTTPSConnector(plan(), wire=wire, dns=DNS()).fetch("900004", URL)
        self.assertEqual(body, b"fixture")
        self.assertEqual(len(trace["hops"]), 2)
        self.assertEqual(trace["review_state"], "PENDING")
        self.assertTrue(trace["simulated"])
        self.assertFalse(trace["network_enabled"])
        for destination in [
            "https://evil.invalid/ficha",
            "http://fabricante-prueba.invalid/ficha",
            "https://127.0.0.1/ficha",
            URL + "?secret=x",
            URL,
        ]:
            connector = HTTPSConnector(
                plan(),
                wire=Wire({URL: WireResponse(302, b"", "text/plain", IP, destination)}),
                dns=DNS(),
            )
            with self.assertRaises(ConnectorError):
                connector.fetch("900004", URL)

    def test_redirect_and_request_document_and_time_budgets(self):
        urls = tuple("https://fabricante-prueba.invalid/" + str(i) for i in range(4))
        replies = {
            url: WireResponse(302, b"", "text/plain", IP, urls[(i + 1) % 4])
            for i, url in enumerate(urls)
        }
        c = HTTPSConnector(plan(urls), wire=Wire(replies), dns=DNS())
        for _ in range(3):
            with self.assertRaisesRegex(ConnectorError, "REDIRECT_LIMIT"):
                c.fetch("900004", urls[0])
        with self.assertRaisesRegex(ConnectorError, "REQUEST_LIMIT"):
            c.fetch("900004", urls[0])
        c = HTTPSConnector(plan(), wire=Wire(), dns=DNS())
        for _ in range(3):
            c.fetch("900004", URL)
        with self.assertRaisesRegex(ConnectorError, "SESSION_LIMIT"):
            c.fetch("900004", URL)
        ticks = [0]
        c = HTTPSConnector(plan(), wire=Wire(), dns=DNS(), clock=lambda: ticks[0])
        ticks[0] = 31
        with self.assertRaisesRegex(ConnectorError, "SESSION_LIMIT"):
            c.fetch("900004", URL)
        reader = DeadlineReader(FakeSocket(b"fixture"), 1, lambda: 2)
        with self.assertRaisesRegex(ConnectorError, "TIME_LIMIT"):
            reader.readinto(bytearray(2))

    def test_streaming_size_encoding_duplicate_headers_and_truncation(self):
        for headers, body in [
            (b"Content-Type: text/plain\r\nContent-Length: 524289", b""),
            (b"Content-Type: text/plain", b"x" * 524289),
            (b"Content-Type: text/plain\r\nContent-Length: 100", b"x"),
            (b"Content-Type: text/plain\r\nContent-Encoding: gzip", b"x"),
            (
                b"Content-Type: text/plain\r\nContent-Length: 1\r\nContent-Length: 2",
                b"xx",
            ),
            (
                b"Content-Type: text/plain\r\nTransfer-Encoding: chunked\r\nContent-Length: 1",
                b"0\r\n\r\n",
            ),
            (b"Content-Type: application/javascript", b"x"),
            (b"X-Test: missing-mime", b"x"),
        ]:
            wire, _, _ = codec(b"HTTP/1.1 200 OK\r\n" + headers + b"\r\n\r\n" + body)
            with self.assertRaises(ConnectorError):
                wire._exchange(URL, IP, wire.clock() + 5)
        wire, _, _ = codec(
            b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nTransfer-Encoding: chunked\r\n\r\n7\r\nfixture\r\n0\r\n\r\n"
        )
        self.assertEqual(wire._exchange(URL, IP, wire.clock() + 5).body, b"fixture")

    def test_signature_and_error_logs_never_echo_sensitive_input(self):
        for body, mime in [
            (b"MZpayload", "text/plain"),
            (b"%PDF-false", "application/pdf"),
            (b"not json", "application/json"),
            (b"<script>fetch(1)</script>", "text/plain"),
            (b"\xff", "text/plain"),
        ]:
            with self.assertRaises(ConnectorError):
                content_check(body, mime)
        c = HTTPSConnector(plan(), wire=Wire(), dns=DNS())
        with self.assertRaises(ConnectorError):
            c.fetch(
                "900004",
                "https://user:SECRET@fabricante-prueba.invalid/ficha?token=SECRET",
            )
        self.assertNotIn("SECRET", json.dumps(c.audit))
        for code in [401, 403, 429, 503]:
            c = HTTPSConnector(
                plan(),
                wire=Wire({URL: WireResponse(code, b"PRIVATE", "text/plain", IP)}),
                dns=DNS(),
            )
            with self.assertRaisesRegex(ConnectorError, "ACCESS_RESTRICTED"):
                c.fetch("900004", URL)
            self.assertNotIn("PRIVATE", json.dumps(c.audit))
            self.assertEqual(c.requests, 1)

    def test_dns_deadline_and_busy_resolver_are_bounded_without_network(self):
        import time
        from threading import Event

        release = Event()
        dns = SystemDNS()

        def slow_lookup(*args, **kwargs):
            release.wait(timeout=2)
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (IP, 443))]

        with (
            patch("integration_sandbox.pilot_policy.REAL_NETWORK_ENABLED", True),
            patch.object(socket, "getaddrinfo", side_effect=slow_lookup),
        ):
            try:
                with self.assertRaisesRegex(ConnectorError, "DNS_TIMEOUT"):
                    dns.resolve("fabricante-prueba.invalid", time.monotonic() + 0.02)
                with self.assertRaisesRegex(ConnectorError, "DNS_BUSY"):
                    dns.resolve("fabricante-prueba.invalid", time.monotonic() + 1)
            finally:
                release.set()

    def test_absolute_stream_deadline_covers_repeated_reads(self):
        clock = [0]
        sock = FakeSocket(
            b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n\r\n" + b"x" * 20000
        )
        original = sock.recv

        def slow_read(size):
            clock[0] += 3
            return original(size)

        sock.recv = slow_read
        wire = PinnedHTTPSWire(
            socket_factory=lambda *args: sock, context=FakeTLS(), clock=lambda: clock[0]
        )
        with self.assertRaisesRegex(ConnectorError, "TIME_LIMIT"):
            wire._exchange(URL, IP, 5)
        self.assertTrue(sock.closed)

    def test_real_tls_engine_rejects_untrusted_and_wrong_hostname_without_sockets(self):
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name(
            [x509.NameAttribute(NameOID.COMMON_NAME, "fabricante-prueba.invalid")]
        )
        now = datetime.now(timezone.utc)
        cert = (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(key.public_key())
            .serial_number(1234)
            .not_valid_before(now - timedelta(days=1))
            .not_valid_after(now + timedelta(days=1))
            .add_extension(
                x509.SubjectAlternativeName(
                    [x509.DNSName("fabricante-prueba.invalid")]
                ),
                False,
            )
            .sign(key, hashes.SHA256())
        )
        pem = cert.public_bytes(serialization.Encoding.PEM)
        with tempfile.TemporaryDirectory() as directory:
            cp, kp = Path(directory) / "cert.pem", Path(directory) / "key.pem"
            cp.write_bytes(pem)
            kp.write_bytes(
                key.private_bytes(
                    serialization.Encoding.PEM,
                    serialization.PrivateFormat.PKCS8,
                    serialization.NoEncryption(),
                )
            )
            server = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            server.load_cert_chain(cp, kp)
            for trusted, host in [
                (False, "fabricante-prueba.invalid"),
                (True, "otro.invalid"),
                (True, "fabricante-prueba.invalid"),
            ]:
                client = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                if trusted:
                    client.load_verify_locations(cadata=pem.decode())
                ci, co, si, so = (ssl.MemoryBIO() for _ in range(4))
                c = client.wrap_bio(ci, co, server_hostname=host)
                s = server.wrap_bio(si, so, server_side=True)
                failure, completed = None, False
                for _ in range(20):
                    try:
                        c.do_handshake()
                        completed = True
                    except ssl.SSLWantReadError:
                        pass
                    except ssl.SSLCertVerificationError as exc:
                        failure = exc
                        break
                    data = co.read()
                    if data:
                        si.write(data)
                    try:
                        s.do_handshake()
                    except ssl.SSLWantReadError:
                        pass
                    data = so.read()
                    if data:
                        ci.write(data)
                    if completed:
                        break
                if trusted and host == "fabricante-prueba.invalid":
                    self.assertTrue(completed)
                else:
                    self.assertIsInstance(failure, ssl.SSLCertVerificationError)


if __name__ == "__main__":
    unittest.main(verbosity=2)
