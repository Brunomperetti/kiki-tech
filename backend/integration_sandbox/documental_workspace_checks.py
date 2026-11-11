"""Ordinary authenticated routes, actual disposable PostgreSQL and bounded parser."""

import base64
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
from pathlib import Path
from threading import Barrier
import unittest

from .editor_checks import application, operator
from fastapi.testclient import TestClient
from sqlalchemy import delete, text
from app.database.session import SessionLocal, engine
from app.database.models import EcommApiProductEdit, KikiAiEditorialDraft
from app.services.documental.storage import Document, Dossier
from app.services.documental.migration import UP, DOWN
from app.core.config import get_settings
from .document_test_fixtures import TEXT

ROOT = "/api/ecomm-app/workspace/"
ID = "900001"


class DocumentalWorkspace(unittest.TestCase):
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
        self.client = operator()
        self.addCleanup(self.client.close)

    def ok(self, response):
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def get(self, suffix="evidence", ident=ID):
        return self.ok(self.client.get(ROOT + ident + "/" + suffix))

    def post(self, suffix, payload, ident=ID):
        return self.client.post(ROOT + ident + "/" + suffix, json=payload)

    def incorporate(self, raw=TEXT.encode(), **extra):
        data = self.get()
        payload = dict(
            kind="FILE",
            expected_version=data["version"],
            filename="documento-prueba.txt",
            content_type="text/plain",
            content_base64=base64.b64encode(raw).decode(),
            authorized_local_processing=True,
            declared_official=False,
            provenance_note="Documento inventado para probar el flujo; no es evidencia comercial real.",
            **extra,
        )
        result = self.ok(self.post("documents/import", payload))
        return result, next(
            d
            for d in result["documents"]
            if d["id"] == result["incorporated_document_id"]
        )

    def extracted(self, raw=TEXT.encode()):
        data, doc = self.incorporate(raw)
        data = self.ok(
            self.post(
                "documents/" + doc["id"] + "/provenance",
                dict(
                    expected_document_version=doc["version"],
                    decision="REVIEWED",
                    reason="Revisión explícita de procedencia del documento sintético.",
                ),
            )
        )
        doc = next(d for d in data["documents"] if d["id"] == doc["id"])
        data = self.ok(
            self.post(
                "evidence/extract",
                dict(
                    expected_version=data["version"],
                    document_id=doc["id"],
                    document_version=doc["version"],
                ),
            )
        )
        return data, doc

    def decide(self, data, fact, decision="APPROVED"):
        return self.ok(
            self.post(
                "evidence/facts/" + fact["id"] + "/review",
                dict(
                    expected_version=data["version"],
                    expected_fact_version=fact["version"],
                    decision=decision,
                    reason="Comparé el fragmento y la presentación de prueba de forma explícita.",
                ),
            )
        )

    def approved(self):
        data, doc = self.extracted()
        for key in [f["id"] for f in data["facts"]]:
            fact = next(f for f in data["facts"] if f["id"] == key)
            self.assertEqual(fact["blockers"], [])
            data = self.decide(data, fact)
        return data, doc

    def proposal(self):
        self.approved()
        return self.ok(self.post("proposals/generate", {"expected_version": 0}))

    def review(self, proposal, key="title", value=None):
        return self.post(
            f"proposals/{proposal['draft_id']}/review",
            dict(
                expected_revision=proposal["revision"],
                decisions={
                    key: dict(
                        decision="ACCEPTED",
                        value=value
                        if value is not None
                        else proposal["fields"][key]["value"],
                    )
                },
            ),
        )

    def test_empty_exact_dossier_does_not_inherit_fixture_or_pilot_approvals(self):
        data = self.get()
        self.assertEqual(data["documents"], [])
        self.assertEqual(data["facts"], [])
        self.assertIsNone(data["identity"]["ean"])
        self.assertIsNone(data["identity"]["brand"])
        self.assertEqual(
            self.post("proposals/generate", {"expected_version": 0}).status_code, 409
        )

    def test_original_persistence_sha_citations_and_document_history(self):
        data, doc = self.extracted()
        original = self.get(f"documents/{doc['id']}/original/1")
        self.assertEqual(base64.b64decode(original["content_base64"]), TEXT.encode())
        self.assertEqual(
            original["original"]["sha256"], hashlib.sha256(TEXT.encode()).hexdigest()
        )
        self.assertTrue(doc["history"])
        self.assertTrue(
            all(
                f["location"] and f["quote"] and f["state"] == "PENDING"
                for f in data["facts"]
            )
        )
        self.assertEqual(self.get()["facts"], data["facts"])

    def test_no_cross_variant_documents_even_shared_sku_and_other_presentation(self):
        data, doc = self.extracted()
        other = self.get(ident="900002")
        self.assertEqual(other["documents"], [])
        response = self.post(
            "evidence/extract",
            dict(
                expected_version=other["version"],
                document_id=doc["id"],
                document_version=doc["version"],
            ),
            ident="900002",
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            self.client.get(
                ROOT + "900002" + f"/documents/{doc['id']}/original/1"
            ).status_code,
            409,
        )

    def test_incompatible_presentation_blocks_human_approval(self):
        data, _ = self.extracted(TEXT.replace("250 g", "1 kg").encode())
        fact = data["facts"][0]
        self.assertTrue(fact["blockers"])
        response = self.post(
            "evidence/facts/" + fact["id"] + "/review",
            dict(
                expected_version=data["version"],
                expected_fact_version=fact["version"],
                decision="APPROVED",
                reason="Intento de aprobar una presentación incompatible.",
            ),
        )
        self.assertEqual(response.status_code, 409)

    def test_proposal_uses_only_approved_facts_and_rejects_unbacked_edits(self):
        proposal = self.proposal()
        self.assertIn("title", proposal["fields"])
        self.assertNotIn("media", proposal["fields"])
        self.assertEqual(
            self.review(proposal, value="Cura enfermedades sin evidencia").status_code,
            409,
        )
        reviewed = self.ok(self.review(proposal, value="250 g · Almendras sintéticas"))
        self.assertEqual(reviewed["decisions"]["title"]["decision"], "ACCEPTED")

    def test_provenance_revocation_invalidates_facts_and_proposal(self):
        proposal = self.proposal()
        doc = self.get()["documents"][0]
        self.ok(
            self.post(
                "documents/" + doc["id"] + "/provenance",
                dict(
                    expected_document_version=doc["version"],
                    decision="REVOKED",
                    reason="Revocación explícita de procedencia en pruebas.",
                ),
            )
        )
        self.assertFalse(any(f["verified"] for f in self.get()["facts"]))
        self.assertEqual(self.get("proposals")["state"], "STALE")
        self.assertEqual(self.review(proposal).status_code, 409)

    def test_contradictions_prevent_approval_and_invalidate_existing_facts(self):
        self.approved()
        data, doc = self.extracted(TEXT.replace("600 kcal", "610 kcal").encode())
        energy = [f for f in data["facts"] if f["field"] == "nutrition.energy"]
        self.assertEqual(len(energy), 2)
        self.assertTrue(all(f["blockers"] for f in energy))
        self.assertFalse(any(f["verified"] for f in energy))

    def test_auth_csrf_default_off_invalid_id_and_large_document_fail_closed(self):
        anonymous = TestClient(application, base_url="https://127.0.0.1:8443")
        self.assertEqual(anonymous.get(ROOT + ID + "/evidence").status_code, 401)
        self.assertEqual(
            anonymous.post(
                ROOT + ID + "/proposals/generate", json={"expected_version": 0}
            ).status_code,
            401,
        )
        self.assertEqual(
            self.client.post(
                ROOT + ID + "/proposals/generate",
                json={"expected_version": 0},
                headers={"X-CSRF-Token": "invalid"},
            ).status_code,
            403,
        )
        settings = get_settings()
        settings.kiki_document_workspace_enabled = False
        try:
            self.assertEqual(self.client.get(ROOT + ID + "/evidence").status_code, 403)
        finally:
            settings.kiki_document_workspace_enabled = True
        self.assertEqual(
            self.client.get(ROOT + "None/evidence").status_code, 403
        )  # harness rejects before route
        data = self.get()
        too_big = dict(
            kind="FILE",
            expected_version=data["version"],
            filename="large.pdf",
            content_type="application/pdf",
            content_base64="A" * 699056,
            provenance_note="Archivo demasiado grande debe ser rechazado.",
            authorized_local_processing=True,
        )
        self.assertEqual(self.post("documents/import", too_big).status_code, 422)

    def test_revision_cas_two_operators_one_decision_and_no_lost_update(self):
        data, _ = self.extracted()
        fact = data["facts"][0]
        barrier = Barrier(2)

        def act(decision):
            client = operator()
            try:
                barrier.wait(timeout=10)
                return client.post(
                    ROOT + ID + "/evidence/facts/" + fact["id"] + "/review",
                    json=dict(
                        expected_version=data["version"],
                        expected_fact_version=fact["version"],
                        decision=decision,
                        reason="Decisión concurrente explícita de un operador de pruebas.",
                    ),
                ).status_code
            finally:
                client.close()

        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(act, ["APPROVED", "REJECTED"]))
        self.assertEqual(sorted(results), [200, 409])

    def test_save_selected_fields_via_existing_editor_and_history(self):
        proposal = self.ok(self.review(self.proposal()))
        fields = deepcopy(proposal["base_fields"])
        fields["title"] = proposal["fields"]["title"]["value"]
        response = self.client.post(
            ROOT + ID,
            headers={
                "X-Kiki-Proposal-Id": str(proposal["draft_id"]),
                "X-Kiki-Proposal-Revision": str(proposal["revision"]),
            },
            json=dict(expected_version=0, status="DRAFT", fields=fields),
        )
        saved = self.ok(response)
        self.assertEqual(saved["version"], 1)
        self.assertEqual(saved["fields"]["description"], "")
        self.assertEqual(self.ok(self.client.get(ROOT + ID))["fields"], fields)
        self.assertEqual(self.get("proposals")["state"], "APPLIED")
        self.assertTrue(all(f["verified"] for f in self.get()["facts"]))
        self.assertIn("title", saved["history"][-1]["changes"])
        self.assertEqual(
            self.client.post(
                ROOT + ID,
                headers={
                    "X-Kiki-Proposal-Id": str(proposal["draft_id"]),
                    "X-Kiki-Proposal-Revision": str(proposal["revision"]),
                },
                json=dict(expected_version=0, status="DRAFT", fields=fields),
            ).status_code,
            409,
        )

    def test_editor_change_and_cross_variant_proposal_application_blocked(self):
        proposal = self.ok(self.review(self.proposal()))
        fields = deepcopy(proposal["base_fields"])
        fields["title"] = proposal["fields"]["title"]["value"]
        headers = {
            "X-Kiki-Proposal-Id": str(proposal["draft_id"]),
            "X-Kiki-Proposal-Revision": str(proposal["revision"]),
        }
        self.assertEqual(
            self.client.post(
                ROOT + "900002",
                headers=headers,
                json=dict(expected_version=0, status="DRAFT", fields=fields),
            ).status_code,
            409,
        )
        self.ok(
            self.client.post(
                ROOT + ID,
                json=dict(
                    expected_version=0,
                    status="DRAFT",
                    fields={
                        **proposal["base_fields"],
                        "note": "Otro operador guardó un cambio de prueba.",
                    },
                ),
            )
        )
        self.assertEqual(
            self.client.post(
                ROOT + ID,
                headers=headers,
                json=dict(expected_version=0, status="DRAFT", fields=fields),
            ).status_code,
            409,
        )

    def test_proposal_review_concurrency_one_winner(self):
        proposal = self.proposal()
        barrier = Barrier(2)

        def act(decision):
            client = operator()
            try:
                barrier.wait(timeout=10)
                return client.post(
                    ROOT + ID + f"/proposals/{proposal['draft_id']}/review",
                    json=dict(
                        expected_revision=proposal["revision"],
                        decisions={
                            "title": dict(
                                decision=decision,
                                value=proposal["fields"]["title"]["value"],
                            )
                        },
                    ),
                ).status_code
            finally:
                client.close()

        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(act, ["ACCEPTED", "REJECTED"]))
        self.assertEqual(sorted(results), [200, 409])

    def test_replacing_document_invalidates_approvals_and_preserves_originals(self):
        data, doc = self.approved()
        data, revised = self.incorporate(
            TEXT.replace("600 kcal", "610 kcal").encode(),
            document_id=doc["id"],
            expected_document_version=doc["version"],
        )
        self.assertEqual(revised["version"], doc["version"] + 1)
        self.assertTrue(all(f["state"] == "STALE" for f in data["facts"]))
        old = self.get(f"documents/{doc['id']}/original/1")
        new = self.get(f"documents/{doc['id']}/original/{revised['version']}")
        self.assertNotEqual(old["original"]["sha256"], new["original"]["sha256"])
        self.assertEqual(base64.b64decode(old["content_base64"]), TEXT.encode())

    def test_documental_drafts_do_not_replace_historical_ai_results(self):
        proposal = self.proposal()
        from app.services.ecomm_ai_editor_service import EcommAiEditor

        with SessionLocal() as db:
            historical = EcommAiEditor(db).latest(ID)
            self.assertFalse(historical["available"])
            record = db.get(KikiAiEditorialDraft, proposal["draft_id"])
            self.assertEqual(record.product_key, "ECOMM_DOCUMENTAL:" + ID)
        self.assertEqual(self.get("proposals")["draft_id"], proposal["draft_id"])

    def test_migration_down_up_only_disposable_and_no_sandbox_imports_in_common(self):
        with engine.begin() as connection:
            for statement in DOWN + UP:
                connection.execute(text(statement))
        self.assertEqual(self.get()["facts"], [])
        directory = Path("app/services/documental")
        for p in directory.glob("*.py"):
            self.assertNotIn("integration_sandbox", p.read_text(), str(p))
            self.assertNotIn("hileret_pilot", p.read_text(), str(p))
            self.assertNotIn("commercial_pilot", p.read_text(), str(p))
        from app.core.config import Settings

        self.assertFalse(Settings(_env_file=None).kiki_document_workspace_enabled)


if __name__ == "__main__":
    unittest.main(verbosity=2)
