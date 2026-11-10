"""2F real PostgreSQL tests: evidence lineage, existing editor CAS, no providers."""

from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import unittest
from .bootstrap import create_sandbox_app

application = create_sandbox_app()

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import delete, select, event  # noqa: E402
from app.database.session import SessionLocal, engine  # noqa: E402
from app.database.models import (  # noqa: E402
    EcommApiProductEdit,
    KikiAiEditorialDraft,
    CatalogSnapshot,
    KikiEcommAiDailySlot,
)
from app.core.config import get_settings  # noqa: E402
from .research.storage import Dossier, Document, initialize  # noqa: E402


def operator():
    client = TestClient(application, base_url="https://127.0.0.1:8443")
    response = client.post(
        "/api/auth/login",
        json={
            "username": "operador-prueba",
            "password": "solo-datos-sinteticos",
        },
    )
    assert response.status_code == 200
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    return client


class ProposalPostgreSQL(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lifecycle = TestClient(application, base_url="https://127.0.0.1:8443")
        cls.lifecycle.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.lifecycle.__exit__(None, None, None)

    def setUp(self):
        with SessionLocal() as db:
            for table in (KikiAiEditorialDraft, EcommApiProductEdit, Dossier, Document):
                db.execute(delete(table))
            db.commit()
        initialize(engine, SessionLocal)
        self.client = operator()
        self.addCleanup(self.client.close)

    def ok(self, response):
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def research(self, ident="900001"):
        return self.ok(self.client.get("/api/test-research/" + ident))

    def document(self, name, ident="900001", approve=True, omit=()):
        case = self.research(ident)
        doc = next(d for d in case["documents"] if d["id"] == name)
        case = self.ok(
            self.client.post(
                f"/api/test-research/{ident}/extract",
                json={
                    "expected_version": case["version"],
                    "document_id": name,
                    "document_version": doc["version"],
                },
            )
        )
        if approve:
            for fact in [
                f
                for f in case["facts"]
                if f["document_id"] == name and f["field"] not in omit
            ]:
                current = next(f for f in case["facts"] if f["id"] == fact["id"])
                case = self.ok(
                    self.client.post(
                        f"/api/test-research/{ident}/facts/{fact['id']}/review",
                        json={
                            "expected_version": case["version"],
                            "expected_fact_version": current["version"],
                            "decision": "APPROVED",
                            "reason": "Contraste individual de documento sintético de prueba.",
                        },
                    )
                )
        return case

    def workspace(self, ident="900001"):
        return self.ok(self.client.get("/api/ecomm-app/workspace/" + ident))

    def full(self):
        self.document("alm-clasificacion")
        self.document("alm-tecnica")
        return self.generate()

    def generate(self, ident="900001"):
        return self.ok(
            self.client.post(
                f"/api/test-proposals/{ident}/generate",
                json={
                    "expected_version": self.workspace(ident)["version"],
                },
            )
        )

    def reviewed(self, proposal, keys=("title", "description"), values=None):
        decisions = {
            key: {
                "decision": "ACCEPTED",
                "value": (values or {}).get(key, proposal["fields"][key]["value"]),
            }
            for key in keys
        }
        return self.ok(
            self.client.post(
                f"/api/test-proposals/{proposal['ecomm_id']}/{proposal['draft_id']}/review",
                json={
                    "expected_revision": proposal["revision"],
                    "decisions": decisions,
                },
            )
        )

    def apply(self, proposal, client=None, extra=None):
        fields = deepcopy(proposal["base_fields"])
        for key, decision in proposal["decisions"].items():
            if decision["decision"] == "ACCEPTED":
                fields[key] = decision["value"]
        fields.update(extra or {})
        return (client or self.client).post(
            "/api/ecomm-app/workspace/" + proposal["ecomm_id"],
            headers={
                "X-Kiki-Proposal-Id": str(proposal["draft_id"]),
                "X-Kiki-Proposal-Revision": str(proposal["revision"]),
            },
            json={
                "expected_version": proposal["workspace_version"],
                "status": "DRAFT",
                "fields": fields,
            },
        )

    def latest(self):
        return self.ok(self.client.get("/api/test-proposals/900001"))

    def test_complete_proposal_existing_draft_storage_lineage_and_no_automatic_writes(
        self,
    ):
        before = self.workspace()
        proposal = self.full()
        self.assertEqual(self.workspace(), before)
        self.assertEqual(len(proposal["fields"]), 13)
        self.assertEqual(proposal["generator"], "deterministic-synthetic-evidence-v1")
        self.assertTrue(proposal["source_current"])
        self.assertEqual(len(proposal["evidence"]), 12)
        for key, field in proposal["fields"].items():
            self.assertTrue(field["evidence_ids"], key)
            for fact_id in field["evidence_ids"]:
                fact = next(f for f in proposal["evidence"] if f["id"] == fact_id)
                self.assertEqual(fact["ecomm_id"], "900001")
                self.assertEqual(fact["state"], "APPROVED")
                self.assertTrue(
                    fact["quote"] and fact["version"] and fact["document_hash"]
                )
        with SessionLocal() as db:
            self.assertIsNotNone(db.get(KikiAiEditorialDraft, proposal["draft_id"]))
            self.assertIsNone(db.scalar(select(KikiEcommAiDailySlot)))

    def test_missing_ingredients_never_fill_claims_or_unverified_identity(self):
        self.document("alm-clasificacion")
        self.document("alm-tecnica", omit=("ingredients",))
        proposal = self.generate()
        text = str(proposal["fields"])
        self.assertNotIn("Ingredientes:", text)
        self.assertTrue(any("Ingredientes:" in x for x in proposal["missing"]))
        self.assertNotIn("media", proposal["fields"])
        self.assertNotIn("sources", proposal["fields"])
        self.assertNotIn("proposed_gtin", proposal["fields"])
        empty = self.generate("900003")
        self.assertEqual(
            empty["fields"], {}
        )  # no title derived from unverified API name

    def test_contradictory_nutrition_excluded_and_invalidates_generated_proposal(self):
        proposal = self.full()
        self.document("alm-nutricion-conflicto", approve=False)
        self.assertFalse(self.latest()["source_current"])
        current = self.generate()
        self.assertNotIn("Energía:", str(current["fields"]))
        self.assertTrue(any("Energía:" in x for x in current["missing"]))
        response = self.client.post(
            f"/api/test-proposals/900001/{proposal['draft_id']}/review",
            json={
                "expected_revision": proposal["revision"],
                "decisions": {
                    "title": {
                        "decision": "ACCEPTED",
                        "value": proposal["fields"]["title"]["value"],
                    }
                },
            },
        )
        self.assertEqual(response.status_code, 409)

    def test_selected_edited_fields_saved_reloaded_history_rejected_and_media_preserved(
        self,
    ):
        fields = self.workspace()["fields"]
        fields.update(
            title="Título anterior aprobado por operador",
            brand="Marca sintética KIKI",
            manufacturer="Fabricante de prueba",
            category="Categoría manual",
            media=[
                {
                    "kind": "IMAGE",
                    "url": "https://synthetic.invalid/a.jpg",
                    "alt": "Prueba",
                    "source_url": "https://synthetic.invalid/procedencia",
                }
            ],
        )
        self.ok(
            self.client.post(
                "/api/ecomm-app/workspace/900001",
                json={"expected_version": 0, "status": "DRAFT", "fields": fields},
            )
        )
        proposal = self.full()
        edited = "\n".join(reversed(proposal["fields"]["description"]["clauses"][:2]))
        reviewed = self.reviewed(
            proposal, ("title", "description"), {"description": edited}
        )
        # Explicit rejection of category is recorded, while unchanged fields retain values.
        decisions = {
            **reviewed["decisions"],
            "category": {"decision": "REJECTED", "value": "Dietética"},
        }
        reviewed = self.ok(
            self.client.post(
                f"/api/test-proposals/900001/{proposal['draft_id']}/review",
                json={
                    "expected_revision": reviewed["revision"],
                    "decisions": decisions,
                },
            )
        )
        saved = self.ok(self.apply(reviewed))
        self.assertEqual(saved["version"], 2)
        self.assertEqual(saved["fields"]["description"], edited)
        self.assertEqual(saved["fields"]["category"], "Categoría manual")
        self.assertEqual(saved["fields"]["media"], fields["media"])
        self.assertEqual(saved["fields"]["manufacturer"], fields["manufacturer"])
        self.assertEqual(
            saved["history"][-1]["changes"]["title"]["before"], fields["title"]
        )
        self.assertEqual(self.workspace()["fields"], saved["fields"])
        self.assertEqual(self.latest()["state"], "APPLIED")
        self.assertEqual(self.apply(reviewed).status_code, 409)

    def test_text_without_source_or_unselected_extra_field_cannot_be_saved(self):
        proposal = self.full()
        for value in (
            "Sin gluten. Producto orgánico.",
            "No contiene almendras.",
            "Peso: 900001 g.",
            "Ingredientes: Almendras.\nSin alérgenos.",
        ):
            response = self.client.post(
                f"/api/test-proposals/900001/{proposal['draft_id']}/review",
                json={
                    "expected_revision": proposal["revision"],
                    "decisions": {
                        "description": {"decision": "ACCEPTED", "value": value}
                    },
                },
            )
            self.assertEqual(response.status_code, 409)
        reviewed = self.reviewed(proposal)
        self.assertEqual(
            self.apply(reviewed, extra={"brand": "Marca inventada"}).status_code, 409
        )
        self.assertEqual(self.workspace()["version"], 0)
        self.assertEqual(self.latest()["state"], "REVIEWED")

    def test_different_presentations_and_related_sku_pack_do_not_share_facts(self):
        self.full()
        self.document("alm-pack-1kg", ident="900002")
        kilogram = self.generate("900002")
        self.assertNotIn("title", kilogram["fields"])
        self.assertTrue(
            all(
                f["ecomm_id"] == "900002" and f["presentation"] == "1 kg"
                for f in kilogram["evidence"]
            )
        )
        with SessionLocal() as db:
            capture = db.scalar(select(CatalogSnapshot))
            original = deepcopy(capture.payload)
            changed = deepcopy(original)
            changed[0]["items"][1]["variants"][0].update(
                description="Pack x2 de 250 g", is_combo=True
            )
            capture.payload = changed
            db.commit()
        try:
            self.document("alm-pack-x2", ident="900002")
            pack = self.generate("900002")
            self.assertEqual(
                pack["fields"]["title"]["value"],
                "Almendras sintéticas · Pack x2 de 250 g",
            )
            self.assertNotIn("Ingredientes:", str(pack["fields"]))
            self.assertTrue(all(f["ecomm_id"] == "900002" for f in pack["evidence"]))
        finally:
            with SessionLocal() as db:
                db.scalar(select(CatalogSnapshot)).payload = original
                db.commit()

    def test_revocation_after_review_blocks_apply_without_commercial_effect(self):
        reviewed = self.reviewed(self.full())
        case = self.research()
        fact = next(f for f in case["facts"] if f["field"] == "ingredients")
        self.ok(
            self.client.post(
                f"/api/test-research/900001/facts/{fact['id']}/review",
                json={
                    "expected_version": case["version"],
                    "expected_fact_version": fact["version"],
                    "decision": "REVOKED",
                    "reason": "Revocación de prueba posterior a la generación.",
                },
            )
        )
        self.assertEqual(self.apply(reviewed).status_code, 409)
        self.assertEqual(self.workspace()["version"], 0)
        self.assertEqual(self.latest()["state"], "STALE")

    def test_document_revision_invalidates_and_blocks_apply(self):
        reviewed = self.reviewed(self.full())
        self.ok(
            self.client.post(
                "/api/test-research/documents/alm-tecnica/revision",
                json={"expected_version": 1, "new_version": 2},
            )
        )
        self.assertEqual(self.apply(reviewed).status_code, 409)
        self.assertEqual(self.workspace()["version"], 0)
        self.assertFalse(self.latest()["source_current"])

    def test_changed_workspace_invalidates_even_for_disjoint_fields(self):
        reviewed = self.reviewed(self.full())
        fields = self.workspace()["fields"]
        fields["note"] = "Otro operador guardó una observación."
        self.ok(
            self.client.post(
                "/api/ecomm-app/workspace/900001",
                json={"expected_version": 0, "status": "DRAFT", "fields": fields},
            )
        )
        self.assertEqual(self.apply(reviewed).status_code, 409)
        self.assertEqual(self.workspace()["fields"]["note"], fields["note"])
        self.assertEqual(self.latest()["state"], "STALE")

    def test_two_operators_apply_same_base_only_one_writes_real_postgres(self):
        reviewed = self.reviewed(self.full())
        clients = [operator(), operator()]
        barrier = Barrier(2)

        def synchronize(
            _connection, _cursor, statement, _parameters, _context, _executemany
        ):
            if "kiki_research_test.control" in statement and "FOR UPDATE" in statement:
                barrier.wait(timeout=10)

        event.listen(engine, "before_cursor_execute", synchronize)
        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                responses = list(
                    executor.map(lambda client: self.apply(reviewed, client), clients)
                )
        finally:
            event.remove(engine, "before_cursor_execute", synchronize)
            for client in clients:
                client.close()
        self.assertEqual(sorted(r.status_code for r in responses), [200, 409])
        self.assertEqual(self.workspace()["version"], 1)
        self.assertEqual(len(self.workspace()["history"]), 1)
        self.assertEqual(self.latest()["state"], "APPLIED")

    def test_auth_csrf_routes_and_real_ai_remain_blocked(self):
        anonymous = TestClient(application, base_url="https://127.0.0.1:8443")
        try:
            self.assertEqual(
                anonymous.get("/api/test-proposals/900001").status_code, 401
            )
            self.assertEqual(
                anonymous.post(
                    "/api/test-proposals/900001/generate", json={"expected_version": 0}
                ).status_code,
                401,
            )
        finally:
            anonymous.close()
        token = self.client.headers.pop("X-CSRF-Token")
        self.assertEqual(
            self.client.post(
                "/api/test-proposals/900001/generate", json={"expected_version": 0}
            ).status_code,
            403,
        )
        self.client.headers["X-CSRF-Token"] = token
        for path in (
            "/api/test-proposals/1/generate",
            "/api/ecomm-app/workspace/ai/900001/suggest",
            "/api/mercadolibre/sync",
            "/api/test-proposals/bulk",
        ):
            self.assertEqual(self.client.post(path).status_code, 403)
        settings = get_settings()
        self.assertFalse(
            settings.kiki_ai_enabled
            or settings.kiki_ai_api_key
            or settings.ml_client_secret
            or settings.ecomm_app_api_token
        )

    def test_provenance_change_with_identical_canonical_values_does_not_revoke_facts(
        self,
    ):
        proposal = self.full()
        reviewed = self.reviewed(proposal, ("brand", "manufacturer", "presentation"))
        self.ok(self.apply(reviewed))
        self.assertEqual(
            len([f for f in self.research()["facts"] if f["verified"]]), 12
        )

    def test_approved_commercial_record_is_untouched_until_explicit_selected_save(self):
        generated = self.full()
        fields = deepcopy(generated["base_fields"])
        fields.update(
            {key: proposed["value"] for key, proposed in generated["fields"].items()}
        )
        fields.update(
            title="Título ya aprobado por una persona",
            seo_keywords="almendras, prueba",
            sources=[
                {
                    "kind": "ETIQUETA",
                    "name": "Etiqueta sintética",
                    "url": "",
                    "note": "Verificación manual exclusivamente de prueba.",
                    "verified": True,
                }
            ],
            media=[
                {
                    "kind": "IMAGE",
                    "url": "https://synthetic.invalid/imagen.jpg",
                    "alt": "Prueba",
                    "source_url": "",
                }
            ],
        )
        approved = self.ok(
            self.client.post(
                "/api/ecomm-app/workspace/900001",
                json={
                    "expected_version": 0,
                    "status": "READY_FOR_CHANNELS",
                    "fields": fields,
                },
            )
        )
        proposal = self.generate()
        reviewed = self.reviewed(proposal, ("title",))
        self.assertEqual(self.workspace(), approved)
        saved = self.ok(self.apply(reviewed))
        self.assertEqual(saved["status"], "DRAFT")
        self.assertEqual(saved["version"], 2)
        self.assertEqual(saved["fields"]["media"], fields["media"])
        self.assertEqual(saved["fields"]["sources"], fields["sources"])
        self.assertEqual(saved["history"][-1]["previous_status"], "READY_FOR_CHANNELS")

    def test_canonical_presentation_changes_after_generation_block_application(self):
        reviewed = self.reviewed(self.full())
        with SessionLocal() as db:
            capture = db.scalar(select(CatalogSnapshot))
            original = deepcopy(capture.payload)
            changed = deepcopy(original)
            changed[0]["items"][0]["variants"][0]["description"] = "500 g"
            capture.payload = changed
            db.commit()
        try:
            self.assertEqual(self.apply(reviewed).status_code, 409)
            self.assertEqual(self.workspace()["version"], 0)
            self.assertEqual(self.latest()["state"], "STALE")
        finally:
            with SessionLocal() as db:
                db.scalar(select(CatalogSnapshot)).payload = original
                db.commit()

    def test_misassigned_fact_is_not_authorized_even_with_shared_sku(self):
        reviewed = self.reviewed(self.full())
        with SessionLocal() as db:
            dossier = db.get(Dossier, "900001")
            facts = deepcopy(dossier.facts)
            next(f for f in facts if f["field"] == "ingredients")["ecomm_id"] = "900002"
            dossier.facts = facts
            db.commit()
        self.assertEqual(self.apply(reviewed).status_code, 409)
        proposal = self.generate()
        self.assertNotIn("Ingredientes:", str(proposal["fields"]))
        self.assertTrue(all(f["ecomm_id"] == "900001" for f in proposal["evidence"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
