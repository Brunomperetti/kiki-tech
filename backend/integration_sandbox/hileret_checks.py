"""Hileret preparation. No authentic PDF supplied: never fake a successful pilot.

Generated PDF/text bytes below are NEGATIVE synthetic controls only. They are not
manufacturer evidence and never produce an approved commercial fact/proposal.
"""

import base64
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
from threading import Barrier
import unittest
from .bootstrap import create_sandbox_app

application = create_sandbox_app()

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import delete, select  # noqa: E402
from app.database.session import SessionLocal, engine  # noqa: E402
from app.database.models import (  # noqa: E402
    EcommApiProductEdit,
    KikiAiEditorialDraft,
    CatalogSnapshot,
)
from .research.storage import Dossier, Document, initialize, digest  # noqa: E402
from .research.service import Research, identity_digest  # noqa: E402
from .hileret_reference import UNIT_ID, PACK_ID, PILOTS, EAN, DUN, URL, reference  # noqa: E402
from .document_parser import parse  # noqa: E402
from .document_test_fixtures import pdf  # noqa: E402

API = "/api/test-commercial-pilot/hileret-200"


def operator():
    client = TestClient(application, base_url="https://127.0.0.1:8443")
    result = client.post(
        "/api/auth/login",
        json={"username": "operador-prueba", "password": "solo-datos-sinteticos"},
    )
    assert result.status_code == 200
    client.headers["X-CSRF-Token"] = result.json()["csrf_token"]
    return client


class HileretPostgreSQL(unittest.TestCase):
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

    def ok(self, response):
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def prepare(self):
        return self.ok(self.client.post(API + "/prepare", json={}))

    def case(self, ident=UNIT_ID):
        return self.ok(self.client.get("/api/test-research/" + ident))

    def workspace(self, ident=UNIT_ID):
        return self.ok(self.client.get("/api/ecomm-app/workspace/" + ident))

    def import_control(
        self,
        raw,
        *,
        ident=UNIT_ID,
        filename="CONTROL-NEGATIVO-SINTETICO.pdf",
        mime="application/pdf",
    ):
        result = self.ok(
            self.client.post(
                f"/api/test-documents/{ident}/import",
                json={
                    "kind": "FILE",
                    "expected_version": self.case(ident)["version"],
                    "filename": filename,
                    "content_type": mime,
                    "content_base64": base64.b64encode(raw).decode(),
                    "reference_url": URL,
                    "declared_official": False,
                    "provenance_note": "CONTROL NEGATIVO SINTÉTICO; no es folleto auténtico de Hileret ni respaldo comercial del fabricante.",
                    "authorized_local_processing": True,
                },
            )
        )
        return result, next(
            d
            for d in result["documents"]
            if d["id"] == result["incorporated_document_id"]
        )

    def extract(self, data, doc, ident=UNIT_ID):
        return self.ok(
            self.client.post(
                f"/api/test-research/{ident}/extract",
                json={
                    "expected_version": data["version"],
                    "document_id": doc["id"],
                    "document_version": doc["version"],
                },
            )
        )

    def test_separate_cases_no_original_no_approved_facts_no_catalog_or_mama_change(
        self,
    ):
        self.assertEqual(self.ok(self.client.get(API))["cases"], [])
        self.ok(
            self.client.post("/api/test-commercial-pilot/mama-350/prepare", json={})
        )
        mama = self.ok(self.client.get("/api/test-commercial-pilot/mama-350"))
        with SessionLocal() as db:
            catalog = digest(db.scalar(select(CatalogSnapshot)).payload)
        first = self.prepare()
        self.assertEqual(first, self.prepare())
        self.assertEqual({c["test_id"] for c in first["cases"]}, set(PILOTS))
        for case in first["cases"]:
            self.assertIsNone(case["authentic_ecomm_id"])
            self.assertTrue(case["test_id_is_synthetic"])
            self.assertIsNone(case["variant"]["gtin"])
            self.assertFalse(case["original_pdf_available"])
            self.assertEqual(case["document_status"], "BLOCKED_NO_ORIGINAL_PDF")
            self.assertEqual(case["approved_fact_count"], 0)
            self.assertEqual(case["proposed_fields_preview"], {})
            self.assertEqual(len(case["blocked_fields"]), 9)
            self.assertEqual(case["references"]["excel"]["ean_declared"], EAN)
            self.assertIsNone(
                case["references"]["brochure"]["document_sha256_at_registration"]
            )
            self.assertIsNone(case["documents"][0]["original"])
            self.assertEqual(case["documents"][0]["parse_status"], "REFERENCE_ONLY")
            self.assertTrue(all(not v for v in case["current_fields"].values()))
        self.assertNotEqual(EAN, DUN)
        self.assertEqual(
            self.ok(self.client.get("/api/test-commercial-pilot/mama-350")), mama
        )
        with SessionLocal() as db:
            self.assertEqual(
                digest(db.scalar(select(CatalogSnapshot)).payload), catalog
            )

    def test_reference_and_unrelated_fixtures_cannot_be_extracted_or_generated(self):
        self.prepare()
        for ident in PILOTS:
            case = self.case(ident)
            for doc_id in (case["documents"][0]["id"], "alm-tecnica"):
                self.assertEqual(
                    self.client.post(
                        f"/api/test-research/{ident}/extract",
                        json={
                            "expected_version": case["version"],
                            "document_id": doc_id,
                            "document_version": 1,
                        },
                    ).status_code,
                    409,
                )
            response = self.client.post(
                f"/api/test-proposals/{ident}/generate", json={"expected_version": 0}
            )
            self.assertEqual(response.status_code, 409)
            self.assertIn("PDF original", response.json()["detail"])
            context = self.ok(
                self.client.get(f"/api/test-proposals/{ident}/generation-context")
            )
            self.assertEqual(context["facts"], [])
            self.assertEqual(context["provider"]["calls"], 0)
            self.assertFalse(context["provider"]["enabled"])

    def test_identity_contrasts_unit_pack6_box9_dun_and_shared_ean(self):
        # Structural comparison only, not evidence or an official extraction.
        shape = {
            "identity": {
                "name": "Hileret Stevia",
                "brand": "Hileret",
                "ean": EAN,
                "presentation": "200 ml",
                "is_combo": False,
            },
            "claims": [],
            "associated_ecomm_id": UNIT_ID,
        }
        self.assertEqual(Research.identity_issues(reference(UNIT_ID), shape), [])
        self.assertTrue(Research.identity_issues(reference(PACK_ID), shape))
        pack = deepcopy(shape)
        pack.update(associated_ecomm_id=PACK_ID)
        pack["identity"].update(
            name=PILOTS[PACK_ID]["name"], presentation="6 x 200 ml", is_combo=True
        )
        self.assertEqual(Research.identity_issues(reference(PACK_ID), pack), [])
        self.assertTrue(Research.identity_issues(reference(UNIT_ID), pack))
        for changes in (
            {"ean": DUN},
            {"presentation": "9 x 200 ml", "is_combo": True},
            {"presentation": "6 x 200 ml", "is_combo": True},
            {"brand": "Otra marca"},
            {"ean": None},
            {"is_combo": None},
        ):
            wrong = deepcopy(shape)
            wrong["identity"].update(changes)
            self.assertTrue(Research.identity_issues(reference(UNIT_ID), wrong))
        self.assertNotEqual(
            identity_digest(reference(UNIT_ID)), identity_digest(reference(PACK_ID))
        )
        self.assertEqual(
            identity_digest(reference(UNIT_ID)),
            identity_digest(
                reference(
                    UNIT_ID,
                    {
                        "brand": "Hileret",
                        "proposed_gtin": EAN,
                        "presentation": "200 ml",
                    },
                )
            ),
        )
        self.assertTrue(
            Research.identity_issues(reference(UNIT_ID, {"proposed_gtin": DUN}), shape)
        )

    def test_negative_pdf_keeps_bytes_hash_pages_quotes_and_blocks_approval(self):
        self.prepare()
        raw = pdf(
            "CONTROL SINTETICO NEGATIVO - NO ES FOLLETO HILERET\nNombre: PRODUCTO DE CONTROL\nMarca: MARCA DE CONTROL\nEAN: 12345670\nPresentación: 200 ml\nTipo de venta: Unidad\nContenido neto: 200 ml",
            pages=2,
            compressed=True,
        )
        data, doc = self.import_control(raw)
        self.assertEqual(
            doc["body"]["original"]["sha256"], hashlib.sha256(raw).hexdigest()
        )
        self.assertEqual(doc["body"]["source"]["review_state"], "PENDING")
        self.assertTrue(
            any(loc.startswith("pagina/2/") for loc in doc["body"]["sections"])
        )
        original = self.ok(
            self.client.get(f"/api/test-documents/{UNIT_ID}/{doc['id']}/original/1")
        )
        self.assertEqual(base64.b64decode(original["content_base64"]), raw)
        # Even explicitly reviewing the negative source cannot bypass incompatible identity.
        data = self.ok(
            self.client.post(
                f"/api/test-documents/{UNIT_ID}/{doc['id']}/provenance",
                json={
                    "expected_document_version": 1,
                    "decision": "REVIEWED",
                    "reason": "Control negativo: archivo de prueba, identidad incompatible, no aprobar hechos.",
                },
            )
        )
        doc = next(d for d in data["documents"] if d["id"] == doc["id"])
        data = self.extract(data, doc)
        fact = data["facts"][0]
        self.assertIn(fact["quote"], doc["body"]["sections"][fact["location"]])
        self.assertTrue(fact["blockers"])
        self.assertFalse(fact["verified"])
        self.assertEqual(
            self.client.post(
                f"/api/test-research/{UNIT_ID}/facts/{fact['id']}/review",
                json={
                    "expected_version": data["version"],
                    "expected_fact_version": fact["version"],
                    "decision": "APPROVED",
                    "reason": "Control negativo: debe rechazarse la aprobación incompatible.",
                },
            ).status_code,
            409,
        )
        self.assertEqual(
            self.client.post(
                f"/api/test-research/{PACK_ID}/extract",
                json={
                    "expected_version": self.case(PACK_ID)["version"],
                    "document_id": doc["id"],
                    "document_version": doc["version"],
                },
            ).status_code,
            409,
        )
        self.assertEqual(
            self.ok(
                self.client.get(f"/api/test-documents/{UNIT_ID}/{doc['id']}/original/1")
            )["content_base64"],
            original["content_base64"],
        )
        self.assertTrue(
            any(h["action"] == "PROVENANCE_REVIEWED" for h in self.case()["history"])
        )
        self.assertEqual(
            self.ok(self.client.get(API))["cases"][0]["approved_fact_count"], 0
        )

    def test_compatible_transcription_is_not_original_brochure(self):
        self.prepare()
        raw = f"CONTROL SINTETICO - NO DOCUMENTO OFICIAL\nNombre: Hileret Stevia\nMarca: Hileret\nEAN: {EAN}\nPresentación: 200 ml\nTipo de venta: Unidad".encode()
        data, doc = self.import_control(
            raw, filename="CONTROL-NEGATIVO-SINTETICO.txt", mime="text/plain"
        )
        data = self.extract(data, doc)
        self.assertTrue(data["facts"])
        self.assertTrue(
            all(any("PDF original" in b for b in f["blockers"]) for f in data["facts"])
        )
        self.assertFalse(any(f["verified"] for f in data["facts"]))

    def test_note_roundtrip_history_and_two_operators_never_overwrite_other_variant(
        self,
    ):
        self.prepare()
        pack = self.workspace(PACK_ID)
        before = self.workspace()
        self.ok(
            self.client.post(
                f"/api/ecomm-app/workspace/{UNIT_ID}",
                json={
                    "fields": {
                        **before["fields"],
                        "note": "Pendiente PDF original y Ecomm ID auténtico; sólo seguimiento.",
                    },
                    "expected_version": 0,
                    "status": "DRAFT",
                },
            )
        )
        saved = self.workspace()
        self.assertEqual(len(saved["fields"]), 18)
        barrier = Barrier(2)

        def save(note):
            with operator() as client:
                barrier.wait(timeout=5)
                return client.post(
                    f"/api/ecomm-app/workspace/{UNIT_ID}",
                    json={
                        "fields": {**saved["fields"], "note": note},
                        "expected_version": 1,
                        "status": "DRAFT",
                    },
                ).status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(
                sorted(
                    pool.map(save, ["Seguimiento operador A", "Seguimiento operador B"])
                ),
                [200, 409],
            )
        after = self.workspace()
        self.assertEqual(after["version"], 2)
        self.assertEqual(len(after["history"]), 2)
        self.assertEqual(self.workspace(PACK_ID), pack)
        report = self.ok(self.client.get(API))["cases"][0]
        self.assertEqual(report["initial_fields"]["note"], "")
        self.assertEqual(report["current_fields"], after["fields"])
        self.assertTrue(
            all(not after["fields"][key] for key in report["blocked_fields"])
        )
        self.assertEqual(
            self.client.post(
                f"/api/ecomm-app/workspace/{UNIT_ID}",
                json={
                    "fields": after["fields"],
                    "expected_version": 2,
                    "status": "READY_FOR_REVIEW",
                },
            ).status_code,
            409,
        )

    def test_parallel_preparation_is_idempotent_and_preserves_distinct_documents(self):
        barrier = Barrier(2)

        def prepare(_):
            with operator() as client:
                barrier.wait(timeout=5)
                return client.post(API + "/prepare", json={}).status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(list(pool.map(prepare, range(2))), [200, 200])
        self.assertEqual(len(self.ok(self.client.get(API))["cases"]), 2)
        ids = []
        for ident in PILOTS:
            case = self.case(ident)
            self.assertEqual(case["version"], 2)
            self.assertEqual(len(case["documents"]), 1)
            ids.append(case["documents"][0]["id"])
        self.assertNotEqual(*ids)

    def test_auth_csrf_no_collector_arbitrary_ids_or_invalid_pdf(self):
        with TestClient(application, base_url="https://127.0.0.1:8443") as anonymous:
            self.assertEqual(anonymous.post(API + "/prepare", json={}).status_code, 401)
        token = self.client.headers.pop("X-CSRF-Token")
        self.assertEqual(self.client.post(API + "/prepare", json={}).status_code, 403)
        self.client.headers["X-CSRF-Token"] = token
        self.prepare()
        for ident in PILOTS:
            self.assertEqual(
                self.client.post(
                    f"/api/test-discovery/{ident}/start", json={}
                ).status_code,
                403,
            )
        self.assertEqual(
            self.client.get(
                "/api/ecomm-app/workspace/PILOT-HILERET-200-BOX9-SYNTHETIC"
            ).status_code,
            403,
        )
        with self.assertRaises(ValueError):
            parse(
                "falso.pdf",
                "application/pdf",
                base64.b64encode(b"No son bytes PDF").decode(),
            )
        self.assertEqual(self.case()["facts"], [])
        self.assertFalse(
            self.ok(self.client.get("/api/test-discovery/pilot-status"))[
                "network_enabled"
            ]
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
