"""2M: real adapter code with entirely in-memory network/DNS primitives.

No test opens an OS socket or resolves a hostname. sys.audit below emits events
only, demonstrating the guard without performing the underlying operation.
"""

from contextlib import redirect_stdout
from datetime import timedelta
import hashlib
import io
import json
import os
from pathlib import Path
import socket
import ssl
import stat
import sys
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ecomm_reader.authorization import (
    SCOPE,
    attest,
    load_authorization,
    read_private,
    utcnow,
)
from ecomm_reader import native
from ecomm_reader.native import NativeChannel, NativeResolver, prepare
from ecomm_reader.policy import BARCODE, HOST, PATH, Request, page_url
from ecomm_reader.query import arguments, main
from ecomm_reader.reader import InventoryReader
from ecomm_reader.safety import Code, Failure, native_call
from ecomm_reader.simulated import FakeContext, FakeSocket, envelope, http_reply, item
from ecomm_reader.wire import Credential, get_bytes

CONTROL = "OFFLINE_NON_SECRET_2M_CONTROL"


def metadata(*, max_pages=1):
    now = utcnow().replace(microsecond=0)
    return {
        "version": 1,
        "host": HOST,
        "path": PATH,
        "method": "GET",
        "barcode": BARCODE,
        "max_pages": max_pages,
        "scopes": [SCOPE],
        "credential_sha256": hashlib.sha256(CONTROL.encode()).hexdigest(),
        "account_reference": "SYNTHETIC-ACCOUNT-NOT-CLIENT",
        "permissions_reference": "OFFLINE MOCK OWNER REVIEW",
        "reviewed_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "expires_at": (now + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "reviewed_by_owner": True,
    }


def grant(*, max_pages=1):
    return attest(
        Credential(CONTROL),
        json.dumps(metadata(max_pages=max_pages)).encode(),
        max_pages=max_pages,
    )


def dns_rows(ip="8.8.8.8"):
    return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, 443))]


class Driver:
    def __init__(self, replies, **options):
        self.replies, self.options, self.channels = list(replies), options, []

    def socket(self, family, kind, proto):
        raw = FakeSocket(self.replies.pop(0), **self.options)
        raw.family = family
        # Emitting the audit event is not the underlying socket operation.
        sys.audit("socket.__new__", raw, family, kind, proto)
        connect = raw.connect

        def checked_connect(address):
            sys.audit("socket.connect", raw, address)
            connect(address)

        raw.connect = checked_connect
        self.channels.append(raw)
        return raw


class Lookup:
    def __init__(self, answers=None):
        self.answers = answers or [dns_rows()]
        self.calls = []

    def __call__(self, *args):
        sys.audit("socket.getaddrinfo", *args)
        self.calls.append(args)
        return self.answers[min(len(self.calls) - 1, len(self.answers) - 1)]


class AuditedContext(FakeContext):
    def wrap_socket(self, channel, server_hostname):
        sys.audit(
            "socket.__new__",
            channel,
            channel.family,
            socket.SOCK_STREAM,
            socket.IPPROTO_TCP,
        )
        return super().wrap_socket(channel, server_hostname)


def adapted(*responses, max_pages=1, context=None, lookup=None, **socket_options):
    authority = grant(max_pages=max_pages)
    driver = Driver([http_reply(value) for value in responses], **socket_options)
    dns = lookup or Lookup()
    resolver, wire = prepare(
        authority, driver=driver, lookup=dns, context=context or AuditedContext()
    )
    return InventoryReader.authorized_query(authority, resolver, wire), driver, dns


class ScopeAndSecrets(unittest.TestCase):
    def test_matching_owner_attestation_is_explicitly_not_server_verification(self):
        authority = grant()
        self.assertEqual(authority.max_pages, 1)
        self.assertNotIn(CONTROL, repr(authority))
        authority.validate()

    def test_unknown_additional_missing_or_write_scopes_are_refused(self):
        for scopes in (
            None,
            [],
            "inventario:leer",
            ["inventario:escribir"],
            [SCOPE, "facturacion:emitir"],
            [SCOPE, SCOPE],
        ):
            value = metadata()
            value["scopes"] = scopes
            with self.subTest(scopes=scopes), self.assertRaises(Failure):
                attest(Credential(CONTROL), json.dumps(value).encode())

    def test_attestation_is_bound_to_credential_host_path_filter_and_page_budget(self):
        for key, change in (
            ("credential_sha256", "0" * 64),
            ("host", "kiki-tech-api.onrender.com"),
            ("path", "/api/ecomm-app/workspace/1"),
            ("method", "POST"),
            ("barcode", "8851876201433"),
            ("max_pages", True),
            ("reviewed_by_owner", False),
            ("account_reference", ""),
            ("permissions_reference", CONTROL),
        ):
            value = metadata()
            value[key] = change
            with self.subTest(key=key), self.assertRaises(Failure) as caught:
                attest(Credential(CONTROL), json.dumps(value).encode())
            self.assertNotIn(CONTROL, str(caught.exception))
        with self.assertRaises(Failure):
            attest(Credential(CONTROL), json.dumps(metadata()).encode(), max_pages=2)
        with self.assertRaises(Failure):
            attest(None, json.dumps(metadata()).encode())

    def test_expired_future_long_lived_or_ambiguous_review_is_refused(self):
        for key, change in (
            ("expires_at", "2020-01-01T00:00:00Z"),
            ("expires_at", "2099-01-01T00:00:00Z"),
            ("reviewed_at", "2099-01-01T00:00:00Z"),
            ("reviewed_at", "yesterday"),
        ):
            value = metadata()
            value[key] = change
            with self.assertRaises(Failure):
                attest(Credential(CONTROL), json.dumps(value).encode())

    def test_missing_credential_never_looks_in_environment(self):
        with (
            patch.dict(os.environ, {"ECOMM_APP_API_TOKEN": CONTROL}),
            patch(
                "ecomm_reader.authorization.read_private",
                side_effect=Failure(Code.SECRET_FILE),
            ) as read,
        ):
            with self.assertRaises(Failure) as caught:
                load_authorization("/missing/private-token", "/missing/scope")
            self.assertEqual(caught.exception.code, Code.CREDENTIAL)
            self.assertEqual(read.call_count, 1)

    def test_private_file_admission_uses_fd_flags_and_checks_metadata_before_read(self):
        info = SimpleNamespace(
            st_mode=stat.S_IFREG | 0o400,
            st_uid=os.geteuid(),
            st_nlink=1,
            st_size=3,
            st_mtime_ns=1,
            st_ctime_ns=1,
        )
        with (
            patch("ecomm_reader.authorization.os.open", return_value=55) as opened,
            patch("ecomm_reader.authorization.os.fstat", return_value=info),
            patch("ecomm_reader.authorization.os.read", side_effect=[b"abc", b""]),
            patch("ecomm_reader.authorization.os.close") as closed,
        ):
            self.assertEqual(read_private("/private/token", 4097), b"abc")
            flags = opened.call_args.args[1]
            self.assertTrue(flags & os.O_NOFOLLOW)
            self.assertTrue(flags & os.O_CLOEXEC)
            self.assertTrue(flags & os.O_NONBLOCK)
            self.assertFalse(
                flags & (os.O_CREAT | os.O_TRUNC | os.O_WRONLY | os.O_RDWR)
            )
            closed.assert_called_once_with(55)
        for changes in (
            {"st_mode": stat.S_IFREG | 0o644},
            {"st_uid": os.geteuid() + 1},
            {"st_nlink": 2},
            {"st_size": 99999},
            {"st_mode": stat.S_IFIFO | 0o600},
        ):
            bad = SimpleNamespace(**(vars(info) | changes))
            with (
                patch("ecomm_reader.authorization.os.open", return_value=55),
                patch("ecomm_reader.authorization.os.fstat", return_value=bad),
                patch("ecomm_reader.authorization.os.read") as read,
                patch("ecomm_reader.authorization.os.close"),
            ):
                with self.assertRaises(Failure):
                    read_private("/private/token", 4097)
                read.assert_not_called()

    def test_mutating_truncated_or_growing_private_file_is_refused(self):
        info = SimpleNamespace(
            st_mode=stat.S_IFREG | 0o400,
            st_uid=os.geteuid(),
            st_nlink=1,
            st_size=3,
            st_mtime_ns=1,
            st_ctime_ns=1,
        )
        for raw, after in (
            (b"abcd", info),
            (b"ab", info),
            (b"abc", SimpleNamespace(**(vars(info) | {"st_mtime_ns": 2}))),
        ):
            with (
                patch("ecomm_reader.authorization.os.open", return_value=55),
                patch("ecomm_reader.authorization.os.fstat", side_effect=[info, after]),
                patch("ecomm_reader.authorization.os.read", side_effect=[raw, b""]),
                patch("ecomm_reader.authorization.os.close"),
            ):
                with self.assertRaises(Failure):
                    read_private("/private/token", 3)


class DeploymentAndGuard(unittest.TestCase):
    def test_managed_cloud_is_refused_even_if_proxy_variables_are_removed(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(Path, "exists", return_value=True),
        ):
            with self.assertRaises(Failure) as caught:
                native.require_direct_environment()
            self.assertEqual(caught.exception.code, Code.ENVIRONMENT)

    def test_every_inherited_proxy_causes_rejection_without_network_fallback(self):
        for key in native.PROXY_KEYS:
            with (
                patch.dict(os.environ, {key: "http://proxy.invalid:1234"}, clear=True),
                patch.object(Path, "exists", return_value=False),
            ):
                with self.assertRaises(Failure):
                    native.require_direct_environment()

    def test_only_a_reviewed_direct_environment_is_supported(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(Path, "exists", return_value=False),
        ):
            native.require_direct_environment()

    def test_cli_does_not_accept_urls_methods_tokens_or_implicit_authorization(self):
        for args in (
            [],
            ["--live"],
            ["--token", CONTROL],
            [
                "--authorize-one-query",
                "--url",
                page_url(1),
                "--scope-evidence",
                "/metadata",
            ],
            [
                "--authorize-one-query",
                "--credential-file",
                "/same",
                "--scope-evidence",
                "/same",
            ],
        ):
            output = io.StringIO()
            with (
                patch("ecomm_reader.query.load_authorization") as load,
                redirect_stdout(output),
            ):
                self.assertEqual(main(args), 2)
                load.assert_not_called()
            self.assertNotIn(CONTROL, output.getvalue())
        self.assertNotIn(
            "--max-pages",
            arguments(
                [
                    "--authorize-one-query",
                    "--credential-file",
                    "/secret",
                    "--scope-evidence",
                    "/metadata",
                ]
            ),
        )

    def test_cli_environment_gate_precedes_even_opening_credentials(self):
        with (
            patch(
                "ecomm_reader.query.require_direct_environment",
                side_effect=Failure(Code.ENVIRONMENT),
            ),
            patch("ecomm_reader.query.load_authorization") as load,
            redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(
                main(
                    [
                        "--authorize-one-query",
                        "--credential-file",
                        "/secret",
                        "--scope-evidence",
                        "/metadata",
                    ]
                ),
                2,
            )
            load.assert_not_called()

    def test_scoped_audit_permission_does_not_allow_other_destinations_operations_or_later_calls(
        self,
    ):
        authority, raw = grant(), object()
        with patch.object(native, "require_direct_environment"):
            with native_call(
                authority, "connect", channel=raw, address=("8.8.8.8", 443)
            ):
                sys.audit("socket.connect", raw, ("8.8.8.8", 443))
                for other in (("127.0.0.1", 443), ("8.8.8.8", 80), ("1.1.1.1", 443)):
                    with self.assertRaises(Failure):
                        sys.audit("socket.connect", raw, other)
                with self.assertRaises(Failure):
                    sys.audit("socket.getaddrinfo", HOST, 443, 0, 1, 6, 0)
            with native_call(authority, "dns"):
                sys.audit("socket.getaddrinfo", HOST, 443, 0, 1, 6, 0)
                with self.assertRaises(Failure):
                    sys.audit(
                        "socket.getaddrinfo",
                        "kiki-tech-api.onrender.com",
                        443,
                        0,
                        1,
                        6,
                        0,
                    )
                with self.assertRaises(Failure):
                    sys.audit("socket.__new__", raw, 2, 1, 6)
            with self.assertRaises(Failure):
                sys.audit("socket.connect", raw, ("8.8.8.8", 443))
        with self.assertRaises(Failure):
            with native_call(object(), "dns"):
                self.fail("no authority")


@patch.object(native, "require_direct_environment")
class Adapter(unittest.TestCase):
    def test_adapter_construction_never_resolves_or_connects(self, environment):
        driver, lookup = Driver([]), Lookup()
        authority = grant()
        prepare(authority, driver=driver, lookup=lookup, context=FakeContext())
        self.assertEqual(driver.channels, [])
        self.assertEqual(lookup.calls, [])

    def test_actual_adapter_get_codec_and_variant_identity_with_fake_primitives(
        self, environment
    ):
        reader, driver, lookup = adapted(envelope())
        result = reader.read()
        self.assertEqual(
            result["mode"], "AUTHORIZED_PROVIDER_RESPONSE"
        )  # fixture, not real data
        self.assertEqual(result["real_requests"], 1)  # code-path counter, mocked I/O
        self.assertEqual(
            result["scope_verification"], "OWNER_ATTESTED_NOT_SERVER_VERIFIED"
        )
        self.assertEqual(result["candidates"][0]["response_variant_id"], "900001")
        self.assertIsNone(result["authentic_ecomm_id"])
        self.assertFalse(result["binding_permitted"])
        self.assertNotIn(CONTROL, json.dumps(result))
        self.assertNotIn("external_writes", result)
        self.assertEqual(driver.channels[0].address, ("8.8.8.8", 443))
        self.assertEqual(len(lookup.calls), 2)
        self.assertTrue(
            driver.channels[0].sent.startswith(
                b"GET /api/v3/public/inventario/productos?barcode=7794940000796&page=1&limit=50&sort=sku_asc HTTP/1.1"
            )
        )
        self.assertNotIn(b"Cookie:", driver.channels[0].sent)
        with self.assertRaises(Failure):
            reader.read()

    def test_full_future_cli_is_exercised_only_with_local_doubles(self, environment):
        reader, driver, lookup = adapted(envelope())
        output = io.StringIO()
        with (
            patch("ecomm_reader.query.require_direct_environment"),
            patch(
                "ecomm_reader.query.load_authorization",
                return_value=reader._authorization,
            ),
            patch(
                "ecomm_reader.query.prepare",
                return_value=(reader.resolver, reader.wire),
            ),
            redirect_stdout(output),
        ):
            self.assertEqual(
                main(
                    [
                        "--authorize-one-query",
                        "--credential-file",
                        "/not-opened",
                        "--scope-evidence",
                        "/not-opened-either",
                    ]
                ),
                0,
            )
        self.assertEqual(
            json.loads(output.getvalue())["candidates"][0]["response_variant_id"],
            "900001",
        )
        self.assertEqual(len(driver.channels), 1)

    def test_no_credential_wrong_credential_domain_or_method_never_opens_a_socket(
        self, environment
    ):
        reader, driver, _ = adapted(envelope())
        for request, credential in (
            (Request(page_url(1), "POST"), reader.credential),
            (
                Request(page_url(1).replace(HOST, "kiki-tech-api.onrender.com")),
                reader.credential,
            ),
            (Request(page_url(1)), None),
            (Request(page_url(1)), Credential("OFFLINE_OTHER_NON_SECRET")),
        ):
            with self.assertRaises(Failure):
                reader.wire.exchange(
                    request, "8.8.8.8", time.monotonic() + 12, credential, lambda: None
                )
        self.assertEqual(driver.channels, [])

    def test_native_channel_refuses_plaintext_non_get_and_a_second_write(
        self, environment
    ):
        authority = grant()
        raw = FakeSocket(b"")
        channel = NativeChannel(raw, "8.8.8.8", authority)
        with self.assertRaises(Failure):
            channel.sendall(get_bytes(Request(page_url(1)), authority.credential))
        channel.tls_verified = True
        for payload in (
            b"POST / HTTP/1.1\r\n\r\n",
            b"GET /other HTTP/1.1\r\n\r\n",
            get_bytes(Request(page_url(2)), authority.credential),
        ):
            with self.assertRaises(Failure):
                channel.sendall(payload)
        payload = get_bytes(Request(page_url(1)), authority.credential)
        channel.sendall(payload)
        with self.assertRaises(Failure):
            channel.sendall(payload)
        self.assertEqual(raw.sent, payload)

    def test_tls_invalid_hostname_and_unverified_context_are_refused(self, environment):
        reader, driver, _ = adapted(envelope(), context=FakeContext(fail=True))
        with self.assertRaises(Failure):
            reader.read()
        self.assertEqual(driver.channels[0].sent, b"")
        context = FakeContext()
        context.verify_mode = ssl.CERT_NONE
        with self.assertRaises(Failure):
            adapted(envelope(), context=context)
        reader, driver, _ = adapted(envelope())
        raw = reader.wire.factory.open("8.8.8.8")
        with self.assertRaises(Failure):
            reader.wire.context.wrap_socket(raw, "kiki-tech-api.onrender.com")
        raw.close()

    def test_redirects_and_http_errors_are_never_followed_retried_or_logged(
        self, environment
    ):
        for status in (200, 301, 302, 307, 308, 401, 403, 429, 500):
            authority = grant()
            driver = Driver(
                [
                    http_reply(
                        body=CONTROL.encode(),
                        status=status,
                        headers=[
                            ("Location", "https://kiki-tech-api.onrender.com/"),
                            ("Content-Type", "text/plain"),
                        ],
                    )
                ]
            )
            resolver, wire = prepare(
                authority, driver=driver, lookup=Lookup(), context=FakeContext()
            )
            reader = InventoryReader.authorized_query(authority, resolver, wire)
            with self.assertRaises(Failure) as caught:
                reader.read()
            self.assertNotIn(CONTROL, str(caught.exception))
            self.assertEqual(len(driver.channels), 1)

    def test_dns_private_mixed_rebinding_and_peer_change_block_before_bearer(
        self, environment
    ):
        for answers in (
            [dns_rows("127.0.0.1")],
            [dns_rows("8.8.8.8") + dns_rows("10.0.0.1")],
            [dns_rows(), dns_rows("1.1.1.1")],
        ):
            reader, driver, _ = adapted(envelope(), lookup=Lookup(answers))
            with self.assertRaises(Failure):
                reader.read()
            self.assertTrue(all(channel.sent == b"" for channel in driver.channels))
        reader, driver, _ = adapted(envelope(), tls_peer="1.1.1.1")
        with self.assertRaises(Failure):
            reader.read()
        self.assertEqual(driver.channels[0].sent, b"")

    def test_dns_deadline_is_bounded_without_real_resolution(self, environment):
        import threading

        release = threading.Event()

        def stalled(*args):
            release.wait(0.1)
            return dns_rows()

        resolver = NativeResolver(grant(), lookup=stalled)
        try:
            with self.assertRaises(Failure) as caught:
                resolver.resolve(HOST, time.monotonic() + 0.01)
            self.assertEqual(caught.exception.code, Code.TIME)
        finally:
            release.set()

    def test_ipv6_pin_and_audit_scope_are_consistent_without_os_sockets(
        self, environment
    ):
        address = "2606:4700:4700::1111"
        rows = [
            (
                socket.AF_INET6,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                (address, 443, 0, 0),
            )
        ]
        reader, driver, _ = adapted(envelope(), lookup=Lookup([rows]))
        self.assertEqual(
            reader.read()["candidates"][0]["response_variant_id"], "900001"
        )
        self.assertEqual(driver.channels[0].address, (address, 443, 0, 0))
        for invalid in (("::1", 443, 0, 0), (address, 443, 0, 2)):
            rows = [
                (socket.AF_INET6, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", invalid)
            ]
            reader, driver, _ = adapted(envelope(), lookup=Lookup([rows]))
            with self.assertRaises(Failure):
                reader.read()
            self.assertEqual(driver.channels, [])

    def test_default_one_page_cannot_follow_valid_second_page(self, environment):
        rows = [item(910000 + i, brand=None) for i in range(50)]
        reader, driver, _ = adapted(envelope(rows, total=51))
        result = reader.read()
        self.assertEqual(len(driver.channels), 1)
        self.assertEqual(result["scope"], "QUERY_TRUNCATED_AT_ONE_PAGES")
        self.assertFalse(
            any(row["eligible_for_human_review"] for row in result["candidates"])
        )

    def test_second_page_requires_both_explicit_budget_and_valid_pagination(
        self, environment
    ):
        rows = [item(910000 + i, brand=None) for i in range(50)]
        reader, driver, _ = adapted(
            envelope(rows, total=51), envelope([item()], page=2, total=51), max_pages=2
        )
        result = reader.read()
        self.assertEqual(len(driver.channels), 2)
        self.assertEqual(result["candidates"][-1]["response_page"], 2)
        self.assertEqual(result["candidates"][-1]["response_variant_id"], "900001")
        with self.assertRaises(Failure):
            reader._page(3)
        reader, driver, _ = adapted(envelope(), max_pages=2)
        reader.read()
        self.assertEqual(len(driver.channels), 1)

    def test_incorrect_pagination_never_authorizes_a_second_request(self, environment):
        data = envelope()
        data["data"]["paginacion"].update(total=51, total_pages=2)
        reader, driver, _ = adapted(data, max_pages=2)
        with self.assertRaises(Failure) as caught:
            reader.read()
        self.assertEqual(caught.exception.code, Code.PAGINATION)
        self.assertEqual(len(driver.channels), 1)

    def test_multiple_variants_shared_ean_packs_and_conflicts_are_not_bound(
        self, environment
    ):
        rows = [
            item(),
            item(900002),
            item(900003, description="Pack x6 de 200 ml", combo=True),
            item(900004, gtin="8851876201433"),
        ]
        reader, _, _ = adapted(envelope(rows, total=4))
        result = reader.read()
        self.assertEqual(len(result["candidates"]), 4)
        self.assertTrue(
            all(not row["binding_permitted"] for row in result["candidates"])
        )
        self.assertTrue(
            all(not row["eligible_for_human_review"] for row in result["candidates"])
        )
        self.assertIn("BARCODE_GTIN_CONFLICT", result["candidates"][3]["blockers"])

    def test_invalid_identity_blocks_without_parent_or_sku_fallback(self, environment):
        for ident in (None, "", "None", "null", True, 0, "001"):
            reader, driver, _ = adapted(envelope([item(ident)]))
            with self.assertRaises(Failure) as caught:
                reader.read()
            self.assertEqual(caught.exception.code, Code.ID)
            self.assertEqual(len(driver.channels), 1)

    def test_backend_db_writes_and_unscoped_sockets_remain_forbidden(self, environment):
        import importlib

        reader, _, _ = adapted(envelope())
        reader.read()
        for module in ("app.main", "backend", "psycopg", "sqlalchemy"):
            with self.assertRaises(Failure):
                importlib.import_module(module)
        with self.assertRaises(Failure):
            open("/tmp/2m-must-not-write", "w")
        with self.assertRaises(Failure):
            socket.socket()
