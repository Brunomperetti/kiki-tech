"""Local parser, actual disposable PostgreSQL, existing auth/editor/proposals."""

import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from threading import Barrier
import unittest
from .bootstrap import create_sandbox_app

application = create_sandbox_app()

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import delete, event  # noqa: E402
from app.database.session import SessionLocal, engine  # noqa: E402
from app.database.models import EcommApiProductEdit, KikiAiEditorialDraft  # noqa: E402
from .research.storage import Dossier, Document, initialize  # noqa: E402
from .document_test_fixtures import TEXT, pdf  # noqa: E402
from .document_worker import child_guard  # noqa: E402


def operator():
    client = TestClient(application, base_url="https://127.0.0.1:8443")
    response = client.post(
        "/api/auth/login",
        json={"username": "operador-prueba", "password": "solo-datos-sinteticos"},
    )
    assert response.status_code == 200
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    return client


class LocalDocumentPostgreSQL(unittest.TestCase):
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

    def get(self, ident="900001"):
        return self.ok(self.client.get("/api/test-research/" + ident))

    def payload(
        self, raw=None, name="tecnica.pdf", mime="application/pdf", **overrides
    ):
        return {
            "kind": "FILE",
            "expected_version": self.get()["version"],
            "filename": name,
            "content_type": mime,
            "content_base64": base64.b64encode(pdf() if raw is None else raw).decode(),
            "authorized_local_processing": True,
            "declared_official": True,
            "provenance_note": "Documento sintético redactado para pruebas automatizadas; no proviene de un fabricante real.",
            **overrides,
        }

    def import_doc(self, **args):
        data = self.ok(
            self.client.post(
                "/api/test-documents/900001/import", json=self.payload(**args)
            )
        )
        key = data["incorporated_document_id"]
        return data, next(d for d in data["documents"] if d["id"] == key)

    def provenance(self, doc, decision="REVIEWED"):
        return self.ok(
            self.client.post(
                f"/api/test-documents/900001/{doc['id']}/provenance",
                json={
                    "expected_document_version": doc["version"],
                    "decision": decision,
                    "reason": "Contrasté manualmente la procedencia del documento sintético.",
                },
            )
        )

    def extract(self, data, doc):
        return self.ok(
            self.client.post(
                "/api/test-research/900001/extract",
                json={
                    "expected_version": data["version"],
                    "document_id": doc["id"],
                    "document_version": doc["version"],
                },
            )
        )

    def approve_all(self, data, doc_id):
        for fact in [f for f in data["facts"] if f["document_id"] == doc_id]:
            data = self.ok(
                self.client.post(
                    f"/api/test-research/900001/facts/{fact['id']}/review",
                    json={
                        "expected_version": data["version"],
                        "expected_fact_version": next(
                            f["version"] for f in data["facts"] if f["id"] == fact["id"]
                        ),
                        "decision": "APPROVED",
                        "reason": "Comprobé el dato contra el fragmento documental sintético.",
                    },
                )
            )
        return data

    def full(self):
        data, doc = self.import_doc()
        data = self.provenance(doc)
        doc = next(d for d in data["documents"] if d["id"] == doc["id"])
        return self.approve_all(self.extract(data, doc), doc["id"]), doc

    def test_accessible_compressed_pdf_original_pages_and_real_persistence(self):
        raw = pdf(compressed=True)
        data, doc = self.import_doc(raw=raw)
        self.assertEqual(doc["body"]["parse_status"], "TEXT_EXTRACTED")
        self.assertIn("pagina/1/linea/1", doc["body"]["sections"])
        self.assertEqual(
            doc["body"]["identity_evidence"]["ean"]["location"], "pagina/1/linea/4"
        )
        self.assertIn("12345670", doc["body"]["identity_evidence"]["ean"]["quote"])
        self.assertFalse(data["synthetic_only"])
        self.assertTrue(data["isolated_only"])
        self.assertNotIn("original_base64", doc["body"])
        original = self.ok(
            self.client.get(f"/api/test-documents/900001/{doc['id']}/original/1")
        )
        self.assertEqual(base64.b64decode(original["content_base64"]), raw)
        self.assertEqual(
            original["original"]["sha256"], hashlib.sha256(raw).hexdigest()
        )
        with SessionLocal() as db:
            self.assertEqual(
                db.get(Document, doc["id"]).body["associated_ecomm_id"], "900001"
            )
        self.assertEqual(self.get()["documents"], data["documents"])

    def test_declaration_official_does_not_approve_origin_or_facts(self):
        data, doc = self.import_doc()
        data = self.extract(data, doc)
        self.assertTrue(
            all(f["state"] == "PENDING" and not f["verified"] for f in data["facts"])
        )
        fact = data["facts"][0]
        blocked = self.client.post(
            f"/api/test-research/900001/facts/{fact['id']}/review",
            json={
                "expected_version": data["version"],
                "expected_fact_version": fact["version"],
                "decision": "APPROVED",
                "reason": "Declaración oficial no prueba una fuente auténtica.",
            },
        )
        self.assertEqual(blocked.status_code, 409)
        self.assertTrue(any("Procedencia" in x for x in fact["blockers"]))

    def test_full_approved_evidence_generates_and_saves_with_existing_editor(self):
        data, _doc = self.full()
        self.assertEqual(len([f for f in data["facts"] if f["verified"]]), 15)
        available = self.ok(self.client.get("/api/test-proposals/900001"))
        self.assertFalse(available["available"])
        self.assertFalse(available["synthetic_only"])
        p = self.ok(
            self.client.post(
                "/api/test-proposals/900001/generate", json={"expected_version": 0}
            )
        )
        self.assertFalse(p["synthetic_only"])
        self.assertIn("Conservación:", p["fields"]["description"]["value"])
        decisions = {
            key: {"decision": "ACCEPTED", "value": p["fields"][key]["value"]}
            for key in ("title", "description")
        }
        p = self.ok(
            self.client.post(
                f"/api/test-proposals/900001/{p['draft_id']}/review",
                json={"expected_revision": p["revision"], "decisions": decisions},
            )
        )
        fields = {**p["base_fields"], **{k: v["value"] for k, v in decisions.items()}}
        saved = self.ok(
            self.client.post(
                "/api/ecomm-app/workspace/900001",
                headers={
                    "X-Kiki-Proposal-Id": str(p["draft_id"]),
                    "X-Kiki-Proposal-Revision": str(p["revision"]),
                },
                json={"expected_version": 0, "status": "DRAFT", "fields": fields},
            )
        )
        self.assertEqual(saved["version"], 1)
        self.assertEqual(
            saved["fields"],
            self.ok(self.client.get("/api/ecomm-app/workspace/900001"))["fields"],
        )

    def test_missing_text_pdf_requires_processing_never_fake_success(self):
        data, doc = self.import_doc(raw=pdf(empty=True, scanned=True))
        self.assertEqual(doc["body"]["parse_status"], "NEEDS_OCR")
        self.assertEqual(doc["body"]["sections"], {})
        self.assertEqual(
            self.client.post(
                "/api/test-research/900001/extract",
                json={
                    "expected_version": data["version"],
                    "document_id": doc["id"],
                    "document_version": 1,
                },
            ).status_code,
            409,
        )

    def test_insufficient_document_leaves_identity_empty_and_no_invention(self):
        _data, doc = self.import_doc(
            raw=b"DOCUMENTO SINTETICO. Sin datos de producto.",
            name="insuficiente.txt",
            mime="text/plain",
        )
        self.assertEqual(doc["body"]["parse_status"], "INSUFFICIENT_DATA")
        self.assertIsNone(doc["body"]["identity"]["name"])
        self.assertTrue(any("ausente" in i for i in doc["issues"]))

    def test_ean_presentation_and_pack_discrepancies_block_approval(self):
        for changed in (
            TEXT.replace("12345670", "12345685"),
            TEXT.replace("250 g", "1 kg"),
            TEXT.replace("Unidad", "Pack"),
            TEXT.replace("Contenido neto: 250 g", "Contenido neto: 1000 g"),
            TEXT.replace("Contenido neto: 250 g", "Contenido neto: 250 unidades"),
        ):
            data, doc = self.import_doc(
                raw=changed.encode(), name="contraste.txt", mime="text/plain"
            )
            data = self.provenance(doc)
            doc = next(d for d in data["documents"] if d["id"] == doc["id"])
            data = self.extract(data, doc)
            self.assertTrue(
                all(
                    f["blockers"]
                    for f in data["facts"]
                    if f["document_id"] == doc["id"]
                )
            )
        self.assertEqual(
            self.client.get(
                f"/api/test-documents/900002/{doc['id']}/original/2"
            ).status_code,
            409,
        )
        foreign = self.client.post(
            "/api/test-research/900002/extract",
            json={
                "expected_version": self.get("900002")["version"],
                "document_id": doc["id"],
                "document_version": 2,
            },
        )
        self.assertEqual(foreign.status_code, 409)

    def test_missing_nutritional_units_and_conflicting_formulation(self):
        data, doc = self.import_doc(
            raw=TEXT.replace("600 kcal/100 g", "600").encode(),
            name="sin-unidad.txt",
            mime="text/plain",
        )
        data = self.provenance(doc)
        doc = next(d for d in data["documents"] if d["id"] == doc["id"])
        data = self.extract(data, doc)
        self.assertTrue(
            any(
                "unidad" in issue
                for f in data["facts"]
                if f["field"] == "nutrition.energy"
                for issue in f["blockers"]
            )
        )
        # Explicit conflicting manufacturer statements, no invented interpretation.
        data, prose = self.import_doc(
            raw=TEXT.replace("600 kcal/100 g", "600. Unidad no especificada").encode(),
            name="texto-sin-unidad.txt",
            mime="text/plain",
        )
        data = self.provenance(prose)
        prose = next(d for d in data["documents"] if d["id"] == prose["id"])
        data = self.extract(data, prose)
        energy = next(
            f
            for f in data["facts"]
            if f["document_id"] == prose["id"] and f["field"] == "nutrition.energy"
        )
        self.assertIsNone(energy["unit"])
        self.assertTrue(energy["blockers"])
        data, other = self.import_doc(
            raw=TEXT.replace("F-PRUEBA-A", "F-PRUEBA-B").encode(),
            name="otra-formula.txt",
            mime="text/plain",
        )
        data = self.provenance(other)
        other = next(d for d in data["documents"] if d["id"] == other["id"])
        data = self.extract(data, other)
        self.assertTrue(
            any(
                "contradictorio" in issue
                for f in data["facts"]
                if f["field"] == "formulation"
                for issue in f["blockers"]
            )
        )

    def test_url_is_only_a_reference_no_fetch_no_fact_no_authentication(self):
        data, doc = self.import_doc(
            raw=b"",
            name="",
            mime="",
            kind="URL",
            reference_url="https://api.mercadolibre.com/fabricante/no-consultar",
        )
        self.assertEqual(doc["body"]["parse_status"], "REFERENCE_ONLY")
        self.assertEqual(doc["body"]["source"]["review_state"], "PENDING")
        self.assertFalse(data["facts"])

    def test_missing_origin_and_missing_authorization_rejected(self):
        for extra in ({"authorized_local_processing": False}, {"provenance_note": ""}):
            self.assertEqual(
                self.client.post(
                    "/api/test-documents/900001/import", json=self.payload(**extra)
                ).status_code,
                422,
            )
        response = self.client.post(
            "/api/test-documents/900001/import",
            json=self.payload(provenance_note=" " * 15),
        )
        self.assertEqual(response.status_code, 409)

    def test_pdf_active_encrypted_oversized_complex_and_path_security(self):
        cases = [
            (pdf(active=True), "activo.pdf", "application/pdf"),
            (pdf(encrypted=True), "cifrado.pdf", "application/pdf"),
            (pdf(), "mime.pdf", "text/plain"),
            (
                b'{"dato":{"anidado":{"excesivo":"no permitido"}}}',
                "estructura.json",
                "application/json",
            ),
            (pdf(pages=11), "largo.pdf", "application/pdf"),
            (b"no-es-pdf", "falso.pdf", "application/pdf"),
            (b"x" * 524289, "grande.txt", "text/plain"),
            (b"texto", "../ruta.txt", "text/plain"),
            (b"texto", "C:\\ruta.txt", "text/plain"),
            (b"<img src='https://production.invalid/a'>", "imagen.html", "text/html"),
            (b"<script>alert(1)</script>", "activo.html", "text/html"),
            (
                pdf(text="x" * 2_000_000, compressed=True),
                "bomba.pdf",
                "application/pdf",
            ),
        ]
        for raw, name, mime in cases:
            response = self.client.post(
                "/api/test-documents/900001/import",
                json=self.payload(raw=raw, name=name, mime=mime),
            )
            self.assertIn(response.status_code, (409, 422), name)
        self.assertFalse(
            any(d["body"].get("associated_ecomm_id") for d in self.get()["documents"])
        )
        # Rejection does not poison the parser parent or the API.
        self.import_doc()

    def test_structured_json_and_passive_html_reuse_locations(self):
        for raw, name, mime in [
            (
                json.dumps(
                    {
                        "Nombre": "Almendras sintéticas",
                        "Energía": {"valor": "600", "unidad": "kcal/100 g"},
                    },
                    ensure_ascii=False,
                ).encode(),
                "datos.json",
                "application/json",
            ),
            (
                "<html><body><p>Ingredientes: Almendras</p></body></html>".encode(),
                "etiqueta.html",
                "text/html",
            ),
        ]:
            _data, doc = self.import_doc(raw=raw, name=name, mime=mime)
            self.assertEqual(doc["body"]["parse_status"], "TEXT_EXTRACTED")
            self.assertTrue(
                all(k.startswith(("json/", "html/")) for k in doc["body"]["sections"])
            )

    def test_document_replacement_preserves_original_and_invalidates_decisions_and_proposal(
        self,
    ):
        data, doc = self.full()
        p = self.ok(
            self.client.post(
                "/api/test-proposals/900001/generate", json={"expected_version": 0}
            )
        )
        changed = self.payload(
            raw=pdf(TEXT.replace("600 kcal/100 g", "620 kcal/100 g")),
            document_id=doc["id"],
            expected_document_version=2,
        )
        data = self.ok(
            self.client.post("/api/test-documents/900001/import", json=changed)
        )
        self.assertTrue(all(f["state"] == "STALE" for f in data["facts"]))
        self.assertFalse(
            self.ok(self.client.get("/api/test-proposals/900001"))["source_current"]
        )
        original = self.ok(
            self.client.get(f"/api/test-documents/900001/{doc['id']}/original/1")
        )
        self.assertEqual(base64.b64decode(original["content_base64"]), pdf())
        self.assertEqual(p["ecomm_id"], "900001")

    def test_revoked_origin_invalidates_facts_not_automatic_reverification(self):
        _data, doc = self.full()
        data = self.provenance(doc, "REVOKED")
        self.assertTrue(all(f["state"] == "STALE" for f in data["facts"]))
        self.assertTrue(all(not f["verified"] for f in data["facts"]))

    def test_concurrent_replacement_same_document_base_one_wins_postgres(self):
        _data, doc = self.import_doc()
        body = self.payload(
            document_id=doc["id"], expected_document_version=doc["version"]
        )
        clients = [operator(), operator()]
        barrier = Barrier(2)

        def synchronize(_conn, _cursor, statement, _params, _context, _many):
            if "kiki_research_test.control" in statement and "FOR UPDATE" in statement:
                barrier.wait(timeout=20)

        event.listen(engine, "before_cursor_execute", synchronize)
        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                responses = list(
                    executor.map(
                        lambda c: c.post(
                            "/api/test-documents/900001/import", json=body
                        ),
                        clients,
                    )
                )
        finally:
            event.remove(engine, "before_cursor_execute", synchronize)
            for c in clients:
                c.close()
        self.assertEqual(sorted(r.status_code for r in responses), [200, 409])
        with SessionLocal() as db:
            self.assertEqual(db.get(Document, doc["id"]).version, 2)

    def test_authentication_csrf_and_worker_network_process_guards(self):
        body = self.payload()
        anonymous = TestClient(application, base_url="https://127.0.0.1:8443")
        try:
            self.assertEqual(
                anonymous.post(
                    "/api/test-documents/900001/import", json=body
                ).status_code,
                401,
            )
        finally:
            anonymous.close()
        self.client.headers.pop("X-CSRF-Token")
        self.assertEqual(
            self.client.post(
                "/api/test-documents/900001/import", json=body
            ).status_code,
            403,
        )
        for operation in (
            "socket.connect",
            "socket.getaddrinfo",
            "os.system",
            "os.fork",
            "subprocess.Popen",
        ):
            with self.assertRaises(ValueError):
                child_guard(operation, ())


if __name__ == "__main__":
    unittest.main(verbosity=2)
