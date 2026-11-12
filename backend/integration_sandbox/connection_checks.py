"""Original provider services on verified disposable PostgreSQL, no network."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from threading import Barrier
import unittest
from urllib.parse import parse_qs, urlsplit

from .bootstrap import create_sandbox_app

application = create_sandbox_app(connections=True)

from fastapi import HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import delete, select  # noqa: E402
from app.database.session import SessionLocal  # noqa: E402
from app.database.models import (  # noqa: E402
    CatalogSnapshot,
    EcommApiProductEdit,
    MercadoLibreConnection,
    MercadoLibreOAuthState,
    MercadoLibreSync,
)
from app.integrations.ecomm_app.catalog_stage import STAGE_SOURCE  # noqa: E402
from app.services import ecomm_api_refresh_job_service as jobs  # noqa: E402
from app.api.routes.connections import upcoming_updates  # noqa: E402
from .connection_fixtures import (  # noqa: E402
    InventoryFixture,
    MLFixtureTransport,
    LocalMLService,
    seed_connection,
)
from .policy import CONNECTION_ACTIONS, route_allowed, IsolationError  # noqa: E402


class Connections(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lifecycle = TestClient(application, base_url="https://127.0.0.1:8443")
        cls.lifecycle.__enter__()
        with SessionLocal() as db:
            cls.original = deepcopy(
                db.scalar(
                    select(CatalogSnapshot).where(
                        CatalogSnapshot.source == STAGE_SOURCE
                    )
                ).payload
            )

    def reset(self, *, reseed=True):
        InventoryFixture.fail = False
        InventoryFixture.calls = []
        MLFixtureTransport.fail = False
        MLFixtureTransport.calls = []
        with SessionLocal() as db:
            for model in (
                MercadoLibreOAuthState,
                MercadoLibreSync,
                MercadoLibreConnection,
                EcommApiProductEdit,
            ):
                db.execute(delete(model))
            db.execute(
                delete(CatalogSnapshot).where(CatalogSnapshot.source != STAGE_SOURCE)
            )
            db.scalar(
                select(CatalogSnapshot).where(CatalogSnapshot.source == STAGE_SOURCE)
            ).payload = deepcopy(self.original)
            db.commit()
        if reseed:
            seed_connection(SessionLocal)

    @classmethod
    def tearDownClass(cls):
        cls().reset(reseed=False)
        cls.lifecycle.__exit__(None, None, None)

    def setUp(self):
        self.reset()
        self.client = TestClient(application, base_url="https://127.0.0.1:8443")
        login = self.client.post(
            "/api/auth/login",
            json={"username": "operador-prueba", "password": "solo-datos-sinteticos"},
        )
        self.assertEqual(login.status_code, 200, login.text)
        self.headers = {"X-CSRF-Token": login.json()["csrf_token"]}
        self.addCleanup(self.client.close)

    def status(self):
        response = self.client.get("/api/connections/status")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_authenticated_projection_never_calls_provider_and_leaks_no_credentials(
        self,
    ):
        anonymous = TestClient(application, base_url="https://127.0.0.1:8443")
        try:
            self.assertEqual(anonymous.get("/api/connections/status").status_code, 401)
        finally:
            anonymous.close()
        result = self.status()
        self.assertTrue(result["synthetic"])
        self.assertFalse(result["external_oauth_allowed"])
        self.assertTrue(result["actions_enabled"])
        self.assertEqual(result["ecomm"]["last_successful_variants"], 6)
        self.assertTrue(result["ml"]["connected"])
        self.assertIsNone(result["ml"]["listing_count"])
        for value in (
            "SYNTHETIC-ACCESS",
            "SYNTHETIC-REFRESH",
            "SYNTHETIC-NOT-A-CREDENTIAL",
            "owner",
        ):
            self.assertNotIn(value, str(result))
        self.assertEqual(MLFixtureTransport.calls, [])
        self.assertEqual(InventoryFixture.calls, [])

    def test_schedule_argentina_boundaries_and_no_claim_of_github_health(self):
        morning = upcoming_updates(datetime(2026, 11, 12, 11, 24, tzinfo=timezone.utc))
        self.assertEqual(
            morning, ["2026-11-12T08:25:00-03:00", "2026-11-12T16:25:00-03:00"]
        )
        exact = upcoming_updates(datetime(2026, 11, 12, 19, 25, tzinfo=timezone.utc))
        self.assertEqual(
            exact, ["2026-11-13T08:25:00-03:00", "2026-11-13T16:25:00-03:00"]
        )
        self.assertFalse(self.status()["ecomm"]["github_schedule_verified"])

    def test_mutations_require_csrf_and_old_routes_are_not_bypassed(self):
        for method, path in CONNECTION_ACTIONS:
            self.assertEqual(self.client.request(method, path).status_code, 403, path)
            self.assertFalse(route_allowed(method, path))
            self.assertTrue(route_allowed(method, path, connections=True))
        for path in (
            "/api/ecomm-app/stage/auto/start",
            "/api/ecomm-app/stage/next",
            "/api/mercadolibre/callback",
            "/api/mercadolibre/publish",
        ):
            self.assertFalse(route_allowed("POST", path, connections=True))
        self.assertEqual(
            self.client.post(
                "/api/mercadolibre/publish", headers=self.headers
            ).status_code,
            403,
        )

    def test_manual_original_worker_completes_without_overwriting_editor(self):
        with SessionLocal() as db:
            db.add(
                EcommApiProductEdit(
                    ecomm_id="900003",
                    source_sku="DEMO-CHIA",
                    source_snapshot={},
                    fields={"title": "Edición sintética conservada"},
                    status="DRAFT",
                    version=2,
                    history=[{"version": 2}],
                )
            )
            db.commit()
        response = self.client.post(
            "/api/ecomm-app/stage/manual/start", headers=self.headers
        )
        self.assertEqual(response.status_code, 200, response.text)
        state = self.status()["ecomm"]
        self.assertEqual(state["refresh_job"]["status"], "SUCCESS")
        self.assertEqual(state["last_successful_variants"], 6)
        with SessionLocal() as db:
            edit = db.scalar(select(EcommApiProductEdit))
            self.assertEqual(edit.fields, {"title": "Edición sintética conservada"})
            self.assertEqual(edit.version, 2)
            self.assertEqual(edit.history, [{"version": 2}])
        self.assertEqual(
            InventoryFixture.calls, [("GET", "/api/v3/public/inventario/productos")]
        )

    def test_capture_error_keeps_previous_catalog_and_is_not_publication_error(self):
        InventoryFixture.fail = True
        response = self.client.post(
            "/api/ecomm-app/stage/manual/start", headers=self.headers
        )
        self.assertEqual(response.status_code, 200)
        state = self.status()["ecomm"]
        self.assertEqual(state["refresh_job"]["status"], "FAILED")
        self.assertEqual(state["last_successful_variants"], 6)
        with SessionLocal() as db:
            self.assertEqual(
                db.scalar(
                    select(CatalogSnapshot).where(
                        CatalogSnapshot.source == STAGE_SOURCE
                    )
                ).payload,
                self.original,
            )

    def test_concurrent_manual_and_scheduled_starts_share_original_lock(self):
        barrier = Barrier(2)

        def begin(origin):
            with SessionLocal() as db:
                barrier.wait(timeout=5)
                try:
                    jobs.start_job(db, origin)
                    return 200
                except HTTPException as exc:
                    return exc.status_code

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(begin, ["MANUAL", "SCHEDULED"]))
        self.assertEqual(sorted(results), [200, 409])
        self.assertTrue(self.status()["ecomm"]["refresh_in_progress"])
        self.assertEqual(
            self.client.post(
                "/api/ecomm-app/stage/manual/start", headers=self.headers
            ).status_code,
            409,
        )

    def test_expired_token_uses_original_refresh_and_preserves_old_snapshot_on_error(
        self,
    ):
        with SessionLocal() as db:
            db.scalar(select(MercadoLibreConnection)).expires_at = datetime.now(
                timezone.utc
            ) - timedelta(minutes=1)
            db.commit()
        self.assertTrue(self.status()["ml"]["token_expired"])
        response = self.client.post("/api/mercadolibre/sync", headers=self.headers)
        self.assertEqual(response.status_code, 201, response.text)
        state = self.status()["ml"]
        self.assertFalse(state["token_expired"])
        self.assertEqual(state["listing_count"], 1)
        self.assertEqual(state["publication_count"], 1)
        self.assertIn(("POST", "/oauth/token"), MLFixtureTransport.calls)
        with SessionLocal() as db:
            before = deepcopy(
                db.scalar(
                    select(CatalogSnapshot).where(
                        CatalogSnapshot.source == "MERCADOLIBRE_API"
                    )
                ).payload
            )
        MLFixtureTransport.fail = True
        self.assertEqual(
            self.client.post(
                "/api/mercadolibre/sync", headers=self.headers
            ).status_code,
            502,
        )
        with SessionLocal() as db:
            self.assertEqual(
                db.scalar(
                    select(CatalogSnapshot).where(
                        CatalogSnapshot.source == "MERCADOLIBRE_API"
                    )
                ).payload,
                before,
            )

    def test_disconnected_retains_capture_and_oauth_state_is_original_one_use_flow(
        self,
    ):
        self.assertEqual(
            self.client.post(
                "/api/mercadolibre/sync", headers=self.headers
            ).status_code,
            201,
        )
        with SessionLocal() as db:
            db.execute(delete(MercadoLibreConnection))
            db.commit()
        state = self.status()["ml"]
        self.assertFalse(state["connected"])
        self.assertEqual(state["listing_count"], 1)
        auth = self.client.post("/api/mercadolibre/auth-url", headers=self.headers)
        self.assertEqual(auth.status_code, 200, auth.text)
        state = parse_qs(urlsplit(auth.json()["url"]).query)["state"][0]
        with SessionLocal() as db:
            LocalMLService(db).connect("SYNTHETIC-CODE", state)
            with self.assertRaises(ValueError):
                LocalMLService(db).connect("SYNTHETIC-CODE", state)
        self.assertTrue(self.status()["ml"]["connected"])

    def test_existing_csv_import_counts_products_rows_and_keeps_previous_on_bad_file(
        self,
    ):
        csv = "Identificador de URL;Nombre;SKU;Precio;Stock\nchia-prueba;Chía sintética;DEMO-CHIA;1;2\nchia-prueba;Chía sintética pack x6;PACK-CHIA;6;1\n"
        response = self.client.post(
            "/api/tiendanube/import-csv",
            headers=self.headers,
            files={"file": ("prueba.csv", csv.encode(), "text/csv")},
        )
        self.assertEqual(response.status_code, 201, response.text)
        state = self.status()["tn"]
        self.assertEqual((state["products"], state["records"]), (1, 2))
        self.assertFalse(state["current_publication_verified"])
        self.assertIsNotNone(state["imported_at"])
        self.assertEqual(
            self.client.post(
                "/api/tiendanube/import-csv",
                headers=self.headers,
                files={"file": ("invalido.csv", b"invalid", "text/csv")},
            ).status_code,
            422,
        )
        self.assertEqual(self.status()["tn"], state)

    def test_no_transport_can_escape_the_offline_boundary(self):
        import socket

        with self.assertRaises(IsolationError):
            socket.getaddrinfo("admin.ecomm-app.com", 443)
        for method, path in MLFixtureTransport.calls:
            self.assertTrue(
                method == "GET" or (method == "POST" and path == "/oauth/token")
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
