"""Only loopback HTTPS requests. Trust the generated certificate explicitly."""

import http.client
import json
import re
import ssl
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

from run import ROOT, clean_environment


class GatewayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        directory = ROOT / ".integration-runtime/api"
        for _ in range(120):
            if (directory / "api.sock").exists() and (
                directory / "tls-cert.pem"
            ).exists():
                break
            time.sleep(0.25)
        cls.context = ssl.create_default_context(cafile=str(directory / "tls-cert.pem"))
        cls.process = subprocess.Popen(
            [sys.executable, str(ROOT / "integration/gateway.py"), str(directory)],
            env=clean_environment(),
            stdout=subprocess.DEVNULL,
        )
        try:
            for _ in range(60):
                if cls.process.poll() is not None:
                    raise RuntimeError("La pasarela HTTPS no inició.")
                try:
                    if cls.request("GET", "/health")[0] == 200:
                        return
                except (OSError, http.client.HTTPException):
                    pass
                time.sleep(0.25)
            raise RuntimeError("No se pudo comprobar HTTPS local.")
        except BaseException:
            cls.process.terminate()
            cls.process.wait(timeout=5)
            raise

    @classmethod
    def tearDownClass(cls):
        cls.process.terminate()
        cls.process.wait(timeout=5)

    @classmethod
    def request(cls, method, path, body=None, headers=None):
        connection = http.client.HTTPSConnection(
            "127.0.0.1", 8443, context=cls.context, timeout=5
        )
        try:
            connection.request(method, path, body=body, headers=headers or {})
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def test_https_health_and_resource_policy(self):
        status, headers, body = self.request("GET", "/health")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["database"], "ok")
        self.assertIn("img-src 'none'", headers["content-security-policy"])
        self.assertIn("media-src 'none'", headers["content-security-policy"])

    def test_login_session_csrf_and_logout_over_real_https(self):
        payload = json.dumps(
            {"username": "operador-prueba", "password": "solo-datos-sinteticos"}
        )
        status, headers, body = self.request(
            "POST", "/api/auth/login", payload, {"Content-Type": "application/json"}
        )
        self.assertEqual(status, 200)
        cookie = headers["set-cookie"].split(";", 1)[0]
        self.assertIn("Secure", headers["set-cookie"])
        status, _, _ = self.request("GET", "/api/auth/me", headers={"Cookie": cookie})
        self.assertEqual(status, 200)
        status, _, _ = self.request(
            "POST", "/api/auth/logout", headers={"Cookie": cookie}
        )
        self.assertEqual(status, 403)
        status, _, _ = self.request(
            "POST",
            "/api/auth/logout",
            headers={"Cookie": cookie, "X-CSRF-Token": json.loads(body)["csrf_token"]},
        )
        self.assertEqual(status, 200)
        status, _, _ = self.request("GET", "/api/auth/me", headers={"Cookie": cookie})
        self.assertEqual(status, 401)

    def test_rejects_upstreams_host_spoofing_cross_origin_and_rewrites(self):
        for method, path, headers in [
            ("GET", "https://kiki-tech-api.onrender.com/health", {}),
            ("GET", "/health", {"Host": "kiki-tech-api.onrender.com"}),
            ("GET", "/health", {"Origin": "https://production.invalid"}),
            ("POST", "/api/mercadolibre/sync", {}),
            ("GET", "/images/https://admin.ecomm-app.com/example.jpg", {}),
            ("GET", "/api/ecomm-app/stage/auto/status", {}),
            ("GET", "/dashboard", {}),
        ]:
            with self.subTest(path=path):
                self.assertEqual(self.request(method, path, headers=headers)[0], 403)

    def test_other_methods_and_dashboard_are_not_forwarded(self):
        for method, path in [
            ("GET", "/dashboard"),
            ("DELETE", "/api/auth/me"),
            ("PUT", "/api/auth/me"),
            ("OPTIONS", "/api/auth/login"),
        ]:
            with self.subTest(method=method, path=path):
                self.assertEqual(self.request(method, path)[0], 403)

    def test_integration_entry_and_assets_are_local_and_demo_is_not_served(self):
        status, headers, body = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn(b'name="kiki-environment" content="local-synthetic"', body)
        self.assertIn("script-src 'self'", headers["Content-Security-Policy"])
        for asset in re.findall(rb'(?:src|href)="(/assets/[^"]+)"', body):
            self.assertEqual(self.request("GET", asset.decode())[0], 200)
        for path in [
            "/index.html",
            "/integration.html",
            "/assets/../../render.yaml",
            "/assets/https://production.invalid/example.js",
            "/src/main.tsx",
        ]:
            self.assertEqual(self.request("GET", path)[0], 403)

    def test_parent_application_and_docker_selectors_are_not_inherited(self):
        canaries = {
            key: "synthetic-do-not-inherit"
            for key in [
                "DATABASE_URL",
                "ECOMM_APP_API_TOKEN",
                "ML_CLIENT_SECRET",
                "KIKI_AI_API_KEY",
                "COMPOSE_FILE",
                "COMPOSE_ENV_FILES",
                "DOCKER_HOST",
                "DOCKER_CONTEXT",
                "DOCKER_TLS_VERIFY",
                "DOCKER_CERT_PATH",
                "PYTHONPATH",
                "HTTPS_PROXY",
            ]
        }
        with patch.dict("os.environ", canaries):
            result = clean_environment()
        self.assertFalse(set(result) & set(canaries))

    def test_workspace_large_valid_payload_csrf_and_body_limits(self):
        status, headers, body = self.request(
            "POST",
            "/api/auth/login",
            json.dumps(
                {"username": "operador-prueba", "password": "solo-datos-sinteticos"}
            ),
            {"Content-Type": "application/json"},
        )
        self.assertEqual(status, 200)
        auth = {
            "Cookie": headers["set-cookie"].split(";", 1)[0],
            "X-CSRF-Token": json.loads(body)["csrf_token"],
            "Content-Type": "application/json",
        }
        status, _, body = self.request(
            "GET", "/api/ecomm-app/workspace/900006", headers=auth
        )
        self.assertEqual(status, 200)
        version = json.loads(body)["version"]
        fields = {
            "description": "S" * 5000,
            "details": "D" * 5000,
            "attributes": [{"name": f"A{i}", "value": "V" * 450} for i in range(40)],
        }
        payload = json.dumps(
            {"expected_version": version, "status": "DRAFT", "fields": fields}
        )
        self.assertGreater(len(payload), 16384)
        self.assertEqual(
            self.request(
                "POST",
                "/api/ecomm-app/workspace/900006",
                payload,
                {"Cookie": auth["Cookie"], "Content-Type": "application/json"},
            )[0],
            403,
        )
        status, _, body = self.request(
            "POST", "/api/ecomm-app/workspace/900006", payload, auth
        )
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["fields"]["attributes"], fields["attributes"])
        self.assertEqual(
            self.request(
                "POST",
                "/api/ecomm-app/workspace/900006",
                "",
                {**auth, "Content-Length": "1048577"},
            )[0],
            413,
        )
        # Reject the declared size before transmitting a body; avoids a platform-
        # dependent BrokenPipe when the server correctly closes an oversized stream.
        self.assertEqual(
            self.request("POST", "/api/auth/login", "", {"Content-Length": "16385"})[0],
            413,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
