"""Commercial views/quality on the existing PostgreSQL harness, never providers."""

from copy import deepcopy
from time import perf_counter
import unittest
from sqlalchemy import select, event
from fastapi.testclient import TestClient
from . import channel_checks as legacy
from .editor_checks import full_fields
from app.database.session import SessionLocal, engine
from app.database.models import CatalogSnapshot
from app.services.ecomm_api_work_queue_service import build_queue
from app.services.ecomm_channel_listings import listings
from app.services.ecomm_catalog_quality import identity_index
from app.services.ecomm_api_product_workspace_service import EcommApiProductWorkspace

ROOT = "/api/ecomm-app/workspace/"


class CatalogueOperations(unittest.TestCase):
    setUpClass = classmethod(legacy.Channels.setUpClass.__func__)
    tearDownClass = classmethod(legacy.Channels.tearDownClass.__func__)
    setUp = legacy.Channels.setUp
    tearDown = legacy.Channels.tearDown
    reset = legacy.Channels.reset
    ok = legacy.Channels.ok
    report = legacy.Channels.report
    payload = legacy.Channels.payload
    review = legacy.Channels.review
    date = legacy.Channels.date

    def queue(self, flag="all", **kw):
        return self.ok(self.client.get(ROOT + "queue", params={"filter": flag, **kw}))

    def channel(self, channel="ml", **kw):
        return self.ok(
            self.client.get(
                ROOT + "channels/listings", params={"channel": channel, **kw}
            )
        )

    def test_quality_counts_include_untouched_and_never_merge_codes(self):
        q = self.queue()
        for flag, count in {
            "ean_missing": 3,
            "ean_repeated": 2,
            "sku_repeated": 2,
            "sku_family": 2,
            "barcode_gtin_conflict": 1,
            "commercial_title_missing": 6,
            "long_description_missing": 6,
            "short_description_missing": 6,
            "images_missing": 6,
            "video_unrecorded": 6,
            "commercial_incomplete": 6,
            "ml_unconfirmed": 6,
            "tn_unconfirmed": 6,
        }.items():
            self.assertEqual(q["summary"][flag], count, flag)
            result = self.queue(flag)
            self.assertEqual(result["total"], count, flag)
        ids = [x["ecomm_id"] for x in self.queue("ean_repeated")["items"]]
        self.assertEqual(set(ids), {"900003", "900004"})

    def test_intersection_search_pagination_and_batch_selection_share_contract(self):
        q = self.queue("ean_repeated+images_missing", q="DEMO", limit=1, page=2)
        self.assertEqual(q["total"], 2)
        self.assertEqual(len(q["items"]), 1)
        with SessionLocal() as db:
            ids = build_queue(
                db, filter_name="ean_repeated+images_missing", selection_ids_only=True
            )["selected_ids"]
        self.assertEqual(set(ids), {"900003", "900004"})
        for value in [
            "ean_missing+ean_missing",
            "ean_missing+unknown",
            "all+ean_missing+images_missing",
        ]:
            self.assertEqual(
                self.client.get(ROOT + "queue", params={"filter": value}).status_code,
                409,
            )

    def test_editor_save_updates_real_missing_fields_without_loading_media(self):
        with SessionLocal() as db:
            EcommApiProductWorkspace(db).save("900003", full_fields(), "DRAFT", 1)
        q = self.queue()
        for flag in [
            "commercial_title_missing",
            "long_description_missing",
            "short_description_missing",
            "category_missing",
            "subcategory_missing",
            "attributes_missing",
            "images_missing",
            "video_unrecorded",
            "seo_missing",
        ]:
            self.assertEqual(q["summary"][flag], 5, flag)
            self.assertNotIn(
                "900003", [x["ecomm_id"] for x in self.queue(flag)["items"]]
            )

    def test_every_channel_row_survives_without_a_master_variant(self):
        with SessionLocal() as db:
            snap = db.scalar(
                select(CatalogSnapshot).where(
                    CatalogSnapshot.source == "MERCADOLIBRE_API"
                )
            )
            rows = deepcopy(snap.payload)
            rows.append(
                {
                    "external_id": "MLA999000001",
                    "title": "Legumbres sintéticas sin vincular",
                    "sku": "SIN-MAESTRO",
                    "status": "active",
                }
            )
            snap.payload = rows
            db.commit()
        r = self.channel(q="SIN-MAESTRO", linkage="unlinked")
        self.assertEqual(r["total_records"], 6)
        self.assertEqual(r["matches"], 1)
        self.assertEqual(r["items"][0]["id"], "MLA999000001")
        self.assertEqual(r["items"][0]["ecomm_ids"], [])
        self.assertFalse(r["items"][0]["confirmed_listing"])
        self.assertEqual(self.queue()["summary"]["total"], 6)

    def test_candidates_legacy_reviews_verified_links_and_stale_capture(self):
        before = self.channel(linkage="verified")
        self.assertEqual(before["matches"], 0)
        self.review()
        r = self.channel(q="MLA900000003", linkage="verified")
        self.assertEqual(r["items"][0]["ecomm_ids"], ["900003"])
        self.assertTrue(r["items"][0]["confirmed_listing"])
        self.date("MERCADOLIBRE_API", 48)
        stale = self.channel(q="MLA900000003")
        self.assertFalse(stale["items"][0]["confirmed_listing"])
        self.assertEqual(stale["items"][0]["evidence_state"], "PENDING_VALIDATION")

    def test_tn_csv_never_confirms_current_publication_and_lists_all_rows(self):
        r = self.channel("tn")
        self.assertEqual(r["total_records"], 4)
        self.assertEqual(r["distinct_publications"], 4)
        self.assertTrue(all(not x["confirmed_listing"] for x in r["items"]))
        self.assertFalse(r["freshness"]["fresh"])
        self.assertTrue(all(x["evidence_state"] != "STALE" for x in r["items"]))
        self.assertEqual(r["items"][0]["ecomm_ids"], [])

    def test_family_comparator_rules_reused_without_numerical_overreach(self):
        def pages(skus):
            return [
                {
                    "items": [
                        {
                            "variants": [
                                {"id": i + 1, "sku": s} for i, s in enumerate(skus)
                            ]
                        }
                    ]
                }
            ]

        self.assertEqual(identity_index(pages(["12000", "12987"]))[2], set())
        self.assertEqual(
            identity_index(pages(["12111", "12987"]))[2], {"12111", "12987"}
        )
        self.assertEqual(
            identity_index(pages(["12341", "12349"]))[2], {"12341", "12349"}
        )

    def test_authentication_and_readonly_boundary(self):
        anonymous = TestClient(legacy.application, base_url="https://127.0.0.1:8443")
        self.addCleanup(anonymous.close)
        self.assertEqual(
            anonymous.get(ROOT + "channels/listings?channel=ml").status_code, 401
        )
        self.assertEqual(
            self.client.post(ROOT + "channels/listings", json={}).status_code, 403
        )
        self.assertEqual(
            self.client.get(ROOT + "channels/listings?channel=other").status_code, 422
        )
        self.assertEqual(
            self.client.post("/api/mercadolibre/sync", json={}).status_code, 403
        )

    def test_monthly_review_reuses_versioned_service_and_preserves_content(self):
        with SessionLocal() as db:
            before = EcommApiProductWorkspace(db).save(
                "900003", full_fields(), "READY_FOR_CHANNELS", 1
            )
        r = self.ok(
            self.client.post(
                ROOT + "900003/confirm-review",
                json={"expected_version": before["version"]},
            )
        )
        self.assertEqual(r["fields"], before["fields"])
        self.assertEqual(r["version"], before["version"] + 1)
        self.assertFalse(r["review_schedule"]["review_due"])
        self.assertEqual(
            self.client.post(
                ROOT + "900003/confirm-review",
                json={"expected_version": before["version"]},
            ).status_code,
            409,
        )

    def test_invalid_master_does_not_invent_external_links(self):
        self.review()
        with SessionLocal() as db:
            snap = db.scalar(
                select(CatalogSnapshot).where(
                    CatalogSnapshot.source == "ECOMM_APP_API_STAGE"
                )
            )
            raw = deepcopy(snap.payload)
            raw[0]["total_pages"] = 2
            snap.payload = raw
            db.commit()
        r = self.channel()
        self.assertEqual(r["total_records"], 5)
        self.assertTrue(
            all(not x["ecomm_ids"] and not x["confirmed_listing"] for x in r["items"])
        )

    def test_malformed_channel_capture_is_not_reported_as_empty(self):
        with SessionLocal() as db:
            snap = db.scalar(
                select(CatalogSnapshot).where(
                    CatalogSnapshot.source == "MERCADOLIBRE_API"
                )
            )
            snap.payload = {"unexpected": "format"}
            db.commit()
        self.assertEqual(
            self.client.get(ROOT + "channels/listings?channel=ml").status_code, 409
        )

    def test_channel_query_cost_constant_with_thousands_of_master_variants(self):
        results = []
        for size in [50, 5000]:
            with SessionLocal() as db:
                record = db.scalar(
                    select(CatalogSnapshot).where(
                        CatalogSnapshot.source == "ECOMM_APP_API_STAGE"
                    )
                )
                original = deepcopy(self.original)
                original[0]["items"] = [
                    {
                        "description": "Producto sintético",
                        "is_combo": False,
                        "variants": [
                            {
                                "id": 900001 + i,
                                "sku": f"SKU-{i}",
                                "description": "250 g",
                                "is_combo": False,
                            }
                        ],
                    }
                    for i in range(size)
                ]
                original[0].update(total=size, per_page=max(size, 50), total_pages=1)
                record.payload = original
                db.commit()
                statements = []

                def count(*_):
                    statements.append(1)

                event.listen(engine, "before_cursor_execute", count)
                began = perf_counter()
                try:
                    r = listings(db, "ml")
                finally:
                    event.remove(engine, "before_cursor_execute", count)
                results.append(
                    (size, len(statements), round(perf_counter() - began, 3))
                )
                self.assertEqual(r["total_records"], 5)
        self.assertEqual(results[0][1], results[1][1])
        self.assertLessEqual(results[1][1], 8)
        print("Commercial channel view size/SQL/seconds:", results, flush=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
