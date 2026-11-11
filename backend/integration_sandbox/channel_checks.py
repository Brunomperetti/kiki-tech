"""Actual disposable PostgreSQL, captured provider DTOs and existing decisions."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from threading import Barrier
from time import perf_counter
import unittest
from .editor_checks import application, operator
from fastapi.testclient import TestClient
from sqlalchemy import select, delete, event
from app.database.session import SessionLocal, engine
from app.database.models import (
    CatalogSnapshot,
    EcommApiProductEdit,
    InventoryLinkageDecision,
    TiendanubeMatchDecision,
)
from app.services.ecomm_api_work_queue_service import build_queue
from app.core.config import get_settings
from .channel_fixtures import install

ROOT = "/api/ecomm-app/workspace/"
CHECKS = ["name", "brand", "presentation", "quantity", "sale_type", "codes"]


class Channels(unittest.TestCase):
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
        cls.lifecycle.__exit__(None, None, None)

    def reset(self):
        with SessionLocal() as db:
            for model in (
                EcommApiProductEdit,
                InventoryLinkageDecision,
                TiendanubeMatchDecision,
            ):
                db.execute(delete(model))
            db.execute(
                delete(CatalogSnapshot).where(
                    CatalogSnapshot.source != "ECOMM_APP_API_STAGE"
                )
            )
            db.scalar(
                select(CatalogSnapshot).where(
                    CatalogSnapshot.source == "ECOMM_APP_API_STAGE"
                )
            ).payload = deepcopy(self.original)
            db.commit()

    def setUp(self):
        self.reset()
        install(SessionLocal)
        self.client = operator()
        self.addCleanup(self.client.close)

    def tearDown(self):
        self.reset()

    def ok(self, r):
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def report(self, ident="900003"):
        return self.ok(self.client.get(ROOT + ident + "/channels"))

    def payload(self, row, channel="ml", qty=1, **kw):
        return {
            "channel": channel,
            "listing_id": row["id"],
            "expected_fingerprint": row["token"],
            "expected_revision": row["revision"],
            "decision": "APPROVED",
            "checks": CHECKS,
            "quantity_commercial": qty,
            "reason": "Revisé la identidad, marca, presentación y cantidad del ejemplo sintético.",
            **kw,
        }

    def review(self, ident="900003", channel="ml", qty=1):
        row = self.report(ident)[channel]["candidates"][0]
        return self.ok(
            self.client.post(
                ROOT + ident + "/channels/review", json=self.payload(row, channel, qty)
            )
        )

    def date(self, source, hours):
        with SessionLocal() as db:
            db.scalar(
                select(CatalogSnapshot).where(CatalogSnapshot.source == source)
            ).updated_at = datetime.now(timezone.utc) - timedelta(hours=hours)
            db.commit()

    def test_unit_candidate_human_review_confirmed_capture_and_historical_decisions_untouched(
        self,
    ):
        before = self.report()
        self.assertFalse(before["ml"]["confirmed_listing"])
        self.assertEqual(before["ml"]["evidence_state"], "CANDIDATE")
        result = self.review()
        self.assertTrue(result["ml"]["confirmed_listing"])
        self.assertEqual(result["ml"]["evidence_state"], "CONFIRMED_CAPTURE")
        with SessionLocal() as db:
            old = db.scalar(
                select(InventoryLinkageDecision).where(
                    InventoryLinkageDecision.external_id == "MLA900000003"
                )
            )
            self.assertEqual(
                old.source_snapshot, {"source": "ECOMM_APP_XLSX_HISTORICAL"}
            )
            self.assertEqual(old.history, [])
            self.assertEqual(len(db.scalars(select(InventoryLinkageDecision)).all()), 2)

    def test_tn_fresh_csv_can_verify_link_but_never_current_publication(self):
        self.date("TIENDANUBE", 0)
        result = self.review(channel="tn")
        self.assertEqual(result["tn"]["evidence_state"], "VERIFIED_LINK")
        self.assertTrue(result["tn"]["identity_verified"])
        self.assertFalse(result["tn"]["confirmed_listing"])

    def test_stale_tn_csv_and_ml_capture_block_approval_and_confirmation(self):
        self.assertEqual(self.report()["tn"]["evidence_state"], "STALE")
        self.review()
        self.date("MERCADOLIBRE_API", 48)
        report = self.report()
        self.assertEqual(report["ml"]["evidence_state"], "STALE")
        self.assertFalse(report["ml"]["confirmed_listing"])
        self.assertEqual(
            self.client.post(
                ROOT + "900003/channels/review",
                json=self.payload(report["ml"]["candidates"][0]),
            ).status_code,
            409,
        )

    def test_pack2_pack6_related_sku_do_not_merge_and_wrong_quantity_cannot_be_approved(
        self,
    ):
        a, b = self.report("900001"), self.report("900002")
        self.assertEqual(a["sku"], b["sku"])
        self.assertFalse(a["ml"]["confirmed_listing"])
        self.assertFalse(b["ml"]["confirmed_listing"])
        wrong = next(r for r in a["ml"]["candidates"] if r["id"] == "MLA900000002")
        self.assertFalse(wrong["can_review"])
        self.assertEqual(
            self.client.post(
                ROOT + "900001/channels/review", json=self.payload(wrong, qty=6)
            ).status_code,
            409,
        )
        right = next(r for r in a["ml"]["candidates"] if r["id"] == "MLA900000001")
        result = self.ok(
            self.client.post(
                ROOT + "900001/channels/review", json=self.payload(right, qty=2)
            )
        )
        self.assertTrue(result["ml"]["confirmed_listing"])
        self.assertFalse(self.report("900002")["ml"]["confirmed_listing"])

    def test_same_ean_different_variants_and_barcode_gtin_conflict(self):
        self.review()
        other = self.report("900004")
        self.assertEqual(other["identity"]["gtin"], self.report()["identity"]["gtin"])
        self.assertFalse(other["ml"]["confirmed_listing"])
        bad = self.report("900006")
        self.assertEqual(bad["ml"]["evidence_state"], "IDENTITY_CONFLICT")
        self.assertFalse(bad["ml"]["candidates"][0]["can_review"])

    def test_missing_channel_and_missing_match_never_mean_not_published(self):
        empty = self.report("900005")
        self.assertEqual(empty["ml"]["evidence_state"], "INSUFFICIENT_EVIDENCE")
        self.assertFalse(empty["ml"]["confirmed_listing"])
        with SessionLocal() as db:
            db.execute(
                delete(CatalogSnapshot).where(
                    CatalogSnapshot.source == "MERCADOLIBRE_API"
                )
            )
            db.commit()
        result = self.report()
        self.assertEqual(result["ml"]["evidence_state"], "INSUFFICIENT_EVIDENCE")
        self.assertFalse(result["ml"]["snapshot_available"])

    def test_capture_replacement_invalidates_review_even_if_ids_reused(self):
        self.review()
        with SessionLocal() as db:
            snap = db.scalar(
                select(CatalogSnapshot).where(
                    CatalogSnapshot.source == "MERCADOLIBRE_API"
                )
            )
            rows = deepcopy(snap.payload)
            rows[2]["title"] = "Semillas de chía sintéticas 500 g"
            snap.payload = rows
            db.commit()
        result = self.report()
        self.assertFalse(result["ml"]["confirmed_listing"])
        self.assertFalse(result["ml"]["identity_verified"])

    def test_operator_must_explicitly_review_every_dimension_and_quantity(self):
        row = self.report()["ml"]["candidates"][0]
        for patch in [
            {"checks": ["codes"]},
            {"quantity_commercial": 0},
            {"expected_fingerprint": "0" * 64},
        ]:
            response = self.client.post(
                ROOT + "900003/channels/review", json=self.payload(row, **patch)
            )
            self.assertIn(response.status_code, [409, 422])
        self.assertFalse(self.report()["ml"]["confirmed_listing"])

    def test_invalid_combo_type_is_unknown_and_cannot_validate_identity(self):
        with SessionLocal() as db:
            snap = db.scalar(
                select(CatalogSnapshot).where(
                    CatalogSnapshot.source == "ECOMM_APP_API_STAGE"
                )
            )
            pages = deepcopy(snap.payload)
            pages[0]["items"][2]["variants"][0]["is_combo"] = "false"
            snap.payload = pages
            db.commit()
        row = self.report()["ml"]["candidates"][0]
        self.assertFalse(row["can_review"])
        self.assertEqual(
            self.client.post(
                ROOT + "900003/channels/review", json=self.payload(row)
            ).status_code,
            409,
        )

    def test_csrf_auth_feature_default_off_and_external_routes_denied(self):
        anon = TestClient(application, base_url="https://127.0.0.1:8443")
        self.assertEqual(anon.get(ROOT + "900003/channels").status_code, 401)
        row = self.report()["ml"]["candidates"][0]
        self.assertEqual(
            self.client.post(
                ROOT + "900003/channels/review",
                headers={"X-CSRF-Token": "invalid"},
                json=self.payload(row),
            ).status_code,
            403,
        )
        settings = get_settings()
        settings.kiki_channel_workspace_enabled = False
        try:
            self.assertEqual(self.client.get(ROOT + "900003/channels").status_code, 403)
        finally:
            settings.kiki_channel_workspace_enabled = True
        for path in [
            "/api/mercadolibre/sync",
            "/api/ecomm-app/stage/manual/start",
            "/api/tiendanube/publish",
        ]:
            self.assertEqual(self.client.post(path, json={}).status_code, 403)

    def test_concurrent_human_decisions_one_wins_history_preserved(self):
        row = self.report()["ml"]["candidates"][0]
        barrier = Barrier(2)

        def worker(_):
            client = operator()
            try:
                barrier.wait(timeout=10)
                return client.post(
                    ROOT + "900003/channels/review", json=self.payload(row)
                ).status_code
            finally:
                client.close()

        with ThreadPoolExecutor(2) as pool:
            states = list(pool.map(worker, [0, 1]))
        self.assertEqual(sorted(states), [200, 409])
        self.assertEqual(len(self.report()["ml"]["candidates"][0]["history"]), 1)

    def test_revocation_and_wrong_variant_do_not_reuse_approval(self):
        report = self.review()
        row = report["ml"]["candidates"][0]
        self.assertEqual(
            self.client.post(
                ROOT + "900004/channels/review", json=self.payload(row)
            ).status_code,
            409,
        )
        result = self.ok(
            self.client.post(
                ROOT + "900003/channels/review",
                json=self.payload(row, decision="REVOKED"),
            )
        )
        self.assertFalse(result["ml"]["confirmed_listing"])
        self.assertEqual(len(result["ml"]["candidates"][0]["history"]), 2)

    def test_paused_ml_listing_is_not_confirmed_as_active_publication(self):
        with SessionLocal() as db:
            snap = db.scalar(
                select(CatalogSnapshot).where(
                    CatalogSnapshot.source == "MERCADOLIBRE_API"
                )
            )
            rows = deepcopy(snap.payload)
            rows[2]["status"] = "paused"
            snap.payload = rows
            db.commit()
        result = self.review()
        self.assertTrue(result["ml"]["identity_verified"])
        self.assertFalse(result["ml"]["confirmed_listing"])

    def test_indicators_filter_same_api_variants_and_count_unique_variants(self):
        self.review()
        for flag in [
            "ml_confirmed",
            "tn_verified",
            "channel_candidates",
            "channel_conflicts",
            "channel_no_evidence",
            "channel_stale",
        ]:
            response = self.ok(
                self.client.get(
                    ROOT + "queue",
                    params={"filter": flag, "sort": "capture", "limit": 50},
                )
            )
            self.assertEqual(response["total"], response["summary"][flag])
            self.assertTrue(
                all(
                    "candidates" not in item["channel_coverage"]["ml"]
                    for item in response["items"]
                )
            )
            self.assertTrue(all(flag in r["flags"] for r in response["items"]))
        result = self.ok(
            self.client.get(
                ROOT + "queue",
                params={"filter": "ml_confirmed", "q": "900003", "sort": "capture"},
            )
        )
        self.assertEqual(result["items"][0]["ecomm_id"], "900003")

    def test_orthogonal_capture_flags_include_conflicted_variants_and_absent_channels(
        self,
    ):
        queue = self.ok(
            self.client.get(ROOT + "queue", params={"sort": "capture", "limit": 50})
        )
        self.assertEqual(queue["summary"]["channel_stale"], 6)
        conflicted = next(r for r in queue["items"] if r["ecomm_id"] == "900006")
        self.assertIn("channel_conflicts", conflicted["flags"])
        self.assertIn("channel_stale", conflicted["flags"])
        with SessionLocal() as db:
            db.execute(
                delete(CatalogSnapshot).where(CatalogSnapshot.source == "TIENDANUBE")
            )
            db.commit()
        queue = self.ok(
            self.client.get(ROOT + "queue", params={"sort": "capture", "limit": 50})
        )
        self.assertEqual(queue["summary"]["channel_no_evidence"], 6)

    def test_duplicate_listing_ids_and_missing_ml_variation_sku_never_verify(self):
        with SessionLocal() as db:
            snap = db.scalar(
                select(CatalogSnapshot).where(
                    CatalogSnapshot.source == "MERCADOLIBRE_API"
                )
            )
            rows = deepcopy(snap.payload)
            rows.append(deepcopy(rows[2]))
            rows[3]["external_id"] += " #VAR"
            rows[3]["variant_sku"] = None
            snap.payload = rows
            db.commit()
        self.assertFalse(
            any(c["can_review"] for c in self.report()["ml"]["candidates"])
        )
        self.assertEqual(self.report("900004")["ml"]["candidates"], [])

    def test_multiple_listings_count_separately_from_one_variant_and_keep_pending_candidates(
        self,
    ):
        with SessionLocal() as db:
            snap = db.scalar(
                select(CatalogSnapshot).where(
                    CatalogSnapshot.source == "MERCADOLIBRE_API"
                )
            )
            rows = deepcopy(snap.payload)
            extra = deepcopy(rows[2])
            extra["external_id"] = "MLA900000013"
            rows.append(extra)
            snap.payload = rows
            db.commit()
        self.review()
        queue = self.ok(
            self.client.get(ROOT + "queue", params={"sort": "capture", "limit": 50})
        )
        item = next(r for r in queue["items"] if r["ecomm_id"] == "900003")
        self.assertIn("ml_confirmed", item["flags"])
        self.assertIn("channel_candidates", item["flags"])
        second = next(
            r for r in self.report()["ml"]["candidates"] if r["id"] == "MLA900000013"
        )
        self.ok(
            self.client.post(ROOT + "900003/channels/review", json=self.payload(second))
        )
        queue = self.ok(
            self.client.get(ROOT + "queue", params={"sort": "capture", "limit": 50})
        )
        self.assertEqual(queue["summary"]["ml_confirmed"], 1)
        self.assertEqual(
            queue["channel_coverage"]["summary"]["confirmed_ml_listings"], 2
        )

    def test_thousands_of_variants_have_constant_query_count_no_per_row_requests(self):
        results = []
        for size in [50, 5000]:
            with SessionLocal() as db:
                capture = db.scalar(
                    select(CatalogSnapshot).where(
                        CatalogSnapshot.source == "ECOMM_APP_API_STAGE"
                    )
                )
                pages = deepcopy(self.original)
                pages[0].update(total=size, per_page=size)
                pages[0]["items"] = [
                    {
                        "code": f"SYNTH-{n}",
                        "description": f"Almendras sintéticas {n}",
                        "brand": "Marca sintética KIKI",
                        "is_combo": False,
                        "variants": [
                            {
                                "id": 100000 + n,
                                "sku": f"SYNTH-{n}",
                                "description": "250 g",
                                "is_combo": False,
                            }
                        ],
                    }
                    for n in range(size)
                ]
                capture.payload = pages
                db.scalar(
                    select(CatalogSnapshot).where(
                        CatalogSnapshot.source == "MERCADOLIBRE_API"
                    )
                ).payload = [
                    {
                        "external_id": f"MLA{900100000+n}",
                        "sku": f"SYNTH-{n}",
                        "title": f"Almendras sintéticas {n} 250 g",
                        "brand": "Marca sintética KIKI",
                        "status": "active",
                    }
                    for n in range(size)
                ]
                db.commit()
                statements = []

                def count(*args):
                    statements.append(1)

                event.listen(engine, "before_cursor_execute", count)
                try:
                    started = perf_counter()
                    data = build_queue(db, limit=25, sort="capture")
                    elapsed = perf_counter() - started
                finally:
                    event.remove(engine, "before_cursor_execute", count)
                self.assertEqual(len(data["items"]), 25)
                self.assertEqual(data["summary"]["total"], size)
                self.assertLess(elapsed, 12)
                results.append((size, len(statements), round(elapsed, 3)))
        self.assertEqual(results[0][1], results[1][1])
        self.assertLessEqual(results[1][1], 6)
        print("2P performance size/SQL/seconds:", results, flush=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
