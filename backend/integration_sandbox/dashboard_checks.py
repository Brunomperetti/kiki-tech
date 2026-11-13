"""2N: existing endpoints and services, on preflight-verified disposable PG only."""

from contextlib import contextmanager
from copy import deepcopy
import time
import unittest

from .editor_checks import (
    application,
    operator,
    SessionLocal,
    CatalogSnapshot,
    STAGE_SOURCE,
    blank_fields,
)
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from app.database.models import EcommApiProductEdit


class DashboardPostgreSQL(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lifecycle = TestClient(application, base_url="https://127.0.0.1:8443")
        cls.lifecycle.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.lifecycle.__exit__(None, None, None)

    def setUp(self):
        with SessionLocal() as db:
            db.execute(delete(EcommApiProductEdit))
            db.commit()
        self.client = operator()
        self.addCleanup(self.client.close)

    @contextmanager
    def altered_capture(self, change):
        with SessionLocal() as db:
            row = db.scalar(
                select(CatalogSnapshot).where(CatalogSnapshot.source == STAGE_SOURCE)
            )
            original = deepcopy(row.payload)
            changed = deepcopy(original)
            change(changed)
            row.payload = changed
            db.commit()
        try:
            yield
        finally:
            with SessionLocal() as db:
                row = db.scalar(
                    select(CatalogSnapshot).where(
                        CatalogSnapshot.source == STAGE_SOURCE
                    )
                )
                row.payload = original
                db.commit()

    def queue(self, **params):
        return self.client.get(
            "/api/ecomm-app/workspace/queue", params={"sort": "capture", **params}
        )

    def test_existing_queue_is_authenticated_read_only_and_keeps_source_rows(self):
        with TestClient(application, base_url="https://127.0.0.1:8443") as anonymous:
            self.assertEqual(
                anonymous.get("/api/ecomm-app/workspace/queue").status_code, 401
            )
        value = self.queue(limit=3, page=2).json()
        self.assertEqual(
            [r["ecomm_id"] for r in value["items"]], ["900004", "900005", "900006"]
        )
        self.assertEqual(value["summary"]["total"], 6)
        self.assertEqual(value["summary"]["identity"], 2)
        row = value["items"][0]
        self.assertEqual(row["source"]["ecomm_id"], row["ecomm_id"])
        self.assertEqual(row["source"]["stock_at_capture"], 12)
        self.assertIsNone(row["source"]["barcode"])
        self.assertIsNone(row["source"]["gtin_raw"])
        self.assertFalse(row["channel_coverage"]["ml"]["confirmed_listing"])

    def test_saved_editor_updates_filters_counts_and_brand_search_without_provider_calls(
        self,
    ):
        self.assertEqual(self.queue(filter="draft").json()["total"], 0)
        response = self.client.post(
            "/api/ecomm-app/workspace/900003",
            json={
                "expected_version": 0,
                "status": "DRAFT",
                "fields": {
                    **blank_fields(),
                    "brand": "Marca sintética 2N",
                    "title": "Chía de prueba 2N",
                },
            },
        )
        self.assertEqual(response.status_code, 200)
        value = self.queue(filter="draft", q="Marca sintética 2N").json()
        self.assertEqual(value["total"], 1)
        self.assertEqual(value["summary"]["draft"], 1)
        self.assertEqual(value["summary"]["untouched"], 5)
        self.assertEqual(value["items"][0]["edit_version"], 1)
        self.assertEqual(value["items"][0]["ecomm_id"], "900003")
        self.assertEqual(self.queue(sort="untrusted").status_code, 422)

    def test_barcode_gtin_conflict_is_visible_but_server_also_blocks_saves(self):
        def change(pages):
            pages[0]["items"][2]["variants"][0].update(
                barcode="0000000000000", gtin="1111111111111"
            )

        with self.altered_capture(change):
            catalog = self.client.get("/api/ecomm-app/stage/catalog").json()["items"][2]
            self.assertEqual(catalog["barcode"], "0000000000000")
            self.assertEqual(catalog["gtin_raw"], "1111111111111")
            self.assertIn("BARCODE_GTIN_CONFLICT", catalog["identity_blockers"])
            self.assertEqual(
                self.client.get("/api/ecomm-app/workspace/900003").status_code, 200
            )
            response = self.client.post(
                "/api/ecomm-app/workspace/900003",
                json={
                    "expected_version": 0,
                    "status": "DRAFT",
                    "fields": {**blank_fields(), "note": "No debe persistirse"},
                },
            )
            self.assertEqual(response.status_code, 409)
            self.assertIn(
                "900003",
                [r["ecomm_id"] for r in self.queue(filter="identity").json()["items"]],
            )
            with SessionLocal() as db:
                self.assertIsNone(db.scalar(select(EcommApiProductEdit)))

    def test_invalid_ids_fail_closed_in_both_read_contracts(self):
        for invalid in (None, "", "None", "null", "undefined", True, 0, -1):
            with (
                self.subTest(ident=invalid),
                self.altered_capture(
                    lambda p: p[0]["items"][2]["variants"][0].update(id=invalid)
                ),
            ):
                self.assertEqual(
                    self.client.get("/api/ecomm-app/stage/catalog").status_code, 409
                )
                self.assertEqual(self.queue().status_code, 409)

    def test_unknown_combo_is_not_coerced_in_original_source_and_shared_sku_is_not_merged(
        self,
    ):
        with self.altered_capture(lambda p: p[0]["items"][0].update(is_combo=None)):
            rows = self.queue(q="DEMO-ALM").json()["items"]
            self.assertEqual([x["ecomm_id"] for x in rows], ["900001", "900002"])
            self.assertNotEqual(
                rows[0]["source"]["variant_description"],
                rows[1]["source"]["variant_description"],
            )
            self.assertIsNone(rows[0]["source"]["parent_is_combo"])

    def test_thousands_of_synthetic_variants_have_global_counts_and_bounded_pages(self):
        def change(pages):
            template = deepcopy(pages[0]["items"][0])
            template["description"] = "Catálogo sintético de escala 2N"
            variant = template["variants"][0]
            template["variants"] = [
                {**variant, "id": 910000 + i, "sku": f"SYNTHETIC-2N-{i}"}
                for i in range(5000)
            ]
            pages[0]["items"] = [template]
            pages[0]["total"] = 1

        with self.altered_capture(change):
            started = time.monotonic()
            response = self.queue(limit=25, page=150)
            self.assertEqual(response.status_code, 200)
            value = response.json()
            self.assertEqual(value["summary"]["total"], 5000)
            self.assertEqual(len(value["items"]), 25)
            self.assertEqual(value["items"][0]["ecomm_id"], "913725")
            print(
                f"2N scale: 5000 variants / page=25, elapsed={time.monotonic()-started:.3f}s"
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
