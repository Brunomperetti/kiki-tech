"""Commercial pilot: real user references, NO authentic document supplied.

All generated upload bytes are explicitly NEGATIVE synthetic controls, never
approved facts, nutrition, or a commercial proposal for the real product.
"""

import base64
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import unittest
from .bootstrap import create_sandbox_app

application = create_sandbox_app()

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import delete, select, func  # noqa: E402
from app.database.session import SessionLocal, engine  # noqa: E402
from app.database.models import (  # noqa: E402
    EcommApiProductEdit,
    KikiAiEditorialDraft,
    CatalogSnapshot,
)
from .research.storage import Dossier, Document, initialize, digest  # noqa: E402
from .mama_reference import PILOT_ID, URL, NAME, EAN, CATALOG_NAME  # noqa: E402
from .document_parser import parse  # noqa: E402
from .research.service import Research  # noqa: E402

API = "/api/test-commercial-pilot/mama-350"
ROOT = "/api/test-research/" + PILOT_ID
WORKSPACE = "/api/ecomm-app/workspace/" + PILOT_ID


def operator():
    c = TestClient(application, base_url="https://127.0.0.1:8443")
    r = c.post(
        "/api/auth/login",
        json={"username": "operador-prueba", "password": "solo-datos-sinteticos"},
    )
    assert r.status_code == 200
    c.headers["X-CSRF-Token"] = r.json()["csrf_token"]
    return c


class MamaPostgreSQL(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.life = TestClient(application, base_url="https://127.0.0.1:8443")
        cls.life.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.life.__exit__(None, None, None)

    def setUp(self):
        with SessionLocal() as db:
            for model in (KikiAiEditorialDraft, EcommApiProductEdit, Dossier, Document):
                db.execute(delete(model))
            db.commit()
        initialize(engine, SessionLocal)
        self.client = operator()
        self.addCleanup(self.client.close)

    def ok(self, r):
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def prepare(self):
        return self.ok(self.client.post(API + "/prepare", json={}))

    def case(self):
        return self.ok(self.client.get(ROOT))

    def test_opt_in_refs_idempotence_no_catalog_mutation_or_fabricated_file_hash(self):
        self.assertFalse(self.ok(self.client.get(API))["available"])
        with SessionLocal() as db:
            original = digest(db.scalar(select(CatalogSnapshot)).payload)
        data = self.prepare()
        self.assertIsNone(data["authentic_ecomm_id"])
        self.assertTrue(data["test_id_is_synthetic"])
        self.assertEqual(data["variant"]["id"], PILOT_ID)
        self.assertIsNone(data["variant"]["gtin"])
        x = data["references"]["excel"]
        self.assertEqual(
            (x["row"], x["declared_ean"], x["file_sku"]), (37, EAN, "fideos 10mm Mama")
        )
        self.assertTrue(x["ean_checksum_valid"])
        self.assertFalse(x["ean_official_correspondence_verified"])
        self.assertFalse(x["original_file_available"])
        self.assertIsNone(x["original_file_sha256"])
        self.assertEqual(data["references"]["manufacturer_candidate"]["url"], URL)
        self.assertFalse(data["references"]["manufacturer_candidate"]["downloaded"])
        self.assertEqual(data["reference_record_hash"], digest(data["references"]))
        first = self.case()
        self.assertEqual(len(first["documents"]), 1)
        self.assertEqual(
            first["documents"][0]["body"]["parse_status"], "REFERENCE_ONLY"
        )
        self.assertEqual(first["facts"], [])
        self.prepare()
        self.assertEqual(self.case()["version"], first["version"])
        self.assertEqual(len(self.case()["documents"]), 1)
        catalog = self.ok(self.client.get("/api/ecomm-app/stage/catalog?limit=25"))
        self.assertEqual(catalog["total_variants_in_capture"], 6)
        self.assertNotIn(PILOT_ID, str(catalog))
        with SessionLocal() as db:
            self.assertEqual(
                digest(db.scalar(select(CatalogSnapshot)).payload), original
            )

    def test_missing_documents_block_extraction_generation_and_all_commercial_fields(
        self,
    ):
        data = self.prepare()
        self.assertEqual(data["approved_fact_count"], 0)
        self.assertEqual(data["proposed_fields_preview"], {})
        self.assertEqual(len(data["blocked_fields"]), 9)
        case = self.case()
        doc = case["documents"][0]
        response = self.client.post(
            ROOT + "/extract",
            json={
                "expected_version": case["version"],
                "document_id": doc["id"],
                "document_version": doc["version"],
            },
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            self.client.post(
                ROOT + "/extract",
                json={
                    "expected_version": case["version"],
                    "document_id": "alm-tecnica",
                    "document_version": 1,
                },
            ).status_code,
            409,
        )
        r = self.client.post(
            "/api/test-proposals/" + PILOT_ID + "/generate",
            json={"expected_version": 0},
        )
        self.assertEqual(r.status_code, 409)
        self.assertIn("10 mm", r.json()["detail"])
        self.assertIn("350 g", r.json()["detail"])
        with SessionLocal() as db:
            self.assertEqual(
                db.scalar(select(func.count()).select_from(KikiAiEditorialDraft)), 0
            )
        context = self.ok(
            self.client.get("/api/test-proposals/" + PILOT_ID + "/generation-context")
        )
        self.assertEqual(context["facts"], [])
        self.assertFalse(context["provider"]["enabled"])

    def test_note_roundtrip_compare_and_concurrency_without_invented_copy(self):
        self.prepare()
        record = self.ok(self.client.get(WORKSPACE))
        self.assertEqual(len(record["fields"]), 18)
        self.assertIsNone(record["source"]["authentic_ecomm_id"])
        note = "Pendiente copia auténtica del fabricante y Ecomm ID real. Sólo nota de seguimiento, no propuesta comercial."
        self.ok(
            self.client.post(
                WORKSPACE,
                json={
                    "expected_version": 0,
                    "status": "DRAFT",
                    "fields": {**record["fields"], "note": note},
                },
            )
        )
        recovered = self.ok(self.client.get(WORKSPACE))
        self.assertEqual(recovered["fields"]["note"], note)
        data = self.ok(self.client.get(API))
        self.assertEqual(data["initial_fields"]["note"], "")
        self.assertEqual(data["current_fields"]["note"], note)
        for key in data["blocked_fields"]:
            self.assertEqual(data["current_fields"][key], "")
        barrier = Barrier(2)

        def save(value):
            with operator() as client:
                barrier.wait(timeout=5)
                return client.post(
                    WORKSPACE,
                    json={
                        "expected_version": 1,
                        "status": "DRAFT",
                        "fields": {**recovered["fields"], "note": value},
                    },
                ).status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(
                pool.map(
                    save,
                    ["Nota de operador de prueba A", "Nota de operador de prueba B"],
                )
            )
        self.assertEqual(sorted(results), [200, 409])
        self.assertEqual(
            self.client.post(
                WORKSPACE,
                json={
                    "expected_version": 2,
                    "status": "READY_FOR_REVIEW",
                    "fields": recovered["fields"],
                },
            ).status_code,
            409,
        )

    def test_manual_negative_documents_retain_originals_and_block_identity_mismatches(
        self,
    ):
        self.prepare()
        # Explicit synthetic negative controls. No ingredients or nutrition invented.
        text = f"Nombre: {NAME}\nMarca: Mama\nFabricante: Thai President Foods\nEAN: {EAN}\nPresentación: 350 g\nTipo de venta: Unidad\nAncho: 10 mm\nContenido neto: 350 g"
        for incorrect in [
            text.replace(EAN, "12345670"),
            text.replace("Ancho: 10 mm", "Ancho: 5 mm"),
            text.replace("Contenido neto: 350 g", "Contenido neto: 400 g"),
            text.replace("Marca: Mama", "Marca: Otra marca de control"),
        ]:
            case = self.case()
            data = self.ok(
                self.client.post(
                    "/api/test-documents/" + PILOT_ID + "/import",
                    json={
                        "kind": "FILE",
                        "expected_version": case["version"],
                        "filename": "CONTROL-NEGATIVO-SINTETICO.txt",
                        "content_type": "text/plain",
                        "content_base64": base64.b64encode(incorrect.encode()).decode(),
                        "provenance_note": "CONTROL NEGATIVO SINTÉTICO; no es documentación auténtica ni puede presentarse como evidencia comercial del fabricante.",
                        "authorized_local_processing": True,
                    },
                )
            )
            key = data["incorporated_document_id"]
            doc = next(d for d in data["documents"] if d["id"] == key)
            self.assertTrue(doc["issues"])
            original = self.ok(
                self.client.get(f"/api/test-documents/{PILOT_ID}/{key}/original/1")
            )
            self.assertEqual(
                base64.b64decode(original["content_base64"]), incorrect.encode()
            )
            data = self.ok(
                self.client.post(
                    ROOT + "/extract",
                    json={
                        "expected_version": data["version"],
                        "document_id": key,
                        "document_version": 1,
                    },
                )
            )
            fact = next(
                f
                for f in data["facts"]
                if f["document_id"] == key and f["field"] == "product_name"
            )
            self.assertTrue(fact["blockers"])
            self.assertEqual(
                self.client.post(
                    f"{ROOT}/facts/{fact['id']}/review",
                    json={
                        "expected_version": data["version"],
                        "expected_fact_version": fact["version"],
                        "decision": "APPROVED",
                        "reason": "Intento negativo de aprobación, debe permanecer bloqueado.",
                    },
                ).status_code,
                409,
            )
        self.assertEqual(self.ok(self.client.get(API))["approved_fact_count"], 0)

    def test_width_parser_and_compatibility_are_only_structural_not_manufacturer_verification(
        self,
    ):
        # An isolated parser/identity shape test, not ingested, approved or delivered as a real document.
        raw = f"Nombre: {CATALOG_NAME}\nMarca: Mama\nFabricante: Thai President Foods\nEAN: {EAN}\nPresentación: 350 g\nTipo de venta: Unidad\nAncho: 10 mm\nContenido neto: 0,35 kg"
        parsed = parse(
            "CONTROL-SINTETICO.txt",
            "text/plain",
            base64.b64encode(raw.encode()).decode(),
        )
        from .mama_reference import reference

        parsed["associated_ecomm_id"] = PILOT_ID
        self.assertEqual(Research.identity_issues(reference(), parsed), [])
        width = next(f for f in parsed["claims"] if f["field"] == "width")
        self.assertEqual((width["value"], width["unit"]), ("10", "mm"))
        self.assertIn(width["quote"], parsed["sections"][width["location"]])
        parsed["claims"] = [f for f in parsed["claims"] if f["field"] != "width"]
        self.assertTrue(
            any("Ancho" in s for s in Research.identity_issues(reference(), parsed))
        )

    def test_auth_csrf_no_alias_binding_no_collector_or_provider_access(self):
        with TestClient(application, base_url="https://127.0.0.1:8443") as anonymous:
            self.assertEqual(anonymous.post(API + "/prepare", json={}).status_code, 401)
        self.assertEqual(
            self.client.post(
                API + "/prepare", json={"real_ecomm_id": "inventado"}
            ).status_code,
            422,
        )
        self.client.headers.pop("X-CSRF-Token")
        self.assertEqual(self.client.post(API + "/prepare", json={}).status_code, 403)
        self.client.headers["X-CSRF-Token"] = self.ok(self.client.get("/api/auth/me"))[
            "csrf_token"
        ]
        self.prepare()
        for path in [
            API + "/bind",
            "/api/test-discovery/" + PILOT_ID + "/start",
            "/api/mercadolibre/sync",
            "/api/ecomm-app/workspace/real-id",
        ]:
            self.assertEqual(self.client.post(path, json={}).status_code, 403)
        status = self.ok(self.client.get("/api/test-discovery/pilot-status"))
        self.assertFalse(status["network_enabled"])
        self.assertEqual(status["authorized_domains"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
