"""Real disposable PG: job recovery, CAS, exact identity, performance and no vendors."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from threading import Barrier
from time import perf_counter
from types import SimpleNamespace
from uuid import uuid4
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy import select, delete, event, text
from .editor_checks import application, operator, full_fields
from app.database.session import SessionLocal, engine
from app.database.models import (
    CatalogSnapshot,
    EcommApiProductEdit,
    KikiAiEditorialDraft,
)
from app.services.documental.storage import Dossier, Document
from app.services.editorial_batches.storage import Batch, Item
from app.services.editorial_batches.service import Batches
from app.services.editorial_batches.migration import UP, DOWN
from app.services.ecomm_api_product_workspace_service import (
    EcommApiProductWorkspace,
    blank_fields,
)
from app.services.ecomm_api_work_queue_service import build_queue
from app.core.config import get_settings
from .editorial_fixtures import approved, catalogue

ROOT = "/api/ecomm-app/editorial-batches"
ACTOR = SimpleNamespace(id="OFFLINE-BATCH-TEST")


class Editorial(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lifecycle = TestClient(application, base_url="https://127.0.0.1:8443")
        cls.lifecycle.__enter__()
        with SessionLocal() as db:
            cls.original = deepcopy(
                db.scalar(
                    select(CatalogSnapshot).where(
                        CatalogSnapshot.source == "ECOMM_APP_API_STAGE"
                    )
                ).payload
            )

    @classmethod
    def tearDownClass(cls):
        with SessionLocal() as db:
            db.scalar(
                select(CatalogSnapshot).where(
                    CatalogSnapshot.source == "ECOMM_APP_API_STAGE"
                )
            ).payload = cls.original
            db.commit()
        cls.lifecycle.__exit__(None, None, None)

    def setUp(self):
        with SessionLocal() as db:
            for model in (
                Item,
                Batch,
                KikiAiEditorialDraft,
                EcommApiProductEdit,
                Dossier,
                Document,
            ):
                db.execute(delete(model))
            db.scalar(
                select(CatalogSnapshot).where(
                    CatalogSnapshot.source == "ECOMM_APP_API_STAGE"
                )
            ).payload = deepcopy(self.original)
            db.commit()
        self.client = operator()
        self.addCleanup(self.client.close)

    def ok(self, response):
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def preview(self, ids=None, operation="GENERATE_PROPOSALS", key=None):
        return self.ok(
            self.client.post(
                ROOT + "/preview",
                json={
                    "request_key": key or str(uuid4()),
                    "operation": operation,
                    "selection": {
                        "kind": "IDS",
                        "ids": ids or ["900001"],
                        "query": "",
                        "filter": "all",
                    },
                },
            )
        )

    def start(self, b):
        return self.ok(
            self.client.post(
                ROOT + "/" + b["id"] + "/start",
                json={
                    "confirm": True,
                    "expected_revision": b["revision"],
                    "preview_hash": b["preview_hash"],
                    "idempotency_key": str(uuid4()),
                },
            )
        )

    def step(self, b, resume=False):
        return self.ok(
            self.client.post(
                ROOT + "/" + b["id"] + "/step", json={"resume_interrupted": resume}
            )
        )

    def detail(self, b):
        return self.ok(self.client.get(ROOT + "/" + b["id"]))

    def seed(self):
        with SessionLocal() as db:
            return approved(db)

    def finish(self, b):
        while b["counts"].get("PENDING") or b["counts"].get("RUNNING"):
            b = self.step(b)
        return self.detail(b)

    def test_preview_confirmation_auth_csrf_and_default_off(self):
        self.assertEqual(
            TestClient(application, base_url="https://127.0.0.1:8443")
            .get(ROOT)
            .status_code,
            401,
        )
        csrf = self.client.headers.pop("X-CSRF-Token")
        self.assertEqual(self.client.post(ROOT + "/preview", json={}).status_code, 403)
        self.client.headers["X-CSRF-Token"] = csrf
        b = self.preview()
        self.assertEqual(b["state"], "PREVIEW")
        self.assertEqual(
            self.client.post(ROOT + "/" + b["id"] + "/step", json={}).status_code, 409
        )
        payload = {
            "confirm": False,
            "expected_revision": b["revision"],
            "preview_hash": b["preview_hash"],
            "idempotency_key": str(uuid4()),
        }
        self.assertEqual(
            self.client.post(ROOT + "/" + b["id"] + "/start", json=payload).status_code,
            422,
        )
        with patch.object(get_settings(), "kiki_editorial_batches_enabled", False):
            self.assertEqual(self.client.get(ROOT).status_code, 403)

    def test_preview_and_start_idempotency(self):
        key = str(uuid4())
        b = self.preview(key=key)
        self.assertEqual(self.preview(key=key)["id"], b["id"])
        payload = {
            "confirm": True,
            "expected_revision": b["revision"],
            "preview_hash": b["preview_hash"],
            "idempotency_key": str(uuid4()),
        }
        a = self.ok(self.client.post(ROOT + "/" + b["id"] + "/start", json=payload))
        c = self.ok(self.client.post(ROOT + "/" + b["id"] + "/start", json=payload))
        self.assertEqual(a["revision"], c["revision"])

    def test_approved_evidence_proposal_only_missing_and_atomic_item_history(self):
        self.seed()
        with SessionLocal() as db:
            EcommApiProductWorkspace(db).save(
                "900001",
                {**blank_fields(), "title": "Título preservado del operador"},
                "DRAFT",
                0,
            )
        b = self.preview()
        self.assertEqual(b["summary"]["eligible"], 1)
        self.start(b)
        r = self.finish(b)
        self.assertEqual(r["state"], "COMPLETED")
        draft = r["items"][0]["result"]["proposal_id"]
        p = self.ok(
            self.client.get(
                "/api/ecomm-app/workspace/900001/proposals", params={"draft_id": draft}
            )
        )
        self.assertNotIn("title", p["fields"])
        self.assertEqual(p["state"], "PENDING_REVIEW")
        self.assertTrue(p["evidence"])
        self.assertEqual(p["history"][0]["batch_reference"]["batch_id"], b["id"])
        workspace = self.ok(self.client.get("/api/ecomm-app/workspace/900001"))
        self.assertEqual(workspace["version"], 1)
        self.assertEqual(workspace["fields"]["description"], "")
        self.assertTrue(r["items"][0]["history"])
        self.assertEqual(
            self.client.get(
                "/api/ecomm-app/workspace/900002/proposals", params={"draft_id": draft}
            ).status_code,
            409,
        )

    def test_no_evidence_blocked_not_autoapproved(self):
        b = self.preview()
        self.assertEqual(b["summary"]["eligible"], 0)
        self.start(b)
        self.assertEqual(self.finish(b)["state"], "BLOCKED")
        with SessionLocal() as db:
            self.assertIsNone(db.scalar(select(KikiAiEditorialDraft)))
            self.assertIsNone(db.scalar(select(EcommApiProductEdit)))

    def test_selection_10_50_100_pagination_incremental(self):
        for size in (10, 50, 100):
            with SessionLocal() as db:
                catalogue(db, size)
            b = self.preview([str(900001 + i) for i in range(size)], "REVIEW_TASKS")
            self.assertEqual(b["total"], size)
            self.assertLessEqual(len(b["items"]), 25)
            self.start(b)
            r = self.finish(b)
            self.assertEqual(r["counts"]["COMPLETED"], size)

    def test_filter_selection_exact_count_and_invalid_ids(self):
        with SessionLocal() as db:
            catalogue(db, 100)
        b = self.ok(
            self.client.post(
                ROOT + "/preview",
                json={
                    "request_key": str(uuid4()),
                    "operation": "REVIEW_TASKS",
                    "selection": {
                        "kind": "FILTER",
                        "query": "BATCH-SYNTHETIC-9",
                        "filter": "all",
                    },
                },
            )
        )
        self.assertEqual(b["total"], 11)
        for ids in (["None"], ["900001", "900001"], ["99"], ["null"], [""], ["0"]):
            r = self.client.post(
                ROOT + "/preview",
                json={
                    "request_key": str(uuid4()),
                    "operation": "REVIEW_TASKS",
                    "selection": {"kind": "IDS", "ids": ids},
                },
            )
            self.assertEqual(r.status_code, 409)

    def test_revocation_and_document_changes_block_frozen_preview(self):
        evidence = self.seed()
        b = self.preview()
        self.start(b)
        f = evidence["facts"][0]
        self.ok(
            self.client.post(
                "/api/ecomm-app/workspace/900001/evidence/facts/" + f["id"] + "/review",
                json={
                    "expected_version": evidence["version"],
                    "expected_fact_version": f["version"],
                    "decision": "REVOKED",
                    "reason": "Revocación explícita de test antes del lote.",
                },
            )
        )
        self.assertEqual(self.finish(b)["state"], "CONFLICT")
        queue = self.ok(
            self.client.get(
                "/api/ecomm-app/workspace/queue", params={"filter": "evidence_revoked"}
            )
        )
        self.assertEqual(queue["total"], 1)

    def test_workspace_version_conflict_no_overwrite(self):
        self.seed()
        b = self.preview()
        self.start(b)
        with SessionLocal() as db:
            EcommApiProductWorkspace(db).save(
                "900001",
                {**blank_fields(), "note": "Versión de otro operador"},
                "DRAFT",
                0,
            )
        self.assertEqual(self.finish(b)["state"], "CONFLICT")

    def test_packs_and_shared_ean_do_not_inherit_unit_evidence(self):
        self.seed()
        with SessionLocal() as db:
            record = db.scalar(
                select(CatalogSnapshot).where(
                    CatalogSnapshot.source == "ECOMM_APP_API_STAGE"
                )
            )
            pages = deepcopy(record.payload)
            for i, qty in ((1, 2), (2, 6)):
                pages[0]["items"][i]["is_combo"] = True
                pages[0]["items"][i]["variants"][0].update(
                    description=f"Pack x{qty} de 250 g",
                    is_combo=True,
                    barcode="12345670",
                )
            record.payload = pages
            db.commit()
        b = self.preview(["900001", "900002", "900003"])
        self.assertEqual(b["summary"]["eligible"], 1)
        self.start(b)
        r = self.finish(b)
        self.assertEqual(r["counts"], {"COMPLETED": 1, "BLOCKED": 2})

    def test_barcode_gtin_conflict_blocks_identity(self):
        with SessionLocal() as db:
            r = db.scalar(
                select(CatalogSnapshot).where(
                    CatalogSnapshot.source == "ECOMM_APP_API_STAGE"
                )
            )
            p = deepcopy(r.payload)
            p[0]["items"][0]["variants"][0].update(barcode="12345670", gtin="12345685")
            r.payload = p
            db.commit()
        b = self.preview()
        self.assertEqual(b["summary"]["conflicts"], 1)
        self.start(b)
        self.assertEqual(self.finish(b)["state"], "BLOCKED")

    def test_crash_resume_fences_old_worker_and_never_duplicates(self):
        self.seed()
        b = self.preview()
        self.start(b)
        with SessionLocal() as db:
            old = Batches(db, ACTOR).claim(b["id"])
        self.assertEqual(
            self.client.post(ROOT + "/" + b["id"] + "/step", json={}).status_code, 409
        )
        result = self.step(b, True)
        self.assertEqual(result["state"], "COMPLETED")
        with SessionLocal() as db:
            with self.assertRaises(ValueError):
                Batches(db, ACTOR).process(b["id"], *old)
            db.rollback()
            self.assertEqual(len(db.scalars(select(KikiAiEditorialDraft)).all()), 1)

    def test_failure_rolls_back_generated_drafts_and_explicit_bounded_retry(self):
        self.seed()
        b = self.preview()
        self.start(b)
        original = Batches.process

        def fail(service, *args):
            # Fail after generating but before the actual transaction commit.
            with patch.object(
                service.db, "commit", side_effect=RuntimeError("simulated interruption")
            ):
                return original(service, *args)

        for _ in range(3):
            with SessionLocal() as db:
                with patch.object(Batches, "process", fail):
                    with self.assertRaises(RuntimeError):
                        Batches(db, ACTOR).step(b["id"])
            r = self.detail(b)
            self.assertEqual(r["state"], "ERROR")
            with SessionLocal() as db:
                self.assertIsNone(db.scalar(select(KikiAiEditorialDraft)))
            response = self.client.post(
                ROOT + "/" + b["id"] + "/retry",
                json={"expected_revision": r["revision"]},
            )
            self.assertEqual(response.status_code, 200 if _ < 2 else 409)

    def test_cancel_preserves_completed_results(self):
        self.seed()
        b = self.preview(["900001", "900002"])
        self.start(b)
        with patch.object(get_settings(), "kiki_editorial_step_size", 1):
            self.step(b)
        r = self.detail(b)
        self.ok(
            self.client.post(
                ROOT + "/" + b["id"] + "/cancel",
                json={"expected_revision": r["revision"]},
            )
        )
        r = self.detail(b)
        self.assertEqual(r["counts"], {"COMPLETED": 1, "CANCELLED": 1})
        self.assertEqual(r["state"], "CANCELLED")

    def test_concurrent_workers_exactly_one_proposal(self):
        self.seed()
        b = self.preview()
        self.start(b)
        barrier = Barrier(2)

        def worker():
            with SessionLocal() as db:
                barrier.wait()
                try:
                    return Batches(db, ACTOR).step(b["id"])["state"]
                except Exception:
                    db.rollback()
                    return "BUSY"

        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(lambda _: worker(), range(2)))
        self.assertIn("COMPLETED", results)
        with SessionLocal() as db:
            self.assertEqual(len(db.scalars(select(KikiAiEditorialDraft)).all()), 1)

    def test_monthly_due_soon_tasks_do_not_modify_commercial_values(self):
        with SessionLocal() as db:
            for ident, days in [("900001", 31), ("900002", 25)]:
                EcommApiProductWorkspace(db).save(
                    ident, full_fields(), "READY_FOR_CHANNELS", 0
                )
                e = db.scalar(
                    select(EcommApiProductEdit).where(
                        EcommApiProductEdit.ecomm_id == ident
                    )
                )
                h = deepcopy(e.history)
                h[-1]["at"] = (
                    datetime.now(timezone.utc) - timedelta(days=days)
                ).isoformat()
                e.history = h
                db.commit()
        for name in ("review_due", "review_soon"):
            queue = self.ok(
                self.client.get(
                    "/api/ecomm-app/workspace/queue", params={"filter": name}
                )
            )
            self.assertEqual(queue["total"], 1)
        b = self.preview(["900001", "900002"], "REVIEW_TASKS")
        self.start(b)
        r = self.finish(b)
        self.assertTrue(all(i["result"]["task"]["requires_human"] for i in r["items"]))
        self.assertEqual(
            self.ok(self.client.get("/api/ecomm-app/workspace/900001"))["version"], 1
        )

    def test_query_cost_5000_and_selection_bounded_memory(self):
        import tracemalloc
        import json

        with SessionLocal() as db:
            catalogue(db, 5000)
            calls = []

            def query(*args):
                calls.append(1)

            event.listen(engine, "before_cursor_execute", query)
            try:
                tracemalloc.start()
                start = perf_counter()
                result = build_queue(db, limit=50)
                elapsed = perf_counter() - start
                _, peak = tracemalloc.get_traced_memory()
                tracemalloc.stop()
            finally:
                event.remove(engine, "before_cursor_execute", query)
            metrics = {
                "variants": 5000,
                "queue_seconds": round(elapsed, 3),
                "queries": len(calls),
                "python_peak_mb": round(peak / 1024**2, 2),
                "response_bytes": len(json.dumps(result).encode()),
            }
            print("EDITORIAL_2Q_PERFORMANCE", json.dumps(metrics), flush=True)
            self.assertEqual(result["total"], 5000)
            self.assertEqual(len(result["items"]), 50)
            self.assertLess(len(calls), 15)
            self.assertLess(elapsed, 15)
            self.assertLess(peak, 120 * 1024**2)
            start = perf_counter()
            batch = Batches(db, ACTOR).preview(
                {
                    "request_key": str(uuid4()),
                    "operation": "REVIEW_TASKS",
                    "selection": {
                        "kind": "FILTER",
                        "ids": [],
                        "query": "",
                        "filter": "all",
                    },
                }
            )
            preview_seconds = perf_counter() - start
            started = Batches(db, ACTOR).start(
                batch["id"],
                {
                    "confirm": True,
                    "expected_revision": batch["revision"],
                    "preview_hash": batch["preview_hash"],
                    "idempotency_key": str(uuid4()),
                },
            )
            start = perf_counter()
            Batches(db, ACTOR).step(started["id"])
            step_seconds = perf_counter() - start
            print(
                "EDITORIAL_2Q_BATCH_PERFORMANCE",
                json.dumps(
                    {
                        "preview_variants": batch["total"],
                        "preview_seconds": round(preview_seconds, 3),
                        "step_items": 5,
                        "step_seconds": round(step_seconds, 3),
                    }
                ),
                flush=True,
            )
            self.assertLess(preview_seconds, 20)
            self.assertLess(step_seconds, 5)

    def test_document_provenance_revoked_and_modified_detected(self):
        self.seed()
        with SessionLocal() as db:
            doc = db.scalar(select(Document))
            body = deepcopy(doc.body)
            body["source"]["review_state"] = "REVOKED"
            doc.body = body
            doc.version += 1
            db.commit()
        b = self.preview()
        self.assertEqual(b["summary"]["eligible"], 0)
        self.assertEqual(b["summary"]["documents_changed"], 1)
        self.start(b)
        self.assertEqual(self.finish(b)["state"], "BLOCKED")
        queue = self.ok(
            self.client.get(
                "/api/ecomm-app/workspace/queue", params={"filter": "documents_changed"}
            )
        )
        self.assertEqual(queue["total"], 1)

    def test_reopen_database_pool_recovers_committed_claim(self):
        self.seed()
        b = self.preview()
        self.start(b)
        with SessionLocal() as db:
            Batches(db, ACTOR).claim(b["id"])
        engine.dispose()
        self.assertEqual(self.detail(b)["counts"], {"RUNNING": 1})
        self.assertEqual(self.step(b, True)["state"], "COMPLETED")
        result = self.detail(b)
        self.assertEqual(result["items"][0]["attempts"], 2)
        with SessionLocal() as db:
            self.assertEqual(len(db.scalars(select(KikiAiEditorialDraft)).all()), 1)

    def test_database_projections_preserve_readiness_and_budget(self):
        from app.services.editorial_batches.queue_projection import queue_edits
        from app.services.editorial_batches.context import Context, sources
        from app.services.ecomm_api_product_workspace_service import (
            _readiness,
            review_schedule,
        )

        with SessionLocal() as db:
            EcommApiProductWorkspace(db).save(
                "900001", full_fields(), "READY_FOR_CHANNELS", 0
            )
            original = db.scalar(select(EcommApiProductEdit))
            projected = queue_edits(db)["900001"]
            self.assertEqual(_readiness(projected.fields), _readiness(original.fields))
            self.assertEqual(review_schedule(projected), review_schedule(original))
            with self.assertRaises(ValueError):
                Context(db, ["900001"], sources(db), 100)

    def test_default_off_preserves_queue_without_documental_queries(self):
        calls = []

        def query(connection, cursor, statement, *args):
            calls.append(statement)

        with (
            SessionLocal() as db,
            patch.object(get_settings(), "kiki_editorial_batches_enabled", False),
        ):
            event.listen(engine, "before_cursor_execute", query)
            try:
                result = build_queue(db)
            finally:
                event.remove(engine, "before_cursor_execute", query)
        self.assertEqual(result["total"], 6)
        self.assertFalse(
            any("kiki_evidence_" in q or "kiki_editorial_batch" in q for q in calls)
        )

    def test_zero_budget_no_providers_and_post_only_mutations(self):
        config = get_settings()
        self.assertFalse(config.kiki_ai_enabled)
        self.assertEqual(config.kiki_ai_api_key, "")
        self.assertEqual(config.ecomm_app_api_token, "")
        self.assertEqual(config.ml_client_secret, "")
        self.assertIn(
            self.client.put(ROOT + "/preview", json={}).status_code, (403, 405)
        )
        self.assertIn(self.client.get(ROOT + "/preview").status_code, (403, 422))
        with patch.object(get_settings(), "kiki_document_workspace_enabled", False):
            self.assertEqual(self.client.get(ROOT).status_code, 403)

    def test_additive_migration_round_trip_preserves_editor(self):
        from app.services.editorial_batches.migration_2r import (
            UP as UP_2R,
            DOWN as DOWN_2R,
        )

        with SessionLocal() as db:
            for statement in DOWN_2R:
                db.execute(text(statement))
            for statement in DOWN:
                db.execute(text(statement))
            for statement in UP:
                db.execute(text(statement))
            for statement in UP_2R:
                db.execute(text(statement))
            db.commit()
            self.assertIsNotNone(
                db.execute(
                    text("SELECT count(*) FROM ecomm_api_product_edits")
                ).scalar()
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
