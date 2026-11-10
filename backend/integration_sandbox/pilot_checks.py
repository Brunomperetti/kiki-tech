"""Pilot preparation on real disposable PostgreSQL; ONLY synthetic documents."""

import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import hashlib
from threading import Barrier
import unittest
from .bootstrap import create_sandbox_app

application = create_sandbox_app()

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import delete, event  # noqa: E402
from app.database.session import SessionLocal, engine  # noqa: E402
from app.database.models import EcommApiProductEdit, KikiAiEditorialDraft  # noqa: E402
from .research.storage import Dossier, Document, initialize, digest  # noqa: E402
from .document_test_fixtures import TEXT  # noqa: E402

ROOT = "/api/test-research/900001"
DOCUMENTS = "/api/test-documents/900001"
CONTEXT = "/api/test-proposals/900001/generation-context"


def operator():
    client = TestClient(application, base_url="https://127.0.0.1:8443")
    r = client.post(
        "/api/auth/login",
        json={"username": "operador-prueba", "password": "solo-datos-sinteticos"},
    )
    assert r.status_code == 200
    client.headers["X-CSRF-Token"] = r.json()["csrf_token"]
    return client


class PilotPostgreSQL(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lifecycle = TestClient(application, base_url="https://127.0.0.1:8443")
        cls.lifecycle.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.lifecycle.__exit__(None, None, None)

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

    def case(self):
        return self.ok(self.client.get(ROOT))

    def payload(self, text=TEXT, **extra):
        return {
            "kind": "FILE",
            "expected_version": self.case()["version"],
            "filename": "fixture-sintetico.txt",
            "content_type": "text/plain",
            "content_base64": base64.b64encode(text.encode()).decode(),
            "provenance_note": "Documento SINTÉTICO suministrado para probar el piloto sin fabricante real.",
            "reference_url": "https://fabricante-prueba.invalid/documento",
            "declared_manufacturer": "Fabricante declarado de prueba",
            "declared_consulted_at": "2026-01-01T12:00:00Z",
            "declared_official": True,
            "authorized_local_processing": True,
            **extra,
        }

    def prepare(self, text=TEXT):
        data = self.ok(self.client.post(DOCUMENTS + "/import", json=self.payload(text)))
        key = data["incorporated_document_id"]
        doc = next(d for d in data["documents"] if d["id"] == key)
        data = self.ok(
            self.client.post(
                f"{DOCUMENTS}/{key}/provenance",
                json={
                    "expected_document_version": doc["version"],
                    "decision": "REVIEWED",
                    "reason": "Revisión explícita de la procedencia de un documento SINTÉTICO.",
                },
            )
        )
        doc = next(d for d in data["documents"] if d["id"] == key)
        data = self.ok(
            self.client.post(
                ROOT + "/extract",
                json={
                    "expected_version": data["version"],
                    "document_id": key,
                    "document_version": doc["version"],
                },
            )
        )
        return data, key

    def review(self, data, fact):
        return self.client.post(
            ROOT + f"/facts/{fact['id']}/review",
            json={
                "expected_version": data["version"],
                "expected_fact_version": fact["version"],
                "decision": "APPROVED",
                "reason": "Verifiqué la cita exacta del documento SINTÉTICO suministrado.",
            },
        )

    def test_manual_provenance_metadata_original_and_history_persist_without_official_assumption(
        self,
    ):
        data, key = self.prepare()
        doc = next(d for d in data["documents"] if d["id"] == key)
        self.assertEqual(
            doc["body"]["source"]["declared_manufacturer"],
            "Fabricante declarado de prueba",
        )
        self.assertEqual(
            doc["body"]["identity"]["manufacturer"], "Fabricante de prueba"
        )
        self.assertEqual(
            doc["body"]["source"]["declared_consulted_at"], "2026-01-01T12:00:00+00:00"
        )
        self.assertEqual(doc["body"]["source"]["review_state"], "REVIEWED")
        self.assertFalse(any(f["verified"] for f in data["facts"]))
        original = self.ok(self.client.get(f"{DOCUMENTS}/{key}/original/1"))
        raw = base64.b64decode(original["content_base64"])
        self.assertEqual(raw, TEXT.encode())
        self.assertEqual(
            hashlib.sha256(raw).hexdigest(), doc["body"]["original"]["sha256"]
        )
        document_reads = []

        def count_reads(conn, cursor, statement, parameters, context, many):
            if (
                statement.lstrip().upper().startswith("SELECT")
                and "kiki_research_test.documents" in statement
            ):
                document_reads.append(statement)

        event.listen(engine, "before_cursor_execute", count_reads)
        try:
            reloaded = self.case()
        finally:
            event.remove(engine, "before_cursor_execute", count_reads)
        self.assertLessEqual(
            len(document_reads), 3, "No recargar documentos por cada par de hechos."
        )
        self.assertEqual(reloaded["version"], data["version"])
        self.assertTrue(
            any(h["action"] == "PROVENANCE_REVIEWED" for h in reloaded["history"])
        )

    def test_context_approved_only_quotes_versions_no_generation_or_business_writes(
        self,
    ):
        data, key = self.prepare()
        fact = next(
            f
            for f in data["facts"]
            if f["document_id"] == key and f["field"] == "ingredients"
        )
        self.assertEqual(self.ok(self.client.get(CONTEXT))["facts"], [])
        data = self.ok(self.review(data, fact))
        writes = []

        def track(conn, cursor, statement, parameters, context, many):
            if (
                statement.lstrip()
                .upper()
                .startswith(
                    (
                        "INSERT INTO KIKI_AI_EDITORIAL_DRAFT",
                        "INSERT INTO ECOMM_API_PRODUCT_EDITS",
                        "UPDATE ECOMM_API_PRODUCT_EDITS",
                    )
                )
            ):
                writes.append(statement)

        event.listen(engine, "before_cursor_execute", track)
        try:
            context = self.ok(self.client.get(CONTEXT))
        finally:
            event.remove(engine, "before_cursor_execute", track)
        self.assertEqual(writes, [])
        self.assertEqual(context["provider"]["calls"], 0)
        self.assertFalse(context["provider"]["enabled"])
        self.assertEqual(context["controls"]["max_cost_usd"], "0.00")
        self.assertEqual(len(context["facts"]), 1)
        self.assertEqual(context["facts"][0]["quote"], fact["quote"])
        self.assertEqual(context["facts"][0]["document_hash"], fact["document_hash"])
        self.assertEqual(
            context["context_hash"],
            digest({k: v for k, v in context.items() if k != "context_hash"}),
        )
        self.assertEqual(context, self.ok(self.client.get(CONTEXT)))
        workspace = self.ok(self.client.get("/api/ecomm-app/workspace/900001"))
        self.ok(
            self.client.post(
                "/api/ecomm-app/workspace/900001",
                json={
                    "expected_version": workspace["version"],
                    "status": "DRAFT",
                    "fields": {
                        **workspace["fields"],
                        "title": "Edición sintética posterior",
                    },
                },
            )
        )
        self.assertNotEqual(
            context["context_hash"], self.ok(self.client.get(CONTEXT))["context_hash"]
        )

    def test_incorrect_identity_and_conflicting_sources_never_enter_ai_context(self):
        data, key = self.prepare(TEXT.replace("12345670", "12345687"))
        fact = next(
            f
            for f in data["facts"]
            if f["document_id"] == key and f["field"] == "ingredients"
        )
        self.assertEqual(self.review(data, fact).status_code, 409)
        self.assertEqual(self.ok(self.client.get(CONTEXT))["facts"], [])
        data, key = self.prepare()
        data, other = self.prepare(TEXT.replace("600 kcal", "610 kcal"))
        for fact in [
            f
            for f in data["facts"]
            if f["document_id"] in {key, other} and f["field"] == "nutrition.energy"
        ]:
            self.assertTrue(any("contradictorio" in x for x in fact["blockers"]))
            self.assertEqual(self.review(data, fact).status_code, 409)
        self.assertEqual(self.ok(self.client.get(CONTEXT))["facts"], [])

    def test_manual_metadata_validation_auth_and_no_network_activation_api(self):
        for date in [
            "2026-01-01",
            (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        ]:
            self.assertEqual(
                self.client.post(
                    DOCUMENTS + "/import", json=self.payload(declared_consulted_at=date)
                ).status_code,
                422,
            )
        with TestClient(application, base_url="https://127.0.0.1:8443") as anonymous:
            self.assertEqual(
                anonymous.get("/api/test-discovery/pilot-status").status_code, 401
            )
            self.assertEqual(anonymous.get(CONTEXT).status_code, 401)
        status = self.ok(self.client.get("/api/test-discovery/pilot-status"))
        self.assertTrue(status["release_locked"])
        self.assertEqual(status["authorized_domains"], [])
        for path in [
            "/api/test-discovery/pilot-status",
            "/api/test-discovery/enable",
            CONTEXT,
            "/api/test-proposals/real/generation-context",
        ]:
            self.assertEqual(
                self.client.post(path, json={"network_enabled": True}).status_code, 403
            )

    def test_concurrent_provenance_decisions_preserve_cas_and_originals(self):
        data, key = self.prepare()
        doc = next(d for d in data["documents"] if d["id"] == key)
        barrier = Barrier(2)

        def decide(decision):
            with operator() as client:
                barrier.wait(timeout=5)
                return client.post(
                    f"{DOCUMENTS}/{key}/provenance",
                    json={
                        "expected_document_version": doc["version"],
                        "decision": decision,
                        "reason": "Revisión concurrente explícita del mismo documento SINTÉTICO.",
                    },
                ).status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(decide, ["REVIEWED", "REJECTED"]))
        self.assertEqual(sorted(results), [200, 409])
        self.assertEqual(
            self.ok(self.client.get(f"{DOCUMENTS}/{key}/original/1"))["content_base64"],
            base64.b64encode(TEXT.encode()).decode(),
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
