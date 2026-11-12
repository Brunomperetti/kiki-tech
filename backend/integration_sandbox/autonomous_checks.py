"""2R: actual disposable PostgreSQL and the existing deterministic editorial rules."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import timedelta
from threading import Barrier, Event
from time import perf_counter
from uuid import uuid4
from unittest.mock import patch
import json
import tracemalloc
import unittest
from sqlalchemy import select, func, event, text
from . import editorial_checks as legacy
from .editorial_checks import ROOT, ACTOR
from .editorial_fixtures import catalogue
from app.database.session import SessionLocal, engine
from app.database.models import (
    EcommApiProductEdit,
    KikiAiEditorialDraft,
    CatalogSnapshot,
)
from app.services.editorial_batches.service import Batches, now
from app.services.editorial_batches.executor import Executor, SourceCache
from app.services.editorial_batches.storage import Batch, Item
from app.services.editorial_batches.context import Context, sources
from app.services.ecomm_api_product_workspace_service import (
    EcommApiProductWorkspace,
    blank_fields,
)
from app.core.config import get_settings


class Autonomous(unittest.TestCase):
    setUpClass = classmethod(legacy.Editorial.setUpClass.__func__)
    tearDownClass = classmethod(legacy.Editorial.tearDownClass.__func__)
    ok = legacy.Editorial.ok
    preview = legacy.Editorial.preview
    start = legacy.Editorial.start
    detail = legacy.Editorial.detail
    seed = legacy.Editorial.seed

    def setUp(self):
        legacy.Editorial.setUp(self)
        self.mode = patch.object(
            get_settings(), "kiki_editorial_executor_enabled", True
        )
        self.mode.start()
        self.addCleanup(self.mode.stop)
        self.executor = Executor(SessionLocal)

    def drain(self, b, preview=False):
        for _ in range(2000):
            current = self.detail(b)
            if (preview and current["state"] != "PREPARING") or (
                not preview
                and current["state"] not in {"PREPARING", "PENDING", "RUNNING"}
            ):
                return current
            self.executor.tick()
        self.fail("Ejecutor no terminó el trabajo acotado.")

    def ready(self, ids=None, operation="GENERATE_PROPOSALS"):
        return self.drain(self.preview(ids, operation), preview=True)

    def test_unconfirmed_previews_never_execute_and_browser_cannot_step(self):
        self.seed()
        b = self.ready()
        self.assertEqual(b["state"], "PREVIEW")
        for _ in range(3):
            self.executor.tick()
        with SessionLocal() as db:
            self.assertIsNone(db.scalar(select(KikiAiEditorialDraft)))
        self.assertEqual(
            self.client.post(ROOT + "/" + b["id"] + "/step", json={}).status_code, 409
        )

    def test_workflow_partial_status_exact_ids_and_no_commercial_writes(self):
        self.seed()
        b = self.ready(["900001", "900002"])
        self.assertEqual(b["summary"]["eligible"], 1)
        self.start(b)
        r = self.drain(b)
        self.assertEqual(r["public_state"], "COMPLETED_WITH_BLOCKS")
        self.assertEqual(r["progress"]["processed"], 2)
        self.assertEqual(r["progress"]["completed"], 1)
        self.assertEqual(r["progress"]["blocked"], 1)
        with SessionLocal() as db:
            self.assertIsNone(db.scalar(select(EcommApiProductEdit)))
            self.assertEqual(
                db.scalar(select(func.count()).select_from(KikiAiEditorialDraft)), 1
            )
        self.assertEqual(r["items"][0]["ecomm_id"], "900001")
        self.assertTrue(r["items"][0]["history"])

    def test_all_blocked_status_and_invalid_selection(self):
        b = self.ready()
        self.start(b)
        r = self.drain(b)
        self.assertEqual(r["public_state"], "BLOCKED")
        self.assertEqual(
            self.client.post(
                ROOT + "/preview",
                json={
                    "request_key": str(uuid4()),
                    "operation": "REVIEW_TASKS",
                    "selection": {"kind": "IDS", "ids": ["None"]},
                },
            ).status_code,
            409,
        )

    def test_expired_owner_is_recovered_old_owner_cannot_write(self):
        self.seed()
        b = self.ready()
        self.start(b)
        with SessionLocal() as db:
            claim = Batches(db, ACTOR).claim_next()
            ident, token, ids, kind = claim
            row = db.get(Batch, ident)
            row.lease_until = now() - timedelta(seconds=1)
            db.commit()
        second = Executor(SessionLocal)
        second.tick()
        r = self.detail(b)
        self.assertEqual(r["state"], "COMPLETED")
        self.assertEqual(r["items"][0]["attempts"], 2)
        with SessionLocal() as db:
            with self.assertRaises(ValueError):
                Batches(db, ACTOR).process(ident, token, ids)
            db.rollback()
            self.assertEqual(
                db.scalar(select(func.count()).select_from(KikiAiEditorialDraft)), 1
            )

    def test_two_executors_claim_one_action(self):
        self.seed()
        b = self.ready()
        self.start(b)
        barrier = Barrier(2)

        def work(_):
            barrier.wait()
            return Executor(SessionLocal).tick()

        with ThreadPoolExecutor(2) as pool:
            list(pool.map(work, range(2)))
        self.drain(b)
        with SessionLocal() as db:
            self.assertEqual(
                db.scalar(select(func.count()).select_from(KikiAiEditorialDraft)), 1
            )
        self.assertEqual(self.detail(b)["items"][0]["attempts"], 1)

    def test_other_batch_waits_for_incompatible_variant_reservation(self):
        a = self.ready(operation="REVIEW_TASKS")
        b = self.ready(operation="REVIEW_TASKS")
        self.start(a)
        self.start(b)
        with SessionLocal() as db:
            first = Batches(db, ACTOR).claim(a["id"])
        with SessionLocal() as db:
            self.assertIsNone(Batches(db, ACTOR).claim(b["id"]))
        with SessionLocal() as db:
            Batches(db, ACTOR).process(a["id"], *first)
        self.assertEqual(self.drain(b)["state"], "COMPLETED")

    def test_cancellation_commits_while_worker_holds_chunk_lock(self):
        self.seed()
        b = self.ready(["900001", "900002"])
        self.start(b)
        with SessionLocal() as db:
            claim = Batches(db, ACTOR).claim(b["id"])
        entered, release = Event(), Event()
        original = Context.inspect

        def slow(context, *args):
            result = original(context, *args)
            entered.set()
            self.assertTrue(release.wait(5))
            return result

        def process():
            with SessionLocal() as db:
                with patch.object(Context, "inspect", slow):
                    return Batches(db, ACTOR).process(b["id"], *claim)

        with ThreadPoolExecutor(1) as pool:
            future = pool.submit(process)
            self.assertTrue(entered.wait(5))
            try:
                start = perf_counter()
                result = self.ok(
                    self.client.post(
                        ROOT + "/" + b["id"] + "/cancel",
                        json={"expected_revision": b["revision"]},
                    )
                )
                self.assertLess(perf_counter() - start, 2)
                self.assertTrue(result["cancel_requested"])
            finally:
                release.set()
            future.result(timeout=10)
        r = self.detail(b)
        self.assertEqual(r["state"], "CANCELLED")
        self.assertEqual(r["counts"], {"COMPLETED": 1, "CANCELLED": 1})
        with SessionLocal() as db:
            self.assertEqual(
                db.scalar(select(func.count()).select_from(KikiAiEditorialDraft)), 1
            )
            self.assertIsNone(db.scalar(select(EcommApiProductEdit)))

    def test_cancel_during_preview_never_runs(self):
        with SessionLocal() as db:
            catalogue(db, 100)
        b = self.preview([str(900001 + i) for i in range(100)])
        self.ok(
            self.client.post(
                ROOT + "/" + b["id"] + "/cancel",
                json={"expected_revision": b["revision"]},
            )
        )
        self.executor.tick()
        r = self.detail(b)
        self.assertEqual(r["state"], "CANCELLED")
        self.assertEqual(r["counts"], {"CANCELLED": 100})
        self.assertEqual(r["progress"]["processed"], 0)
        self.assertEqual(r["progress"]["prepared"], 0)

    def test_changed_commercial_version_stays_conflict(self):
        self.seed()
        b = self.ready()
        self.start(b)
        with SessionLocal() as db:
            EcommApiProductWorkspace(db).save(
                "900001",
                {**blank_fields(), "title": "Edición de otro operador"},
                "DRAFT",
                0,
            )
        r = self.drain(b)
        self.assertEqual(r["items"][0]["state"], "CONFLICT")
        self.assertEqual(r["public_state"], "BLOCKED")

    def test_preview_and_generation_preserve_exact_document_evidence(self):
        self.seed()
        with SessionLocal() as db:
            context = Context(db, ["900001"], sources(db), 2_000_000)
            original = context.inspect(db, ACTOR, "900001")
            context.release()
            db.rollback()
            projected = Context(db, ["900001"], sources(db), 2_000_000, preview=True)
            new = projected.inspect(db, ACTOR, "900001")
            projected.release()
        self.assertEqual(original, new)

    def test_cache_detects_capture_mutation_and_does_not_merge_packs(self):
        cache = SourceCache()
        with SessionLocal() as db:
            first = cache.load(db, True)
            db.commit()
            record = db.scalar(
                select(CatalogSnapshot).where(
                    CatalogSnapshot.source == "ECOMM_APP_API_STAGE"
                )
            )
            pages = deepcopy(record.payload)
            pages[0]["items"][0]["variants"][0].update(
                is_combo=True,
                description="Pack x6 de 250 g",
                barcode="12345670",
                gtin="12345685",
            )
            record.payload = pages
            db.commit()
            second = cache.load(db, True)
            self.assertIsNot(first, second)
            self.assertTrue(second["900001"]["identity_blockers"])
            self.assertTrue(second["900001"]["is_combo"])
        b = self.ready(["900001", "900002"])
        self.start(b)
        r = self.drain(b)
        self.assertEqual(r["progress"]["blocked"], 2)

    def test_preview_failures_are_bounded_and_recorded(self):
        b = self.preview()
        for index in range(3):
            with patch.object(
                Batches,
                "preview_step",
                side_effect=RuntimeError("injected offline failure"),
            ):
                self.executor.tick()
            if index < 2:
                self.assertEqual(self.detail(b)["state"], "PREPARING")
        r = self.detail(b)
        self.assertEqual(r["public_state"], "FAILED")
        self.assertFalse(r["authorized_by"])
        self.assertEqual(r["counts"], {"ERROR": 1})

    def test_claim_cannot_use_items_from_another_batch(self):
        a = self.ready(operation="REVIEW_TASKS")
        b = self.ready(operation="REVIEW_TASKS")
        self.start(a)
        with SessionLocal() as db:
            claim = Batches(db, ACTOR).claim(a["id"])
            wrong = db.scalar(select(Item).where(Item.batch_id == b["id"]))
            with self.assertRaises(ValueError):
                Batches(db, ACTOR).process(a["id"], claim[0], [wrong.id])
            db.rollback()

    def test_new_migration_reverses_without_losing_editor_or_2q_jobs(self):
        from app.services.editorial_batches.migration_2r import UP, DOWN

        b = self.ready(operation="REVIEW_TASKS")
        with SessionLocal() as db:
            for sql in DOWN:
                db.execute(text(sql))
            for sql in UP:
                db.execute(text(sql))
            db.commit()
            self.assertIsNotNone(db.get(Batch, b["id"]))

    def test_5000_equivalent_before_after_http_and_total_work(self):
        with SessionLocal() as db:
            catalogue(db, 5000)
        ids = [str(900001 + i) for i in range(5000)]

        def body():
            return {
                "request_key": str(uuid4()),
                "operation": "REVIEW_TASKS",
                "selection": {"kind": "IDS", "ids": ids, "query": "", "filter": "all"},
            }

        def measure(fn):
            calls = []

            def sql(*_):
                calls.append(1)

            event.listen(engine, "before_cursor_execute", sql)
            tracemalloc.start()
            start = perf_counter()
            try:
                value = fn()
                elapsed = perf_counter() - start
                _, peak = tracemalloc.get_traced_memory()
            finally:
                tracemalloc.stop()
                event.remove(engine, "before_cursor_execute", sql)
            return value, {
                "seconds": round(elapsed, 3),
                "queries": len(calls),
                "python_peak_mib": round(peak / 1024**2, 2),
            }

        with (
            SessionLocal() as db,
            patch.object(get_settings(), "kiki_editorial_executor_enabled", False),
        ):
            before, old = measure(lambda: Batches(db, ACTOR).preview(body()))
            old_summary = before["summary"]
            old_fingerprints = list(
                db.execute(
                    select(Item.ecomm_id, Item.expected)
                    .where(Item.batch_id == before["id"])
                    .order_by(Item.position)
                ).tuples()
            )
            db.rollback()
        with SessionLocal() as db:
            after, http = measure(lambda: Batches(db, ACTOR).preview(body()))

        def finish_analysis():
            for _ in range(100):
                self.executor.tick()
                with SessionLocal() as db:
                    row = db.get(Batch, after["id"])
                    if row.state == "PREVIEW":
                        return Batches(db, ACTOR).detail(row.id)
            self.fail("El análisis incremental no terminó.")

        result, work = measure(finish_analysis)
        self.assertEqual(result["summary"], old_summary)
        self.assertEqual(result["preview_hash"], before["preview_hash"])
        with SessionLocal() as db:
            self.assertEqual(
                list(
                    db.execute(
                        select(Item.ecomm_id, Item.expected)
                        .where(Item.batch_id == after["id"])
                        .order_by(Item.position)
                    ).tuples()
                ),
                old_fingerprints,
            )
        print(
            "EDITORIAL_2R_EQUIVALENT_PERFORMANCE",
            json.dumps(
                {
                    "variants": 5000,
                    "selection": "same explicit IDs, same capture, no complete documents",
                    "baseline_2q_sync": old,
                    "new_http_enqueue": http,
                    "new_background_analysis": work,
                    "summaries_hash_and_all_identity_versions_equal": True,
                }
            ),
            flush=True,
        )
        self.assertLess(http["seconds"], old["seconds"])
        self.assertLess(http["python_peak_mib"], old["python_peak_mib"])
        self.assertLess(work["queries"], old["queries"])
        self.assertEqual(result["total"], 5000)


if __name__ == "__main__":
    unittest.main(verbosity=2)
