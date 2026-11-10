"""Authentic user-supplied PDF; approvals below explicitly simulate a test operator.

No import, source declaration, hash or extraction is itself a human approval.
"""

import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
from pathlib import Path
from threading import Barrier
import unittest
from .hileret_checks import application, operator
from fastapi.testclient import TestClient
from sqlalchemy import delete
from app.database.session import SessionLocal, engine
from app.database.models import EcommApiProductEdit, KikiAiEditorialDraft
from .research.storage import Dossier, Document, initialize
from .hileret_reference import UNIT_ID, PACK_ID, EAN, DUN, URL
from .hileret_brochure import SHA256, SIZE, PROFILE, matches
from .document_parser import parse

REASON = "RECORRIDO AUTOMATIZADO DE PRUEBA, no aprobación efectiva del cliente: contrastados bytes, página 2 y citas del original adjunto."


class AuthenticHileret(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.life = TestClient(application, base_url="https://127.0.0.1:8443")
        cls.life.__enter__()
        cls.raw = Path("/pilot-inputs/hileret-original.pdf").read_bytes()
        cls.encoded = base64.b64encode(cls.raw).decode()

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
        self.ok(
            self.client.post("/api/test-commercial-pilot/hileret-200/prepare", json={})
        )

    def ok(self, response):
        self.assertEqual(response.status_code, 200, response.text[:1500])
        return response.json()

    def case(self, ident=UNIT_ID):
        return self.ok(self.client.get(f"/api/test-research/{ident}"))

    def workspace(self, ident=UNIT_ID):
        return self.ok(self.client.get(f"/api/ecomm-app/workspace/{ident}"))

    def payload(self, ident=UNIT_ID):
        return {
            "kind": "FILE",
            "expected_version": self.case(ident)["version"],
            "filename": "Folleto Ventas Hileret 17x25_400s.pdf",
            "content_type": "application/pdf",
            "content_base64": self.encoded,
            "reference_url": URL,
            "provenance_note": "Original adjunto por el usuario, quien declara descarga del dominio oficial Hileret. Codex verifica bytes y contenido local; no realizó descarga web ni conoce fecha de consulta original.",
            "declared_official": True,
            "authorized_local_processing": True,
        }

    def incorporate(self, ident=UNIT_ID):
        data = self.ok(
            self.client.post(
                f"/api/test-documents/{ident}/import", json=self.payload(ident)
            )
        )
        return data, next(
            d for d in data["documents"] if d["id"] == data["incorporated_document_id"]
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

    def review_source(self, doc, ident=UNIT_ID):
        data = self.ok(
            self.client.post(
                f"/api/test-documents/{ident}/{doc['id']}/provenance",
                json={
                    "expected_document_version": doc["version"],
                    "decision": "REVIEWED",
                    "reason": REASON,
                },
            )
        )
        return data, next(d for d in data["documents"] if d["id"] == doc["id"])

    def approve(self, data, field, ident=UNIT_ID):
        fact = next(f for f in data["facts"] if f["field"] == field)
        return self.ok(
            self.client.post(
                f"/api/test-research/{ident}/facts/{fact['id']}/review",
                json={
                    "expected_version": data["version"],
                    "expected_fact_version": fact["version"],
                    "decision": "APPROVED",
                    "reason": REASON,
                },
            )
        )

    def test_original_hash_exact_cells_citations_and_no_automatic_approval(self):
        self.assertEqual(len(self.raw), SIZE)
        self.assertEqual(hashlib.sha256(self.raw).hexdigest(), SHA256)
        data, doc = self.incorporate()
        body = doc["body"]
        self.assertEqual(body["extraction_profile"], PROFILE)
        self.assertEqual(body["original"]["sha256"], SHA256)
        self.assertEqual(body["source"]["review_state"], "PENDING")
        self.assertIsNone(body["source"]["declared_consulted_at"])
        self.assertEqual(body["identity"]["ean"], EAN)
        self.assertFalse(body["identity"]["is_combo"])
        self.assertEqual(body["identity"]["presentation"], "200 ml")
        self.assertEqual(len(body["claims"]), 7)
        self.assertTrue(
            all("pagina/2/tabla/stevia/" in c["location"] for c in body["claims"])
        )
        self.assertFalse(
            any("Zucra" in s or "907,20" in s for s in body["sections"].values())
        )
        self.assertEqual(data["facts"], [])
        data = self.extract(data, doc)
        self.assertTrue(
            all(
                f["state"] == "PENDING" and not f["verified"] and f["blockers"]
                for f in data["facts"]
            )
        )
        for fact in data["facts"]:
            self.assertIn(fact["quote"], body["sections"][fact["location"]])
        self.assertEqual(
            self.client.post(
                f"/api/test-proposals/{UNIT_ID}/generate", json={"expected_version": 0}
            ).status_code,
            409,
        )
        original = self.ok(
            self.client.get(f"/api/test-documents/{UNIT_ID}/{doc['id']}/original/1")
        )
        self.assertEqual(base64.b64decode(original["content_base64"]), self.raw)

    def test_explicit_test_reviews_limited_proposal_roundtrip_and_preserved_pack(self):
        before, pack_before = self.workspace(), self.workspace(PACK_ID)
        data, doc = self.incorporate()
        data, doc = self.review_source(doc)
        data = self.extract(data, doc)
        self.assertFalse(any(f["verified"] for f in data["facts"]))
        for field in (
            "product_name",
            "brand",
            "presentation",
            "net_weight",
            "ean",
            "logistic_units",
            "logistic_dun",
        ):
            data = self.approve(data, field)
        self.assertTrue(all(f["verified"] for f in data["facts"]))
        proposal = self.ok(
            self.client.post(
                f"/api/test-proposals/{UNIT_ID}/generate",
                json={"expected_version": before["version"]},
            )
        )
        self.assertEqual(
            proposal["fields"]["title"]["value"], "Hileret Stevia · 200 ml"
        )
        for key in (
            "category",
            "subcategory",
            "manufacturer",
            "proposed_gtin",
            "media",
        ):
            self.assertNotIn(key, proposal["fields"])
        for field in proposal["fields"].values():
            text = str(field["value"])
            self.assertNotIn(DUN, text)
            self.assertNotIn("9 x", text)
            self.assertNotIn("sin gluten", text.lower())
            self.assertTrue(field["evidence_ids"])
        decisions = {
            key: {"decision": "ACCEPTED", "value": field["value"]}
            for key, field in proposal["fields"].items()
        }
        reviewed = self.ok(
            self.client.post(
                f"/api/test-proposals/{UNIT_ID}/{proposal['draft_id']}/review",
                json={
                    "expected_revision": proposal["revision"],
                    "decisions": decisions,
                },
            )
        )
        fields = {
            **before["fields"],
            **{k: v["value"] for k, v in proposal["fields"].items()},
        }
        saved = self.ok(
            self.client.post(
                f"/api/ecomm-app/workspace/{UNIT_ID}",
                json={
                    "fields": fields,
                    "expected_version": before["version"],
                    "status": "DRAFT",
                },
                headers={
                    "X-Kiki-Proposal-Id": str(proposal["draft_id"]),
                    "X-Kiki-Proposal-Revision": str(reviewed["revision"]),
                },
            )
        )
        self.assertEqual(saved, self.workspace())
        self.assertEqual(
            saved["fields"]["description"],
            "Hileret Stevia · 200 ml.\nContenido neto: 200 ml.",
        )
        self.assertEqual(self.workspace(PACK_ID), pack_before)
        report = self.ok(self.client.get("/api/test-commercial-pilot/hileret-200"))[
            "cases"
        ][0]
        self.assertTrue(report["ean_verified_in_test"])
        self.assertEqual(
            report["logistics_verified_in_test"],
            {"logistic_units": "9", "logistic_dun": DUN},
        )
        self.assertIsNone(report["authentic_ecomm_id"])
        self.assertEqual(report["initial_fields"]["title"], "")
        self.assertEqual(report["current_fields"], fields)
        self.assertIn("category", report["blocked_fields"])
        self.assertTrue(
            all(f["verified"] for f in self.case()["facts"])
        )  # compatible editorial values preserve identity

    def test_shared_ean_does_not_authorize_pack6_or_box9(self):
        data, doc = self.incorporate(PACK_ID)
        data, doc = self.review_source(doc, PACK_ID)
        data = self.extract(data, doc, PACK_ID)
        self.assertTrue(all(f["blockers"] and not f["verified"] for f in data["facts"]))
        fact = data["facts"][0]
        self.assertEqual(
            self.client.post(
                f"/api/test-research/{PACK_ID}/facts/{fact['id']}/review",
                json={
                    "expected_version": data["version"],
                    "expected_fact_version": fact["version"],
                    "decision": "APPROVED",
                    "reason": REASON,
                },
            ).status_code,
            409,
        )
        self.assertEqual(
            self.client.post(
                f"/api/test-research/{UNIT_ID}/extract",
                json={
                    "expected_version": self.case()["version"],
                    "document_id": doc["id"],
                    "document_version": doc["version"],
                },
            ).status_code,
            409,
        )
        self.assertIsNone(self.workspace(PACK_ID)["source"]["gtin"])
        self.assertEqual(
            self.client.get(
                "/api/ecomm-app/workspace/PILOT-HILERET-200-BOX9-SYNTHETIC"
            ).status_code,
            403,
        )

    def test_hash_pinning_limits_mime_and_scope_fail_closed(self):
        changed = bytearray(self.raw)
        changed[-10] ^= 1
        self.assertFalse(matches(changed))
        for raw in (bytes(changed), self.raw + b"extra", b"x" * 524289):
            with self.assertRaises(ValueError):
                parse(
                    "hileret-original.pdf",
                    "application/pdf",
                    base64.b64encode(raw).decode(),
                )
        with self.assertRaises(ValueError):
            parse("hileret-original.pdf", "text/plain", self.encoded)
        payload = self.payload()
        payload["content_base64"] = base64.b64encode(changed).decode()
        self.assertEqual(
            self.client.post(
                f"/api/test-documents/{UNIT_ID}/import", json=payload
            ).status_code,
            409,
        )
        self.assertEqual(
            self.client.post(
                "/api/test-documents/900001/import", json=self.payload()
            ).status_code,
            409,
        )
        self.assertEqual(self.case()["facts"], [])

    def test_document_review_versions_concurrency_and_original_retention(self):
        data, doc = self.incorporate()
        barrier = Barrier(2)

        def review(_):
            with operator() as client:
                barrier.wait(timeout=5)
                return client.post(
                    f"/api/test-documents/{UNIT_ID}/{doc['id']}/provenance",
                    json={
                        "expected_document_version": 1,
                        "decision": "REVIEWED",
                        "reason": REASON,
                    },
                ).status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(review, range(2))), [200, 409])
        data = self.case()
        current = next(d for d in data["documents"] if d["id"] == doc["id"])
        self.assertEqual(current["version"], 2)
        self.assertEqual(current["body"]["original"]["sha256"], SHA256)
        for version in (1, 2):
            result = self.ok(
                self.client.get(
                    f"/api/test-documents/{UNIT_ID}/{doc['id']}/original/{version}"
                )
            )
            self.assertEqual(base64.b64decode(result["content_base64"]), self.raw)
        data = self.extract(data, current)
        self.approve(data, "ean")
        fact = next(f for f in data["facts"] if f["field"] == "ean")
        self.assertEqual(
            self.client.post(
                f"/api/test-research/{UNIT_ID}/facts/{fact['id']}/review",
                json={
                    "expected_version": data["version"],
                    "expected_fact_version": fact["version"],
                    "decision": "APPROVED",
                    "reason": REASON,
                },
            ).status_code,
            409,
        )

    def test_restricted_subset_never_invents_missing_commercial_content(self):
        _, doc = self.incorporate()
        data, doc = self.review_source(doc)
        data = self.extract(data, doc)
        self.approve(data, "brand")
        result = self.ok(
            self.client.post(
                f"/api/test-proposals/{UNIT_ID}/generate", json={"expected_version": 0}
            )
        )
        self.assertEqual(set(result["fields"]), {"brand"})
        self.assertEqual(self.workspace()["fields"]["title"], "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
