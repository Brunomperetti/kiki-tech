"""Existing workspace endpoints, actual disposable PostgreSQL, concurrent sessions."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Barrier
import unittest

from .bootstrap import create_sandbox_app

application = create_sandbox_app()

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import delete, select, event  # noqa: E402
from app.database.session import SessionLocal, engine  # noqa: E402
from app.database.models import EcommApiProductEdit, CatalogSnapshot  # noqa: E402
from app.services.ecomm_api_product_workspace_service import blank_fields  # noqa: E402
from app.integrations.ecomm_app.catalog_stage import STAGE_SOURCE  # noqa: E402


def full_fields():
    return {
        **blank_fields(),
        "brand": "Marca sintética",
        "manufacturer": "Fabricante inventado",
        "title": "Almendras de prueba 250 g",
        "short_title": "Almendras sintéticas",
        "short_description": "Descripción corta sintética.",
        "description": "Descripción comercial de prueba.",
        "details": "Detalles inventados para validar el editor.",
        "presentation": "250 g",
        "category": "Dietética sintética",
        "subcategory": "Frutos secos",
        "seo_title": "Almendras de prueba",
        "seo_description": "SEO sintético para probar persistencia.",
        "seo_keywords": "almendras, prueba",
        "note": "Ningún dato corresponde a un producto real.",
        "attributes": [{"name": "Contenido neto", "value": "250 g"}],
        "media": [
            {
                "kind": "IMAGE",
                "url": "https://synthetic.invalid/image.jpg",
                "alt": "Imagen inventada",
                "source_url": "https://synthetic.invalid/product",
            },
            {
                "kind": "VIDEO",
                "url": "https://synthetic.invalid/video.mp4",
                "alt": "Video inventado",
                "source_url": "https://synthetic.invalid/product",
            },
        ],
        "sources": [
            {
                "kind": "FABRICANTE",
                "name": "Fuente de prueba",
                "url": "https://synthetic.invalid/product",
                "note": "Evidencia exclusivamente sintética de la presentación.",
                "verified": True,
            }
        ],
    }


def operator():
    client = TestClient(application, base_url="https://127.0.0.1:8443")
    response = client.post(
        "/api/auth/login",
        json={"username": "operador-prueba", "password": "solo-datos-sinteticos"},
    )
    assert response.status_code == 200
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    return client


class EditorPostgreSQL(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lifecycle = TestClient(application, base_url="https://127.0.0.1:8443")
        cls.lifecycle.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.lifecycle.__exit__(None, None, None)

    def setUp(self):
        with SessionLocal() as db:
            db.execute(delete(EcommApiProductEdit))
            db.commit()
        self.client = operator()
        self.addCleanup(self.client.close)

    def save(self, fields=None, version=0, status="DRAFT", ident="900001"):
        return self.client.post(
            "/api/ecomm-app/workspace/" + ident,
            json={
                "expected_version": version,
                "status": status,
                "fields": fields or full_fields(),
            },
        )

    def test_complete_editor_roundtrip_and_immutable_capture(self):
        with SessionLocal() as db:
            before = deepcopy(
                db.scalar(
                    select(CatalogSnapshot).where(
                        CatalogSnapshot.source == STAGE_SOURCE
                    )
                ).payload
            )
        first = self.save()
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["version"], 1)
        second = operator()
        try:
            recovered = second.get("/api/ecomm-app/workspace/900001").json()
            self.assertEqual(recovered["fields"], full_fields())
            self.assertEqual(len(recovered["history"]), 1)
            self.assertEqual(recovered["history"][0]["version"], 1)
            with SessionLocal() as db:
                persisted = db.scalar(
                    select(EcommApiProductEdit).where(
                        EcommApiProductEdit.ecomm_id == "900001"
                    )
                )
                self.assertEqual(persisted.fields, full_fields())
                self.assertEqual(
                    db.scalar(
                        select(CatalogSnapshot).where(
                            CatalogSnapshot.source == STAGE_SOURCE
                        )
                    ).payload,
                    before,
                )
        finally:
            second.close()

    def race(self, version):
        barrier = Barrier(2)

        def synchronize(
            _connection, _cursor, statement, _parameters, _context, _executemany
        ):
            if "ecomm_api_product_edits" in statement and "FOR UPDATE" in statement:
                barrier.wait(timeout=10)

        operators = [operator(), operator()]
        payloads = [
            {**full_fields(), "title": f"Edición sintética operador {i}"}
            for i in (1, 2)
        ]
        event.listen(engine, "before_cursor_execute", synchronize)
        try:

            def save(index):
                return operators[index].post(
                    "/api/ecomm-app/workspace/900001",
                    json={
                        "expected_version": version,
                        "status": "DRAFT",
                        "fields": payloads[index],
                    },
                )

            with ThreadPoolExecutor(max_workers=2) as executor:
                responses = list(executor.map(save, [0, 1]))
        finally:
            event.remove(engine, "before_cursor_execute", synchronize)
            for client in operators:
                client.close()
        self.assertEqual(
            sorted(response.status_code for response in responses), [200, 409]
        )
        winner = next(
            index
            for index, response in enumerate(responses)
            if response.status_code == 200
        )
        with SessionLocal() as db:
            records = db.scalars(select(EcommApiProductEdit)).all()
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0].version, version + 1)
            self.assertEqual(records[0].fields["title"], payloads[winner]["title"])
            self.assertEqual(len(records[0].history), version + 1)

    def test_two_sessions_update_the_same_version_one_wins(self):
        self.assertEqual(self.save().status_code, 200)
        self.race(1)

    def test_two_sessions_create_the_same_variant_one_wins(self):
        self.race(0)

    def test_validation_readiness_states_and_history_reuse_existing_rules(self):
        self.assertEqual(
            self.save(
                {"note": "Borrador incompleto"}, status="READY_FOR_CHANNELS"
            ).status_code,
            409,
        )
        self.assertEqual(self.save({"proposed_gtin": "123"}).status_code, 409)
        self.assertEqual(
            self.save(
                {
                    **full_fields(),
                    "media": [
                        {"kind": "IMAGE", "url": "http://synthetic.invalid/image"}
                    ],
                }
            ).status_code,
            409,
        )
        self.assertEqual(
            self.save({**full_fields(), "title": "X" * 181}).status_code, 422
        )
        ready = self.save(status="READY_FOR_CHANNELS")
        self.assertEqual(ready.status_code, 200)
        self.assertTrue(ready.json()["readiness"]["ready"])
        changed = self.save(
            {**full_fields(), "note": "Segunda revisión sintética"},
            version=1,
            status="READY_FOR_REVIEW",
        )
        self.assertEqual(changed.status_code, 200)
        self.assertEqual(changed.json()["version"], 2)
        self.assertEqual(len(changed.json()["history"]), 2)

    def test_csrf_authentication_and_unrelated_operations_remain_blocked(self):
        anonymous = TestClient(application, base_url="https://127.0.0.1:8443")
        try:
            self.assertEqual(
                anonymous.get("/api/ecomm-app/workspace/900001").status_code, 401
            )
            self.assertEqual(
                anonymous.post("/api/ecomm-app/workspace/900001", json={}).status_code,
                401,
            )
        finally:
            anonymous.close()
        self.client.headers.pop("X-CSRF-Token")
        self.assertEqual(self.save().status_code, 403)
        self.client.headers["X-CSRF-Token"] = "invalid"
        self.assertEqual(self.save().status_code, 403)
        for path in [
            "/api/ecomm-app/workspace/900001/confirm-review",
            "/api/ecomm-app/workspace/ai/900001/suggest",
            "/api/ecomm-app/workspace/saved",
            "/api/ecomm-app/stage/manual/start",
            "/api/mercadolibre/sync",
        ]:
            self.assertEqual(self.client.post(path).status_code, 403)

    def test_incompatible_sku_blocks_save_and_does_not_overwrite(self):
        self.assertEqual(self.save().status_code, 200)
        with SessionLocal() as db:
            capture = db.scalar(
                select(CatalogSnapshot).where(CatalogSnapshot.source == STAGE_SOURCE)
            )
            original = deepcopy(capture.payload)
            changed = deepcopy(original)
            changed[0]["items"][0]["variants"][0]["sku"] = "SYNTHETIC-IDENTITY-CHANGED"
            capture.payload = changed
            db.commit()
            try:
                self.assertTrue(
                    self.client.get("/api/ecomm-app/workspace/900001").json()[
                        "source_sku_changed"
                    ]
                )
                self.assertEqual(
                    self.save(
                        {**full_fields(), "note": "No debe persistir"}, version=1
                    ).status_code,
                    409,
                )
                edit = db.scalar(select(EcommApiProductEdit))
                self.assertEqual(edit.version, 1)
                self.assertNotEqual(edit.fields["note"], "No debe persistir")
            finally:
                capture.payload = original
                db.commit()

    def test_repeated_sku_variants_have_independent_records(self):
        self.assertEqual(self.save(ident="900001").status_code, 200)
        fields = {
            **full_fields(),
            "presentation": "1 kg",
            "note": "Segunda variante sintética",
        }
        self.assertEqual(self.save(fields, ident="900002").status_code, 200)
        with SessionLocal() as db:
            records = db.scalars(
                select(EcommApiProductEdit).order_by(EcommApiProductEdit.ecomm_id)
            ).all()
            self.assertEqual(len(records), 2)
            self.assertEqual(records[0].source_sku, records[1].source_sku)
            self.assertNotEqual(
                records[0].fields["presentation"], records[1].fields["presentation"]
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
