import json
import ssl
import unittest
from ecomm_reader.policy import HOST, MAX_BYTES, Request, page_url
from ecomm_reader.reader import InventoryReader
from ecomm_reader.safety import Code, Failure
from ecomm_reader.simulated import (
    FakeContext,
    FakeDNS,
    FakeFactory,
    envelope,
    http_reply,
)
from ecomm_reader.wire import Credential, PinnedGetWire

TOKEN = "NON_SECRET_AUTHORIZATION_TEST_CONTROL"


def wire(replies=None, *, context=None, **socket_options):
    factory = FakeFactory(replies or [http_reply(envelope())], **socket_options)
    result = PinnedGetWire(socket_factory=factory, context=context or FakeContext())
    return result, factory


class Wire(unittest.TestCase):
    def exchange(self, instance, *, request=None, revalidate=lambda: None):
        return instance.exchange(
            request or Request(page_url(1)),
            "8.8.8.8",
            instance.clock() + 12,
            Credential(TOKEN),
            revalidate,
        )

    def test_get_codec_uses_pinned_ip_sni_and_no_cookie_or_payload(self):
        context = FakeContext()
        instance, factory = wire(context=context)
        body, digest = self.exchange(instance)
        self.assertEqual(json.loads(body), envelope())
        self.assertEqual(len(digest), 64)
        self.assertEqual(context.sni, [HOST])
        sent = factory.channels[0].sent
        self.assertTrue(
            sent.startswith(
                b"GET /api/v3/public/inventario/productos?barcode=7794940000796&page=1&limit=50&sort=sku_asc HTTP/1.1\r\n"
            )
        )
        self.assertIn(b"Host: admin.ecomm-app.com\r\n", sent)
        self.assertIn(("Authorization: Bearer " + TOKEN).encode(), sent)
        self.assertNotIn(b"Cookie:", sent)
        self.assertNotIn(b"Content-Length:", sent)
        self.assertTrue(sent.endswith(b"\r\n\r\n"))
        self.assertEqual(factory.channels[0].address, ("8.8.8.8", 443))
        self.assertTrue(factory.channels[0].closed)
        self.assertTrue(all(0 < t <= 12 for t in factory.channels[0].timeouts))

    def test_unavailable_live_adapter_fails_before_any_io(self):
        with self.assertRaises(Failure) as caught:
            PinnedGetWire()
        self.assertEqual(caught.exception.code, Code.OFFLINE_ONLY)
        with self.assertRaises(Failure):
            PinnedGetWire(socket_factory=lambda: None)

    def test_invalid_target_or_method_never_opens_a_channel(self):
        instance, factory = wire()
        for request in (
            Request(page_url(1), "POST"),
            Request(page_url(1).replace(HOST, "kiki-tech-api.onrender.com")),
            Request(page_url(1).replace(HOST, "localhost")),
        ):
            with self.assertRaises(Failure):
                self.exchange(instance, request=request)
        self.assertEqual(factory.channels, [])

    def test_insecure_context_rejected_at_construction_and_after_mutation(self):
        for name, value in (
            ("check_hostname", False),
            ("verify_mode", ssl.CERT_NONE),
            ("minimum_version", ssl.TLSVersion.TLSv1),
            ("keylog_filename", "/tmp/forbidden-keylog"),
        ):
            context = FakeContext()
            setattr(context, name, value)
            with self.assertRaises(Failure):
                wire(context=context)
        instance, factory = wire()
        instance.context.check_hostname = False
        with self.assertRaises(Failure):
            self.exchange(instance)
        self.assertEqual(factory.channels, [])

    def test_invalid_certificate_or_peer_never_sends_a_credential(self):
        for options in ({"tcp_peer": "1.1.1.1"}, {"tls_peer": "1.1.1.1"}, {"port": 80}):
            instance, factory = wire(**options)
            with self.assertRaises(Failure):
                self.exchange(instance)
            self.assertEqual(factory.channels[0].sent, b"")
        instance, factory = wire(context=FakeContext(fail=True))
        with self.assertRaises(Failure):
            self.exchange(instance)
        self.assertEqual(factory.channels[0].sent, b"")

    def test_missing_peer_certificate_blocks_authorization(self):
        instance, factory = wire()
        original_factory = factory.__class__.__call__

        # A local callable double with an empty certificate, not a real socket.
        class NoCertificate:
            simulated = True

            def __call__(self):
                channel = original_factory(factory)
                channel.getpeercert = lambda: {}
                return channel

        instance.factory = NoCertificate()
        with self.assertRaises(Failure):
            self.exchange(instance)
        self.assertEqual(factory.channels[0].sent, b"")

    def test_dns_rebinding_checked_again_before_the_bearer_header(self):
        instance, factory = wire()
        reader = InventoryReader(
            FakeDNS([("8.8.8.8",), ("1.1.1.1",)]), instance, Credential(TOKEN)
        )
        with self.assertRaises(Failure) as caught:
            reader.read()
        self.assertEqual(caught.exception.code, Code.REBINDING)
        self.assertEqual(factory.channels[0].sent, b"")

    def test_private_or_mixed_dns_never_connects(self):
        instance, factory = wire()
        reader = InventoryReader(
            FakeDNS([("8.8.8.8", "10.0.0.1")]), instance, Credential(TOKEN)
        )
        with self.assertRaises(Failure):
            reader.read()
        self.assertEqual(factory.channels, [])

    def test_final_peer_must_still_equal_the_pin(self):
        instance, _ = wire(final_peer="1.1.1.1")
        with self.assertRaises(Failure) as caught:
            self.exchange(instance)
        self.assertEqual(caught.exception.code, Code.TLS)

    def test_every_redirect_is_rejected_without_another_request(self):
        for status in (300, 301, 302, 303, 304, 305, 307, 308, 399):
            for destination in (
                "https://kiki-tech-api.onrender.com/",
                "http://127.0.0.1/",
                page_url(2),
            ):
                instance, factory = wire(
                    [
                        http_reply(
                            body=b"", status=status, headers=[("Location", destination)]
                        )
                    ]
                )
                reader = InventoryReader(FakeDNS(), instance, Credential(TOKEN))
                with self.assertRaises(Failure) as caught:
                    reader.read()
                self.assertEqual(caught.exception.code, Code.REDIRECT)
                self.assertEqual(len(factory.channels), 1)
                self.assertNotIn(TOKEN, str(caught.exception))

    def test_location_even_with_200_is_not_followed(self):
        instance, factory = wire(
            [
                http_reply(
                    envelope(),
                    headers=[
                        ("Location", "https://blocked.invalid/"),
                        ("Content-Type", "application/json"),
                    ],
                )
            ]
        )
        with self.assertRaises(Failure) as caught:
            self.exchange(instance)
        self.assertEqual(caught.exception.code, Code.REDIRECT)
        self.assertEqual(len(factory.channels), 1)

    def test_empty_location_is_also_rejected(self):
        instance, _ = wire(
            [
                http_reply(
                    envelope(),
                    headers=[("Location", ""), ("Content-Type", "application/json")],
                )
            ]
        )
        with self.assertRaises(Failure) as caught:
            self.exchange(instance)
        self.assertEqual(caught.exception.code, Code.REDIRECT)

    def test_tls_gets_only_the_time_left_after_connect(self):
        now = [0.0]
        factory = FakeFactory([http_reply(envelope())])
        original = factory.__class__.__call__

        class SlowConnect:
            simulated = True

            def __call__(self):
                channel = original(factory)
                connect = channel.connect

                def slow(address):
                    now[0] = 11.0
                    connect(address)

                channel.connect = slow
                return channel

        instance = PinnedGetWire(
            socket_factory=SlowConnect(), context=FakeContext(), clock=lambda: now[0]
        )
        instance.exchange(
            Request(page_url(1)), "8.8.8.8", 12, Credential(TOKEN), lambda: None
        )
        self.assertEqual(factory.channels[0].timeouts[:2], [12.0, 1.0])
        self.assertTrue(all(t <= 1 for t in factory.channels[0].timeouts[1:]))

    def test_transport_exceptions_are_replaced_by_fixed_codes(self):
        class FailingContext(FakeContext):
            def wrap_socket(self, channel, server_hostname):
                raise RuntimeError("raw Authorization Bearer " + TOKEN)

        instance, _ = wire(context=FailingContext())
        with self.assertRaises(Failure) as caught:
            self.exchange(instance)
        self.assertEqual(str(caught.exception), Code.TLS.value)
        self.assertNotIn(TOKEN, str(caught.exception))

    def test_error_statuses_never_refresh_auth_retry_or_echo_provider_messages(self):
        for status in (401, 403, 404, 429, 500):
            instance, factory = wire([http_reply(body=TOKEN.encode(), status=status)])
            reader = InventoryReader(FakeDNS(), instance, Credential(TOKEN))
            with self.assertRaises(Failure) as caught:
                reader.read()
            self.assertEqual(caught.exception.code, Code.HTTP)
            self.assertNotIn(TOKEN, str(caught.exception))
            self.assertEqual(len(factory.channels), 1)
            with self.assertRaises(Failure):
                reader.read()
            self.assertEqual(len(factory.channels), 1)

    def test_provider_echoing_a_credential_is_rejected(self):
        instance, _ = wire([http_reply({"data": {"items": [], "description": TOKEN}})])
        with self.assertRaises(Failure) as caught:
            self.exchange(instance)
        self.assertEqual(str(caught.exception), Code.SECRET.value)

    def test_content_encoding_types_duplicate_headers_and_bounds(self):
        for headers in (
            [("Content-Type", "text/html")],
            [("Content-Type", "application/json; charset=utf-16")],
            [("Content-Type", "application/json"), ("Content-Encoding", "gzip")],
            [
                ("Content-Type", "application/json"),
                ("Content-Length", str(MAX_BYTES + 1)),
            ],
            [
                ("Content-Type", "application/json"),
                ("Content-Length", "2"),
                ("Content-Length", "2"),
            ],
            [
                ("Content-Type", "application/json"),
                ("Content-Type", "application/json"),
            ],
            [
                ("Content-Type", "application/json"),
                ("Transfer-Encoding", "chunked"),
                ("Content-Length", "5"),
            ],
        ):
            instance, _ = wire([http_reply(body=b"{}", headers=headers)])
            with self.assertRaises(Failure):
                self.exchange(instance)
        instance, _ = wire(
            [
                http_reply(
                    body=b"x" * (MAX_BYTES + 1),
                    headers=[("Content-Type", "application/json")],
                )
            ]
        )
        with self.assertRaises(Failure) as caught:
            self.exchange(instance)
        self.assertEqual(caught.exception.code, Code.LIMIT)

    def test_expired_deadline_never_opens_a_connection(self):
        instance, factory = wire()
        with self.assertRaises(Failure) as caught:
            instance.exchange(
                Request(page_url(1)),
                "8.8.8.8",
                instance.clock() - 1,
                Credential(TOKEN),
                lambda: None,
            )
        self.assertEqual(caught.exception.code, Code.TIME)
        self.assertEqual(factory.channels, [])
