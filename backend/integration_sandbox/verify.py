"""Executable regression suite. Real disposable PostgreSQL; zero provider transports."""

import os
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import Mock

from .policy import (
    DATABASE_URL,
    MARKER,
    IsolationError,
    validate_database_identity,
    validate_environment,
)


class AConfiguration(unittest.TestCase):
    def valid(self):
        return {
            "KIKI_INTEGRATION_MODE": "local-synthetic",
            "DATABASE_URL": DATABASE_URL,
        }

    def test_explicit_synthetic_configuration(self):
        validate_environment(self.valid())

    def test_rejects_other_modes_and_database_targets_before_app_import(self):
        import sys

        for target in [
            "postgresql://user:canary@production.invalid/kiki",
            "postgresql://user:canary@kiki-tech-api.onrender.com/kiki",
            "postgresql://user:canary@127.0.0.1/kiki_integration",
            "sqlite:///./kiki.db",
            DATABASE_URL + "&hostaddr=192.0.2.1",
        ]:
            with self.subTest(target=target.split("@")[-1]):
                with self.assertRaises(IsolationError):
                    validate_environment({**self.valid(), "DATABASE_URL": target})
        for mode in [None, "production", "development", "demo", "test"]:
            config = self.valid()
            config["KIKI_INTEGRATION_MODE"] = mode
            with self.assertRaises(IsolationError):
                validate_environment(config)
        self.assertFalse(
            any(key == "app" or key.startswith("app.") for key in sys.modules)
        )

    def test_rejects_inherited_credentials_and_configuration(self):
        for key in [
            "ECOMM_APP_API_TOKEN",
            "ML_CLIENT_SECRET",
            "OPENAI_API_KEY",
            "KIKI_AI_API_KEY",
            "KIKI_ADMIN_PASSWORD_HASH",
            "APP_SESSION_SECRET",
            "APP_ENCRYPTION_KEY",
            "FRONTEND_URL",
            "PGSERVICE",
            "PGHOSTADDR",
            "PGPASSWORD",
            "database_url",
            "ml_client_secret",
            "HTTPS_PROXY",
        ]:
            with self.subTest(key=key), self.assertRaises(IsolationError):
                validate_environment(
                    {**self.valid(), key: "synthetic-rejection-canary"}
                )

    def test_database_identity_and_privileges_fail_before_ddl(self):
        good = ("kiki_integration", "kiki_integration", None, MARKER)
        connection = Mock()
        connection.execute.return_value.fetchone.side_effect = [good, (False,) * 4]
        validate_database_identity(connection)
        for row in [
            ("production", *good[1:]),
            (*good[:2], "127.0.0.1", MARKER),
            (*good[:3], None),
            (good[0], "postgres", *good[2:]),
        ]:
            connection.reset_mock()
            connection.execute.return_value.fetchone.side_effect = [row]
            with self.assertRaises(IsolationError):
                validate_database_identity(connection)
            self.assertNotIn("CREATE", connection.execute.call_args.args[0].upper())
        connection.execute.return_value.fetchone.side_effect = [
            good,
            (True, False, False, False),
        ]
        with self.assertRaises(IsolationError):
            validate_database_identity(connection)


class BApplication(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from .bootstrap import create_sandbox_app

        # A poisoned .env must be ignored. No change to the checkout's environment files.
        cls.directory = tempfile.TemporaryDirectory()
        cls.previous_cwd = os.getcwd()
        Path(cls.directory.name, ".env").write_text(
            "DATABASE_URL=postgresql://canary@production.invalid/kiki\n"
            "ECOMM_APP_API_TOKEN=synthetic-dotenv-canary\nKIKI_AI_ENABLED=true\n"
        )
        os.chdir(cls.directory.name)
        cls.app = create_sandbox_app()
        os.chdir(cls.previous_cwd)
        from fastapi.testclient import TestClient

        cls.client = TestClient(cls.app, base_url="https://127.0.0.1:8443")
        cls.client.__enter__()  # Runs the real create_all + seed against checked PostgreSQL.

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)
        cls.directory.cleanup()

    def login(self):
        self.client.cookies.clear()
        response = self.client.post(
            "/api/auth/login",
            json={"username": "operador-prueba", "password": "solo-datos-sinteticos"},
        )
        self.assertEqual(response.status_code, 200)
        return response

    def test_postgresql_startup_and_fixture_identity(self):
        from app.database.session import engine
        from sqlalchemy import text

        self.assertEqual(engine.dialect.name, "postgresql")
        with engine.connect() as db:
            self.assertEqual(
                db.execute(
                    text("SELECT current_database(), current_user, inet_server_addr()")
                ).one(),
                ("kiki_integration", "kiki_integration", None),
            )
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["database"], "ok")

    def test_no_inherited_credentials_or_dotenv(self):
        from app.core.config import get_settings

        settings = get_settings()
        self.assertEqual(settings.database_url, DATABASE_URL)
        for key in [
            "ecomm_app_api_token",
            "ml_client_id",
            "ml_client_secret",
            "ml_redirect_uri",
            "kiki_refresh_token",
            "kiki_ai_api_key",
        ]:
            self.assertEqual(getattr(settings, key), "")
        self.assertFalse(settings.kiki_ai_enabled)
        self.assertEqual(settings.kiki_admin_username, "operador-prueba")
        self.assertEqual(settings.ml_api_url, "https://blocked.invalid")
        self.assertFalse(Path("/sandbox/.env").exists())

    def test_postgresql_requires_the_synthetic_password(self):
        import psycopg

        with self.assertRaises(psycopg.OperationalError):
            psycopg.connect(
                host="/var/run/postgresql",
                port=5432,
                dbname="kiki_integration",
                user="kiki_integration",
                password="wrong-synthetic-password",
                connect_timeout=2,
                passfile="/dev/null",
            )

    def test_sessions_cookies_and_revocation(self):
        from app.database.models import AdminSession
        from app.database.session import SessionLocal
        from sqlalchemy import select

        self.client.cookies.clear()
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)
        bad = self.client.post(
            "/api/auth/login",
            json={"username": "operador-prueba", "password": "incorrecta"},
        )
        self.assertEqual(bad.status_code, 401)
        response = self.login()
        cookie = response.headers["set-cookie"]
        for flag in ["HttpOnly", "Secure", "SameSite=none"]:
            self.assertIn(flag, cookie)
        with SessionLocal() as db:
            hashes = db.scalars(select(AdminSession.token_hash)).all()
            self.assertTrue(hashes)
            self.assertNotIn(self.client.cookies["kiki_session"], hashes)
        self.assertEqual(self.client.get("/api/auth/me").status_code, 200)
        self.assertEqual(self.client.post("/api/auth/logout").status_code, 403)
        self.assertEqual(
            self.client.post(
                "/api/auth/logout", headers={"X-CSRF-Token": "invalid"}
            ).status_code,
            403,
        )
        response = self.client.post(
            "/api/auth/logout", headers={"X-CSRF-Token": response.json()["csrf_token"]}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)

    def test_synthetic_catalog_search_and_variant_identity(self):
        self.login()
        response = self.client.get(
            "/api/ecomm-app/stage/catalog?q=DEMO-ALM&limit=1&page=2"
        )
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result["total_matches"], 2)
        self.assertEqual(result["total_variants_in_capture"], 6)
        self.assertEqual(result["items"][0]["ecomm_id"], "900002")
        self.assertEqual(result["items"][0]["sku"], "DEMO-ALM")
        self.assertFalse(result["external_writes_enabled"])
        self.assertFalse(result["operational_source_activated"])

    def test_catalog_authentication_empty_search_and_incomplete_capture(self):
        from app.database.models import CatalogSnapshot
        from app.database.session import SessionLocal
        from app.integrations.ecomm_app.catalog_stage import STAGE_SOURCE
        from sqlalchemy import select

        self.client.cookies.clear()
        self.assertEqual(
            self.client.get("/api/ecomm-app/stage/catalog").status_code, 401
        )
        self.login()
        empty = self.client.get(
            "/api/ecomm-app/stage/catalog?q=NO-SUCH-SYNTHETIC-VARIANT"
        ).json()
        self.assertEqual(empty["total_matches"], 0)
        self.assertEqual(empty["total_variants_in_capture"], 6)
        self.assertEqual(empty["items"], [])
        with SessionLocal() as db:
            record = db.scalar(
                select(CatalogSnapshot).where(CatalogSnapshot.source == STAGE_SOURCE)
            )
            original = record.payload
            record.payload = []
            db.commit()
            try:
                response = self.client.get("/api/ecomm-app/stage/catalog")
                self.assertEqual(response.status_code, 409)
                self.assertNotIn("items", response.json())
            finally:
                record.payload = original
                db.commit()

    def test_expired_session_cannot_read_the_catalog(self):
        from datetime import timedelta
        from app.core.security import utcnow, token_hash
        from app.database.models import AdminSession
        from app.database.session import SessionLocal
        from sqlalchemy import select

        self.login()
        with SessionLocal() as db:
            record = db.scalar(
                select(AdminSession).where(
                    AdminSession.token_hash
                    == token_hash(self.client.cookies["kiki_session"])
                )
            )
            record.expires_at = utcnow() - timedelta(seconds=1)
            db.commit()
        self.assertEqual(
            self.client.get("/api/ecomm-app/stage/catalog").status_code, 401
        )

    def test_all_business_operations_remain_disabled(self):
        csrf = self.login().json()["csrf_token"]
        for method, path in [
            ("POST", "/api/ecomm-app/stage/manual/start"),
            ("POST", "/api/ecomm-app/stage/auto/start"),
            ("POST", "/api/ecomm-app/stage/auto/step"),
            ("POST", "/api/ecomm-app/stage/next"),
            ("POST", "/api/ecomm-app/stage/live-stock-check"),
            ("POST", "/api/mercadolibre/auth-url"),
            ("POST", "/api/mercadolibre/sync"),
            ("GET", "/api/mercadolibre/callback?code=synthetic&state=synthetic"),
            ("POST", "/api/tiendanube/import-csv"),
            ("POST", "/api/ecomm-app/workspace/900001/confirm-review"),
            ("POST", "/api/ecomm-app/workspace/ai/900001/suggest"),
            ("POST", "/api/prepublication/metadata/analyze"),
            ("GET", "/docs"),
            ("GET", "/openapi.json"),
        ]:
            with self.subTest(path=path):
                response = self.client.request(
                    method, path, headers={"X-CSRF-Token": csrf}
                )
                self.assertEqual(response.status_code, 403)

    def test_business_tables_have_no_side_effects(self):
        from app.database.models import Base
        from app.database.session import engine
        from sqlalchemy import func, select

        with engine.connect() as db:
            for table in Base.metadata.sorted_tables:
                if table.name not in {
                    "admin_sessions",
                    "auth_login_throttles",
                    "catalog_snapshots",
                }:
                    with self.subTest(table=table.name):
                        self.assertEqual(
                            db.scalar(select(func.count()).select_from(table)), 0
                        )

    def test_outbound_provider_dns_http_and_raw_sockets_are_blocked(self):
        from urllib.request import urlopen
        import httpx

        for host in [
            "admin.ecomm-app.com",
            "api.mercadolibre.com",
            "api.tiendanube.com",
            "api.openai.com",
            "kiki-tech-api.onrender.com",
            "world.openfoodfacts.org",
        ]:
            with self.subTest(host=host):
                with self.assertRaises(IsolationError):
                    socket.getaddrinfo(host, 443)
                with self.assertRaises(IsolationError):
                    urlopen("https://" + host, timeout=1)
                with self.assertRaises(IsolationError):
                    httpx.get("https://" + host, timeout=1, trust_env=False)
        with socket.socket() as sock, self.assertRaises(IsolationError):
            sock.connect(("192.0.2.1", 443))
        with (
            socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock,
            self.assertRaises(IsolationError),
        ):
            sock.sendto(b"synthetic", ("192.0.2.1", 53))
        with socket.socket(socket.AF_UNIX) as sock, self.assertRaises(IsolationError):
            sock.connect("/var/run/docker.sock")

    def test_existing_ecomm_transport_is_blocked_without_replacement(self):
        from app.integrations.ecomm_app.public_api import _fetch, API_PREFIX

        with self.assertRaises(IsolationError):
            _fetch("GET", API_PREFIX + "/depositos", "synthetic-not-a-token")

    def test_kernel_network_isolation_covers_native_drivers(self):
        self.assertEqual(
            sorted(path.name for path in Path("/sys/class/net").iterdir()), ["lo"]
        )
        self.assertEqual(len(Path("/proc/net/route").read_text().splitlines()), 1)
        import psycopg

        # Documentation-only address; no route exists. Native libpq bypasses Python hooks.
        with self.assertRaises(psycopg.OperationalError):
            psycopg.connect(
                host="192.0.2.1",
                dbname="synthetic",
                user="synthetic",
                connect_timeout=1,
            )

    def test_subprocesses_and_shells_are_blocked(self):
        import subprocess

        with self.assertRaises(IsolationError):
            subprocess.run(["true"], check=True)
        with self.assertRaises(IsolationError):
            os.system("true")

    def test_resource_csp_applies_to_success_and_rejection(self):
        for path in ["/health", "/api/ecomm-app/stage/catalog", "/external-image"]:
            response = self.client.get(path)
            for directive in [
                "img-src 'none'",
                "media-src 'none'",
                "frame-src 'none'",
                "default-src 'none'",
            ]:
                self.assertIn(directive, response.headers["content-security-policy"])
            self.assertEqual(response.headers["x-kiki-environment"], "local-synthetic")

    def test_second_bootstrap_is_rejected_after_application_imports(self):
        with self.assertRaises(IsolationError):
            validate_environment(os.environ)


if __name__ == "__main__":
    unittest.main(verbosity=2)
