"""Real test PostgreSQL and Unix collector/parser; only authored HTTP fixtures."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import base64
import unittest
from .bootstrap import create_sandbox_app

application = create_sandbox_app()

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import delete, event  # noqa: E402
from app.database.session import SessionLocal, engine  # noqa: E402
from app.database.models import EcommApiProductEdit, KikiAiEditorialDraft  # noqa: E402
from .research.storage import Dossier, Document, initialize  # noqa: E402
from .discovery_http import Response, SimulatedHTTP, SyntheticDNS, destination, retrieve  # noqa: E402
from .document_parser import parse  # noqa: E402


def operator():
    client = TestClient(application, base_url="https://127.0.0.1:8443")
    response = client.post(
        "/api/auth/login",
        json={"username": "operador-prueba", "password": "solo-datos-sinteticos"},
    )
    assert response.status_code == 200
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    return client


class CollectorPolicy(unittest.TestCase):
    def test_allowlist_dns_redirect_pinning_and_readonly_trace(self):
        first = "https://fabricante-prueba.invalid/a"
        final = "https://documentos-prueba.invalid/b"
        transport = SimulatedHTTP(
            {
                first: Response(302, location=final),
                final: Response(200, b"fixture", "text/plain"),
            }
        )
        raw, trace = retrieve(first, transport, SyntheticDNS())
        self.assertEqual(raw, b"fixture")
        self.assertEqual(len(trace["hops"]), 2)
        self.assertTrue(trace["simulated"])
        self.assertFalse(trace["network_enabled"])
        self.assertEqual({r["method"] for r in transport.requests}, {"GET"})

    def test_forbidden_domains_protocols_credentials_paths_and_private_dns(self):
        for url in [
            "https://api.mercadolibre.com/a",
            "http://fabricante-prueba.invalid/a",
            "file:///etc/passwd",
            "https://fabricante-prueba.invalid.evil.invalid/a",
            "https://user:secret@fabricante-prueba.invalid/a",
            "https://127.0.0.1/a",
            "https://fabricante-prueba.invalid:8443/a",
            "https://fabricante-prueba.invalid/%2f/a",
        ]:
            with self.assertRaises(ValueError):
                destination(url, SyntheticDNS())
        for addresses in [
            ["127.0.0.1"],
            ["10.0.0.1"],
            ["169.254.169.254"],
            ["::1"],
            ["::ffff:127.0.0.1"],
            ["93.184.215.14", "192.168.1.1"],
            ["100.64.0.1"],
        ]:
            with self.assertRaises(ValueError):
                destination(
                    "https://fabricante-prueba.invalid/a",
                    SyntheticDNS({"fabricante-prueba.invalid": addresses}),
                )

    def test_redirect_escape_loop_and_final_address_mismatch_fail_closed(self):
        url = "https://fabricante-prueba.invalid/a"
        for response in [
            Response(302, location="https://evil.invalid/a"),
            Response(302, location="http://fabricante-prueba.invalid/b"),
            Response(302, location=url),
            Response(200, b"fixture", remote_ip="127.0.0.1"),
        ]:
            with self.assertRaises(ValueError):
                retrieve(url, SimulatedHTTP({url: response}), SyntheticDNS())
        responses = {
            url: Response(302, location="/b"),
            "https://fabricante-prueba.invalid/b": Response(302, location="/c"),
            "https://fabricante-prueba.invalid/c": Response(302, location="/d"),
        }
        transport = SimulatedHTTP(responses)
        with self.assertRaises(ValueError):
            retrieve(url, transport, SyntheticDNS())
        self.assertEqual(len(transport.requests), 3)

    def test_size_time_mime_compression_and_access_restrictions(self):
        url = "https://fabricante-prueba.invalid/a"
        for response in [
            Response(200, b"x" * 524289),
            Response(200, b"x", elapsed_ms=5001),
            Response(200, b"x", content_type="application/javascript"),
            Response(200, b"x", content_encoding="gzip"),
            Response(200, b"x", declared_length=100),
            Response(403),
            Response(429),
        ]:
            with self.assertRaises(ValueError):
                retrieve(url, SimulatedHTTP({url: response}), SyntheticDNS())
        with self.assertRaises(ValueError):
            retrieve(url, object(), SyntheticDNS())

    def test_nutritional_table_rows_and_invalid_units_keep_exact_locations(self):
        html = b"<html><body><table><tr><td>Hidratos de carbono</td><td>30 g/100 g</td></tr><tr><td>Sodio</td><td>10 mg/100 g</td></tr></table></body></html>"
        result = parse("tabla.html", "text/html", base64.b64encode(html).decode())
        self.assertEqual(
            {f["field"] for f in result["claims"]},
            {"nutrition.carbohydrates", "nutrition.sodium"},
        )
        self.assertTrue(
            all(
                f["location"].startswith("html/")
                and f["quote"] in result["sections"][f["location"]]
                for f in result["claims"]
            )
        )
        result = parse(
            "tabla.txt",
            "text/plain",
            base64.b64encode(
                b"Energia: 500. Unidad no especificada\nSodio: 10 kcal"
            ).decode(),
        )
        self.assertTrue(all(f["unit"] is None for f in result["claims"]))


class AssistedPostgreSQL(unittest.TestCase):
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

    def get(self, ident="900004"):
        return self.ok(self.client.get("/api/test-research/" + ident))

    def workspace(self, ident="900004"):
        return self.ok(self.client.get("/api/ecomm-app/workspace/" + ident))

    def start(self, ident="900004"):
        return self.ok(
            self.client.post(
                f"/api/test-discovery/{ident}/start",
                json={
                    "expected_version": self.get(ident)["version"],
                    "expected_workspace_version": self.workspace(ident)["version"],
                },
            )
        )

    def choose(self, data, suffix="tecnica", decision="SELECTED"):
        candidate = next(
            c
            for c in data["assisted"]["candidates"]
            if c["source_id"] == "harina-1000-" + suffix
        )
        response = self.client.post(
            f"/api/test-discovery/900004/candidates/{candidate['id']}/decision",
            json={
                "expected_version": data["version"],
                "run_id": data["assisted"]["run_id"],
                "expected_candidate_version": candidate["version"],
                "decision": decision,
                "reason": "Revisión explícita de una fuente sintética para comprobar el recorrido.",
            },
        )
        return self.ok(response), candidate["id"]

    def acquire(self, data, cid):
        candidate = next(c for c in data["assisted"]["candidates"] if c["id"] == cid)
        return self.ok(
            self.client.post(
                f"/api/test-discovery/900004/candidates/{cid}/acquire",
                json={
                    "expected_version": data["version"],
                    "run_id": data["assisted"]["run_id"],
                    "expected_candidate_version": candidate["version"],
                },
            )
        )

    def source(self, data, key):
        doc = next(d for d in data["documents"] if d["id"] == key)
        return self.ok(
            self.client.post(
                f"/api/test-documents/900004/{key}/provenance",
                json={
                    "expected_document_version": doc["version"],
                    "decision": "REVIEWED",
                    "reason": "Procedencia revisada manualmente sobre un fixture, sin autenticar un fabricante real.",
                },
            )
        )

    def extract(self, data, key):
        doc = next(d for d in data["documents"] if d["id"] == key)
        return self.ok(
            self.client.post(
                "/api/test-research/900004/extract",
                json={
                    "expected_version": data["version"],
                    "document_id": key,
                    "document_version": doc["version"],
                },
            )
        )

    def review(self, data, key, field, decision="APPROVED"):
        fact = next(
            f for f in data["facts"] if f["document_id"] == key and f["field"] == field
        )
        return self.client.post(
            f"/api/test-research/900004/facts/{fact['id']}/review",
            json={
                "expected_version": data["version"],
                "expected_fact_version": fact["version"],
                "decision": decision,
                "reason": "Contrasté el dato contra la referencia documental sintética de prueba.",
            },
        )

    def document(self, suffix="tecnica"):
        data, cid = self.choose(self.start(), suffix)
        data = self.acquire(data, cid)
        key = data["incorporated_document_id"]
        return self.extract(self.source(data, key), key), key

    def test_query_uses_actual_available_data_no_fixture_default_or_sku_identity(self):
        data = self.start()
        run = data["assisted"]
        self.assertEqual(run["ecomm_id"], "900004")
        self.assertIsNone(run["query_context"]["query"]["ean"])
        self.assertIsNone(run["query_context"]["query"]["brand"])
        self.assertIsNone(run["query_context"]["query"]["manufacturer"])
        self.assertNotIn("sku", run["query_context"]["query"])
        self.assertTrue(run["simulated_only"])
        self.assertFalse(run["network_enabled"])
        self.assertEqual(run["candidates"][0]["kind"], "Sitio del fabricante")
        self.assertTrue(
            all(
                c["provenance_state"] == "SIMULATED_UNCHECKED"
                for c in run["candidates"]
            )
        )
        self.assertFalse(
            next(c for c in run["candidates"] if c["source_id"].endswith("-pista"))[
                "declared_official"
            ]
        )

    def test_wrong_ean_pack_and_other_manufacturer_remain_discrepancies(self):
        record = self.workspace("900001")
        fields = {
            **record["fields"],
            "proposed_gtin": "12345687",
            "manufacturer": "Fabricante de prueba",
        }
        self.ok(
            self.client.post(
                "/api/ecomm-app/workspace/900001",
                json={"expected_version": 0, "status": "DRAFT", "fields": fields},
            )
        )
        data = self.start("900001")
        unit = next(
            c
            for c in data["assisted"]["candidates"]
            if c["source_id"] == "almendras-250-tecnica"
        )
        pack = next(
            c
            for c in data["assisted"]["candidates"]
            if c["source_id"] == "almendras-1000-tecnica"
        )
        self.assertEqual(unit["comparisons"]["ean"]["status"], "MISMATCH")
        self.assertEqual(pack["comparisons"]["ean"]["status"], "MATCH")
        self.assertEqual(pack["comparisons"]["presentation"]["status"], "MISMATCH")
        other = next(
            c
            for c in data["assisted"]["candidates"]
            if c["source_id"] == "almendras-250-otro-fabricante"
        )
        self.assertEqual(other["comparisons"]["manufacturer"]["status"], "MISMATCH")
        self.assertEqual(self.get("900002")["facts"], [])

    def test_transfer_uses_2g_pdf_original_and_separate_provenance_not_automatic_approval(
        self,
    ):
        data, cid = self.choose(self.start())
        before = self.workspace()
        data = self.acquire(data, cid)
        key = data["incorporated_document_id"]
        doc = next(d for d in data["documents"] if d["id"] == key)
        self.assertEqual(doc["body"]["original"]["content_type"], "application/pdf")
        self.assertTrue(doc["body"]["retrieval"]["simulated"])
        self.assertEqual(len(doc["body"]["retrieval"]["hops"]), 2)
        self.assertEqual(doc["body"]["source"]["review_state"], "PENDING")
        data = self.extract(data, key)
        self.assertTrue(
            all(
                not f["verified"] and any("Procedencia" in b for b in f["blockers"])
                for f in data["facts"]
            )
        )
        self.assertEqual(before, self.workspace())
        original = self.ok(
            self.client.get(f"/api/test-documents/900004/{key}/original/1")
        )
        self.assertTrue(
            base64.b64decode(original["content_base64"]).startswith(b"%PDF-")
        )

    def test_full_research_proposal_and_existing_versioned_save(self):
        data, key = self.document()
        for field in (
            "product_name",
            "presentation",
            "ingredients",
            "nutrition.sodium",
        ):
            data = self.ok(self.review(data, key, field))
        self.assertEqual(data["assisted"]["state"], "STALE")
        proposal = self.ok(
            self.client.post(
                "/api/test-proposals/900004/generate", json={"expected_version": 0}
            )
        )
        self.assertIn("Sodio: 10 mg/100 g", proposal["fields"]["description"]["value"])
        decisions = {
            field: {"decision": "ACCEPTED", "value": proposal["fields"][field]["value"]}
            for field in ("title", "description")
        }
        proposal = self.ok(
            self.client.post(
                f"/api/test-proposals/900004/{proposal['draft_id']}/review",
                json={
                    "expected_revision": proposal["revision"],
                    "decisions": decisions,
                },
            )
        )
        fields = {
            **proposal["base_fields"],
            **{k: v["value"] for k, v in decisions.items()},
        }
        saved = self.ok(
            self.client.post(
                "/api/ecomm-app/workspace/900004",
                headers={
                    "X-Kiki-Proposal-Id": str(proposal["draft_id"]),
                    "X-Kiki-Proposal-Revision": str(proposal["revision"]),
                },
                json={"expected_version": 0, "status": "DRAFT", "fields": fields},
            )
        )
        self.assertEqual(saved["version"], 1)
        self.assertEqual(saved["fields"], self.workspace()["fields"])
        self.assertTrue(saved["history"])

    def test_contradictory_document_blocks_and_insufficient_document_has_no_false_extraction(
        self,
    ):
        data, cid = self.choose(self.start())
        data = self.acquire(data, cid)
        first = data["incorporated_document_id"]
        data, cid = self.choose(data, "contradiccion")
        data = self.acquire(data, cid)
        second = data["incorporated_document_id"]
        data = self.extract(self.source(data, first), first)
        data = self.extract(self.source(data, second), second)
        self.assertTrue(
            all(
                any("contradictorio" in b for b in f["blockers"])
                for f in data["facts"]
                if f["field"] == "nutrition.energy"
            )
        )
        data, cid = self.choose(data, "insuficiente")
        data = self.acquire(data, cid)
        key = data["incorporated_document_id"]
        doc = next(d for d in data["documents"] if d["id"] == key)
        self.assertEqual(doc["body"]["parse_status"], "INSUFFICIENT_DATA")
        self.assertTrue(doc["issues"])

    def test_certifications_need_specific_approved_support_and_revocation_invalidates(
        self,
    ):
        data, key = self.document()
        self.assertEqual(self.review(data, key, "certification").status_code, 409)
        data = self.ok(self.review(data, key, "certification_evidence"))
        data = self.ok(self.review(data, key, "certification"))
        self.assertTrue(
            next(f for f in data["facts"] if f["field"] == "certification")["verified"]
        )
        data = self.ok(self.review(data, key, "certification_evidence", "REVOKED"))
        self.assertFalse(
            next(f for f in data["facts"] if f["field"] == "certification")["verified"]
        )

    def test_workspace_change_invalidates_run_and_prevents_old_transfer(self):
        data, cid = self.choose(self.start())
        candidate = next(c for c in data["assisted"]["candidates"] if c["id"] == cid)
        record = self.workspace()
        self.ok(
            self.client.post(
                "/api/ecomm-app/workspace/900004",
                json={
                    "expected_version": record["version"],
                    "status": "DRAFT",
                    "fields": {
                        **record["fields"],
                        "note": "Otra sesión cambió el borrador.",
                    },
                },
            )
        )
        old = self.client.post(
            f"/api/test-discovery/900004/candidates/{cid}/acquire",
            json={
                "expected_version": data["version"],
                "run_id": data["assisted"]["run_id"],
                "expected_candidate_version": candidate["version"],
            },
        )
        self.assertEqual(old.status_code, 409)
        self.assertEqual(self.get()["assisted"]["state"], "STALE")
        self.assertFalse(
            any(d["body"].get("associated_ecomm_id") for d in self.get()["documents"])
        )

    def test_concurrent_candidate_decisions_one_wins_without_overwriting_postgres(self):
        data = self.start()
        candidate = data["assisted"]["candidates"][0]
        payload = {
            "expected_version": data["version"],
            "run_id": data["assisted"]["run_id"],
            "expected_candidate_version": candidate["version"],
            "reason": "Decisión humana concurrente sobre un fixture de fabricante.",
        }
        clients = [operator(), operator()]
        barrier = Barrier(2)

        def synchronize(_c, _cursor, statement, _p, _ctx, _many):
            if "kiki_research_test.control" in statement and "FOR UPDATE" in statement:
                barrier.wait(timeout=20)

        event.listen(engine, "before_cursor_execute", synchronize)
        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                responses = list(
                    executor.map(
                        lambda pair: pair[1].post(
                            f"/api/test-discovery/900004/candidates/{candidate['id']}/decision",
                            json={
                                **payload,
                                "decision": ["SELECTED", "REJECTED"][pair[0]],
                            },
                        ),
                        enumerate(clients),
                    )
                )
        finally:
            event.remove(engine, "before_cursor_execute", synchronize)
            for client in clients:
                client.close()
        self.assertEqual(sorted(r.status_code for r in responses), [200, 409])
        with SessionLocal() as db:
            self.assertTrue(db.get(Dossier, "900004").history)

    def test_authentication_csrf_forbidden_parameters_and_other_variants(self):
        data = self.start()
        candidate = data["assisted"]["candidates"][0]
        anonymous = TestClient(application, base_url="https://127.0.0.1:8443")
        try:
            self.assertEqual(
                anonymous.post(
                    "/api/test-discovery/900004/start",
                    json={"expected_version": 0, "expected_workspace_version": 0},
                ).status_code,
                401,
            )
        finally:
            anonymous.close()
        self.assertEqual(
            self.client.post(
                "/api/test-discovery/900004/start",
                json={
                    "expected_version": 0,
                    "expected_workspace_version": 0,
                    "url": "https://api.mercadolibre.com",
                },
            ).status_code,
            422,
        )
        self.assertEqual(
            self.client.post(
                f"/api/test-discovery/900005/candidates/{candidate['id']}/acquire",
                json={
                    "expected_version": self.get("900005")["version"],
                    "run_id": data["assisted"]["run_id"],
                    "expected_candidate_version": 1,
                },
            ).status_code,
            409,
        )
        self.client.headers.pop("X-CSRF-Token")
        self.assertEqual(
            self.client.post(
                "/api/test-discovery/900004/start",
                json={"expected_version": 0, "expected_workspace_version": 0},
            ).status_code,
            403,
        )
        for path in (
            "/api/test-discovery/real/start",
            "/api/ecomm-app/workspace/ai/900004/suggest",
            "/api/mercadolibre/sync",
        ):
            self.assertEqual(self.client.post(path).status_code, 403)


if __name__ == "__main__":
    unittest.main(verbosity=2)
