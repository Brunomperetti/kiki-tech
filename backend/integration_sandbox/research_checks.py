"""Research regressions against real disposable PostgreSQL and existing auth."""

from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import unittest
from .bootstrap import create_sandbox_app

application = create_sandbox_app()

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import delete, select, event, text  # noqa: E402
from app.database.session import engine, SessionLocal  # noqa: E402
from app.database.models import EcommApiProductEdit, CatalogSnapshot, Base  # noqa: E402
from app.integrations.ecomm_app.catalog_stage import STAGE_SOURCE  # noqa: E402
from .research.storage import Dossier, Document, Control, initialize  # noqa: E402


def operator():
    client = TestClient(application, base_url="https://127.0.0.1:8443")
    response = client.post(
        "/api/auth/login",
        json={"username": "operador-prueba", "password": "solo-datos-sinteticos"},
    )
    assert response.status_code == 200
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    return client


class ResearchPostgreSQL(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lifecycle = TestClient(application, base_url="https://127.0.0.1:8443")
        cls.lifecycle.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.lifecycle.__exit__(None, None, None)

    def setUp(self):
        with SessionLocal() as db:
            db.execute(delete(Dossier))
            db.execute(delete(Document))
            db.execute(delete(EcommApiProductEdit))
            db.commit()
        initialize(engine, SessionLocal)
        self.client = operator()
        self.addCleanup(self.client.close)

    def get(self, ident="900001"):
        response = self.client.get("/api/test-research/" + ident)
        self.assertEqual(response.status_code, 200)
        return response.json()

    def extract(self, doc="alm-tecnica", ident="900001"):
        before = self.get(ident)
        current = next(d for d in before["documents"] if d["id"] == doc)
        response = self.client.post(
            f"/api/test-research/{ident}/extract",
            json={
                "expected_version": before["version"],
                "document_id": doc,
                "document_version": current["version"],
            },
        )
        self.assertEqual(response.status_code, 200)
        return response.json()

    def review(self, data, fact, decision="APPROVED", client=None):
        return (client or self.client).post(
            f"/api/test-research/{data['ecomm_id']}/facts/{fact['id']}/review",
            json={
                "expected_version": data["version"],
                "expected_fact_version": fact["version"],
                "decision": decision,
                "reason": "Revisión documental exclusivamente sintética.",
            },
        )

    def test_extraction_pending_provenance_complete_and_no_editor_overwrite(self):
        original = self.client.post(
            "/api/ecomm-app/workspace/900001",
            json={
                "expected_version": 0,
                "status": "DRAFT",
                "fields": {"title": "Título comercial que debe conservarse"},
            },
        ).json()
        data = self.extract()
        self.assertEqual(len(data["facts"]), 6)
        for fact in data["facts"]:
            self.assertEqual(fact["ecomm_id"], "900001")
            self.assertEqual(fact["state"], "PENDING")
            self.assertFalse(fact["verified"])
            for key in (
                "commercial_field",
                "value",
                "presentation",
                "document_id",
                "location",
                "quote",
                "consulted_at",
                "created_by",
                "document_hash",
                "version",
            ):
                self.assertTrue(fact[key])
            self.assertIsNone(fact["reviewer"])
        approved = self.review(data, data["facts"][0])
        self.assertEqual(approved.status_code, 200)
        with SessionLocal() as db:
            saved = db.get(Dossier, "900001")
            self.assertTrue(saved.facts[0]["reviewer"])
            edit = db.scalar(select(EcommApiProductEdit))
            self.assertEqual(edit.fields, original["fields"])
            self.assertEqual(edit.version, 1)
        self.assertFalse(approved.json()["commercial_fields_applied"])

    def test_shared_sku_keeps_separate_variants_and_incompatible_ean_pack_block_approval(
        self,
    ):
        first = self.extract("alm-pack-1kg")
        fact = first["facts"][0]
        self.assertTrue(any("Presentación" in issue for issue in fact["blockers"]))
        self.assertEqual(self.review(first, fact).status_code, 409)
        second = self.extract("alm-pack-1kg", "900002")
        self.assertEqual(first["identity"]["sku"], second["identity"]["sku"])
        self.assertNotEqual(first["facts"][0]["id"], second["facts"][0]["id"])
        self.assertEqual(self.review(second, second["facts"][0]).status_code, 200)
        ean = self.extract("alm-ean-incompatible")
        fact = next(
            f for f in ean["facts"] if f["document_id"] == "alm-ean-incompatible"
        )
        self.assertTrue(any("EAN" in issue for issue in fact["blockers"]))
        self.assertEqual(self.review(ean, fact).status_code, 409)

    def test_missing_units_and_unbacked_claims_are_never_verified(self):
        data = self.extract("alm-incompleta")
        self.assertEqual(len(data["facts"]), 2)
        for fact in data["facts"]:
            self.assertTrue(fact["blockers"])
            self.assertEqual(self.review(data, fact).status_code, 409)
        self.assertIn("Ingredientes", data["missing"])

    def test_contradiction_invalidates_previous_approval_requires_explicit_resolution(
        self,
    ):
        data = self.extract()
        fact = next(f for f in data["facts"] if f["field"] == "nutrition.energy")
        self.assertEqual(self.review(data, fact).status_code, 200)
        data = self.extract("alm-nutricion-conflicto")
        approved = next(
            f
            for f in data["facts"]
            if f["document_id"] == "alm-tecnica" and f["field"] == "nutrition.energy"
        )
        other = next(
            f for f in data["facts"] if f["document_id"] == "alm-nutricion-conflicto"
        )
        self.assertEqual(approved["state"], "STALE")
        self.assertFalse(approved["verified"])
        self.assertTrue(any("contradictorio" in item for item in other["blockers"]))
        self.assertEqual(self.review(data, other).status_code, 409)
        rejected = self.review(data, other, "REJECTED")
        self.assertEqual(rejected.status_code, 200)
        data = self.extract()
        target = next(
            f
            for f in data["facts"]
            if f["document_id"] == "alm-tecnica" and f["field"] == "nutrition.energy"
        )
        self.assertEqual(target["state"], "PENDING")
        self.assertEqual(self.review(data, target).status_code, 200)

    def test_revocation_is_persisted_with_reviewer_reason_and_history(self):
        data = self.extract()
        data = self.review(data, data["facts"][0]).json()
        fact = data["facts"][0]
        data = self.review(data, fact, "REVOKED").json()
        self.assertEqual(data["facts"][0]["state"], "REVOKED")
        self.assertFalse(data["facts"][0]["verified"])
        fresh = operator()
        try:
            recovered = fresh.get("/api/test-research/900001").json()
            self.assertEqual(len(recovered["facts"][0]["history"]), 3)
            self.assertTrue(
                all(
                    event["actor"] and event["reason"]
                    for event in recovered["facts"][0]["history"]
                )
            )
        finally:
            fresh.close()

    def test_document_revision_invalidates_before_reextraction_and_keeps_old_fragment(
        self,
    ):
        data = self.extract()
        fact = next(f for f in data["facts"] if f["field"] == "nutrition.energy")
        self.assertEqual(self.review(data, fact).status_code, 200)
        response = self.client.post(
            "/api/test-research/documents/alm-tecnica/revision",
            json={"expected_version": 1, "new_version": 2},
        )
        self.assertEqual(response.status_code, 200)
        data = self.get()
        old = next(f for f in data["facts"] if f["field"] == "nutrition.energy")
        self.assertEqual(old["state"], "STALE")
        self.assertEqual(old["value"], "600")
        self.assertEqual(self.review(data, old).status_code, 409)
        data = self.extract()
        current = next(f for f in data["facts"] if f["field"] == "nutrition.energy")
        self.assertEqual(current["value"], "620")
        self.assertFalse(current["verified"])
        self.assertTrue(
            any(event["before"].get("value") == "600" for event in current["history"])
        )
        self.assertIn(
            "600",
            str(
                next(doc for doc in data["documents"] if doc["id"] == "alm-tecnica")[
                    "history"
                ]
            ),
        )

    def test_changed_value_and_presentation_invalidate_verified_fingerprint(self):
        for key, value in [("value", "100"), ("presentation", "1 kg")]:
            with self.subTest(key=key):
                self.setUp()
                data = self.extract()
                fact = next(
                    f for f in data["facts"] if f["field"] == "nutrition.energy"
                )
                self.assertEqual(self.review(data, fact).status_code, 200)
                with SessionLocal() as db:
                    item = db.get(Dossier, "900001")
                    changed = deepcopy(item.facts)
                    next(f for f in changed if f["id"] == fact["id"])[key] = value
                    item.facts = changed
                    db.commit()
                current = next(f for f in self.get()["facts"] if f["id"] == fact["id"])
                self.assertEqual(current["state"], "STALE")
                self.assertFalse(current["verified"])

    def test_source_identity_change_invalidates_and_blocks_reuse(self):
        data = self.extract()
        self.assertEqual(self.review(data, data["facts"][0]).status_code, 200)
        with SessionLocal() as db:
            capture = db.scalar(
                select(CatalogSnapshot).where(CatalogSnapshot.source == STAGE_SOURCE)
            )
            original = deepcopy(capture.payload)
            changed = deepcopy(original)
            changed[0]["items"][0]["variants"][0]["description"] = "750 g"
            capture.payload = changed
            db.commit()
            try:
                data = self.get()
                self.assertTrue(
                    all(
                        f["state"] == "STALE" and not f["verified"]
                        for f in data["facts"]
                    )
                )
                self.assertEqual(self.review(data, data["facts"][0]).status_code, 409)
            finally:
                capture.payload = original
                db.commit()

    def test_two_postgresql_sessions_cannot_overwrite_one_decision(self):
        data = self.extract()
        fact = data["facts"][0]
        clients = [operator(), operator()]
        barrier = Barrier(2)

        def synchronize(
            _connection, _cursor, statement, _parameters, _context, _executemany
        ):
            if "kiki_research_test.control" in statement and "FOR UPDATE" in statement:
                barrier.wait(timeout=10)

        event.listen(engine, "before_cursor_execute", synchronize)
        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                responses = list(
                    pool.map(
                        lambda i: self.review(
                            data, fact, "APPROVED" if i == 0 else "REJECTED", clients[i]
                        ),
                        [0, 1],
                    )
                )
        finally:
            event.remove(engine, "before_cursor_execute", synchronize)
            for client in clients:
                client.close()
        self.assertEqual(
            sorted(response.status_code for response in responses), [200, 409]
        )
        recovered = self.get()
        self.assertEqual(recovered["version"], data["version"] + 1)
        self.assertEqual(recovered["facts"][0]["version"], fact["version"] + 1)
        self.assertEqual(len(recovered["facts"][0]["history"]), 2)

    def test_schema_is_additive_csrf_and_external_requests_stay_blocked(self):
        with engine.connect() as connection:
            count = connection.scalar(
                text(
                    "SELECT count(*) FROM information_schema.tables WHERE table_schema='kiki_research_test'"
                )
            )
            self.assertEqual(count, 3)
        self.assertFalse(
            any(
                table.schema == "kiki_research_test"
                for table in Base.metadata.tables.values()
            )
        )
        self.client.headers.pop("X-CSRF-Token")
        self.assertEqual(
            self.client.post("/api/test-research/900001/extract", json={}).status_code,
            403,
        )
        for path in [
            "/api/test-research/search",
            "/api/test-research/900999",
            "/api/test-research/900001/apply",
            "/api/ecomm-app/stage/manual/start",
            "/api/mercadolibre/sync",
        ]:
            self.assertEqual(self.client.post(path).status_code, 403)

    def test_missing_canonical_identity_persists_invalidation_and_no_replacement(self):
        data = self.extract()
        self.assertEqual(self.review(data, data["facts"][0]).status_code, 200)
        with SessionLocal() as db:
            capture = db.scalar(
                select(CatalogSnapshot).where(CatalogSnapshot.source == STAGE_SOURCE)
            )
            original = deepcopy(capture.payload)
            changed = deepcopy(original)
            changed[0]["items"][0]["variants"][0]["id"] = 999999
            capture.payload = changed
            db.commit()
            try:
                self.assertEqual(
                    self.client.get("/api/test-research/900001").status_code, 409
                )
                item = db.get(Dossier, "900001")
                self.assertTrue(all(f["state"] == "STALE" for f in item.facts))
            finally:
                capture.payload = original
                db.commit()

    def test_reextracting_unchanged_rejected_document_keeps_decision_and_version(self):
        data = self.extract("alm-nutricion-conflicto")
        rejected = self.review(data, data["facts"][0], "REJECTED").json()
        repeated = self.extract("alm-nutricion-conflicto")
        self.assertEqual(repeated["version"], rejected["version"])
        self.assertEqual(repeated["facts"][0]["state"], "REJECTED")
        self.assertEqual(
            repeated["facts"][0]["version"], rejected["facts"][0]["version"]
        )

    def test_missing_transaction_control_fails_closed(self):
        with SessionLocal() as db:
            db.execute(delete(Control))
            db.commit()
        try:
            self.assertEqual(
                self.client.get("/api/test-research/900001").status_code, 503
            )
        finally:
            initialize(engine, SessionLocal)


if __name__ == "__main__":
    unittest.main(verbosity=2)
