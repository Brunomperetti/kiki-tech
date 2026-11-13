import importlib
import io
import json
import os
from pathlib import Path
import resource
import socket
import ssl
import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch
from ecomm_reader.cli import main
from ecomm_reader.policy import (
    HOST,
    Request,
    checked_request,
    page_url,
    public_addresses,
    strict_context,
)
from ecomm_reader.reader import query_contract
from ecomm_reader.safety import Code, Failure
from ecomm_reader.wire import Credential


class Policy(unittest.TestCase):
    def test_only_the_exact_https_get_and_filter_are_admitted(self):
        self.assertEqual(checked_request(Request(page_url(1))).hostname, HOST)
        for url in (
            "http://" + HOST + "/api/v3/public/inventario/productos",
            page_url(1).replace(HOST, "kiki-tech-api.onrender.com"),
            page_url(1).replace(HOST, "127.0.0.1"),
            page_url(1).replace(HOST, "169.254.169.254"),
            page_url(1).replace(HOST, HOST + ".evil.invalid"),
            page_url(1).replace(HOST, HOST + "."),
            page_url(1).replace(HOST, "user:password@" + HOST),
            page_url(1).replace(HOST, HOST + ":443"),
            page_url(1).replace("/productos?", "/productos/consulta?"),
            page_url(1).replace("/productos?", "/token?"),
            page_url(1).replace("7794940000796", "8851876201433"),
            page_url(1) + "&barcode=7794940000796",
            page_url(1) + "#fragment",
            page_url(1) + "&q=Hileret",
            page_url(1).replace("page=1", "page=3"),
            page_url(1).replace(HOST, "[::1]"),
            page_url(1).replace(HOST, "ADMIN.ECOMM-APP.COM"),
        ):
            with self.subTest(url=url), self.assertRaises(Failure):
                checked_request(Request(url))

    def test_no_method_other_than_get(self):
        for method in (
            "POST",
            "PUT",
            "DELETE",
            "PATCH",
            "HEAD",
            "OPTIONS",
            "get",
            "GET\r\nPOST",
        ):
            with self.subTest(method=method), self.assertRaises(Failure):
                checked_request(Request(page_url(1), method))

    def test_all_dns_answers_must_be_public_and_unambiguous(self):
        self.assertEqual(public_addresses(["8.8.8.8"]), frozenset({"8.8.8.8"}))
        for value in (
            "127.0.0.1",
            "10.0.0.1",
            "172.16.1.1",
            "192.168.0.1",
            "169.254.169.254",
            "100.64.0.1",
            "0.0.0.0",
            "224.0.0.1",
            "255.255.255.255",
            "::1",
            "::",
            "fc00::1",
            "fe80::1",
            "ff02::1",
            "::ffff:127.0.0.1",
            "::ffff:8.8.8.8",
            "8.8.8.8%eth0",
            "8.8.8.8 ",
            "admin.ecomm-app.com",
            "203.0.113.1",
        ):
            with self.subTest(value=value), self.assertRaises(Failure):
                public_addresses(["8.8.8.8", value])
        for values in ([], ["8.8.8.8"] * 17, None, "8.8.8.8"):
            with self.assertRaises(Failure):
                public_addresses(values)

    def test_tls_context_ignores_keylog_and_uses_verified_hostname(self):
        with patch.dict(
            os.environ,
            {
                "SSLKEYLOGFILE": "/tmp/MUST-NOT-EXIST",
                "SSL_CERT_FILE": "/not-a-trusted-store",
            },
        ):
            context = strict_context()
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertGreaterEqual(context.minimum_version, ssl.TLSVersion.TLSv1_2)
        self.assertIsNone(context.keylog_filename)
        self.assertFalse(Path("/tmp/MUST-NOT-EXIST").exists())

    def test_credentials_never_appear_in_repr_or_validation_errors(self):
        sentinel = "NON_SECRET_REDACTION_CONTROL"
        self.assertNotIn(sentinel, repr(Credential(sentinel)))
        for value in ("", "a\r\nAuthorization: other", "x" * 4097, "á", None):
            with self.assertRaises(Failure) as caught:
                Credential(value)
            self.assertEqual(str(caught.exception), Code.CREDENTIAL.value)

    def test_cli_has_no_live_url_token_or_environment_activation(self):
        for args in (
            ["--live"],
            ["--token", "NON_SECRET_CLI_CONTROL"],
            ["--url", page_url(1)],
            ["refresh"],
            ["plan", "--live"],
        ):
            result = io.StringIO()
            with redirect_stdout(result):
                self.assertEqual(main(args), 2)
            self.assertNotIn("NON_SECRET_CLI_CONTROL", result.getvalue())
            self.assertFalse(json.loads(result.getvalue())["real_network_enabled"])
        with patch.dict(
            os.environ,
            {
                "ECOMM_APP_API_TOKEN": "NON_SECRET_ENV_CONTROL",
                "REAL_NETWORK_ENABLED": "true",
            },
        ):
            self.assertFalse(query_contract()["real_network_enabled"])


class ProcessIsolation(unittest.TestCase):
    def test_no_backend_database_or_native_escape_imports(self):
        for name in (
            "app.main",
            "backend.app",
            "sqlalchemy",
            "psycopg",
            "psycopg2",
            "sqlite3",
            "ctypes",
        ):
            with self.subTest(name=name), self.assertRaises(Failure):
                importlib.import_module(name)
        self.assertFalse(any(n == "app" or n.startswith("app.") for n in sys.modules))

    def test_all_socket_families_and_real_dns_are_blocked_before_io(self):
        for family in (socket.AF_INET, socket.AF_INET6, socket.AF_UNIX):
            with self.assertRaises(Failure):
                socket.socket(family)
        # Audit hook intercepts this before libc DNS; no real request is sent.
        with self.assertRaises(Failure):
            socket.getaddrinfo(HOST, 443)

    def test_external_processes_and_disk_writes_are_blocked(self):
        with self.assertRaises(Failure):
            subprocess.Popen([sys.executable, "-c", "raise SystemExit(0)"])
        with self.assertRaises(Failure):
            os.system("true")
        with self.assertRaises(Failure):
            open("/tmp/reader-must-not-write", "w")
        self.assertFalse(Path("/tmp/reader-must-not-write").exists())

    def test_os_container_has_no_network_mounts_or_writable_root(self):
        self.assertEqual(set(os.listdir("/sys/class/net")), {"lo"})
        self.assertTrue(os.statvfs("/").f_flag & os.ST_RDONLY)
        for path in (
            "/var/run/docker.sock",
            "/var/run/postgresql",
            "/sandbox",
            "/workspace",
            "/reader/backend",
        ):
            self.assertFalse(Path(path).exists())
        self.assertEqual(
            resource.getrlimit(resource.RLIMIT_AS), (160 * 1024 * 1024,) * 2
        )
        self.assertEqual(resource.getrlimit(resource.RLIMIT_CPU), (5, 6))
        status = Path("/proc/self/status").read_text()
        self.assertRegex(status, r"CapEff:\s+0000000000000000")
        self.assertRegex(status, r"NoNewPrivs:\s+1")

    def test_final_image_has_no_application_third_party_packages_or_secrets(self):
        for path in (
            "/sandbox",
            "/pilot-inputs",
            "/offline-build",
            "/usr/local/lib/python3.12/site-packages",
            "/bin/sh",
            "/root/.env",
            "/reader/.env",
        ):
            self.assertFalse(Path(path).exists(), path)
        for name in (
            "DATABASE_URL",
            "ECOMM_APP_API_TOKEN",
            "OPENAI_API_KEY",
            "MERCADOLIBRE_ACCESS_TOKEN",
            "RENDER_EXTERNAL_URL",
            "PYTHONPATH",
        ):
            self.assertNotIn(name, os.environ)
