"""Regression: only completed Ecomm-App API is used for barcode work."""

from copy import deepcopy

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import CatalogSnapshot
from app.services.ecomm_api_barcode_service import (
    api_candidates_for_pages, api_summary, api_evidence,
)
from test_ecomm_api_work_queue import db_fixture


def sample_pages():
    return [{
        "items": [{"description": "Producto", "is_combo": False, "variants": [
            {"id": "1", "sku": "A", "barcode": "7793396000039",
             "gtin": None, "variant_description": "454 g", "is_combo": False},
            {"id": "2", "sku": "B", "barcode": None, "gtin": None,
             "variant_description": "60 g", "is_combo": False},
            {"id": "3", "sku": "C", "barcode": "7793396000039",
             "gtin": None, "is_combo": False},
            {"id": "4", "sku": "D", "barcode": "7798353193212",
             "gtin": None, "is_combo": True},
        ]}],
    }]


def test_only_valid_unique_api_codes_are_lookup_hints():
    pages = sample_pages()
    assert api_candidates_for_pages(pages) == {}
    pages[0]["items"][0]["variants"][2]["barcode"] = "8410771100656"
    assert api_candidates_for_pages(pages) == {
        "1": "7793396000039", "3": "8410771100656",
    }


def test_api_candidates_exclude_duplicate_sku_mismatch_and_pack():
    pages = sample_pages()
    rows = pages[0]["items"][0]["variants"]
    rows[2]["barcode"] = "8410771100656"
    rows[2]["sku"] = "A"
    assert api_candidates_for_pages(pages) == {}
    rows[2]["sku"] = "C"
    rows[0]["gtin"] = "8410771100656"
    assert api_candidates_for_pages(pages) == {"3": "8410771100656"}


def test_db_summary_and_evidence_do_not_read_archived_excel(tmp_path):
    engine = db_fixture(tmp_path)
    with Session(engine) as db:
        stage = db.scalar(select(CatalogSnapshot).where(
            CatalogSnapshot.source == "ECOMM_APP_API_STAGE"
        ))
        pages = deepcopy(stage.payload)
        pages[0]["items"][0]["variants"][0]["barcode"] = "7793396000039"
        stage.payload = pages
        old = CatalogSnapshot(source="ECOMM_APP_GTIN_EXPORT", payload=[{
            "version": 1, "variants": 2, "rows": [
                {"ecomm_id": "101", "sku": "wrong", "gtin": "0000000000000"},
            ],
        }])
        db.add(old)
        db.commit()

        summary = api_summary(db)
        assert summary["source"] == "ECOMM_APP_API_STAGE"
        assert summary["barcode_present"] == 1
        assert summary["total_variants"] == 2
        assert summary["external_writes_enabled"] is False
        record = api_evidence(db, "101")
        assert record["barcode"] == "7793396000039"
        assert record["source"] == "ECOMM_APP_API_STAGE"
        assert record["manufacturer_verified"] is False
        assert api_evidence(db, "102")["barcode"] == ""
        # Historical snapshots are retained as archives and remain untouched.
        assert db.scalar(select(CatalogSnapshot).where(
            CatalogSnapshot.source == "ECOMM_APP_GTIN_EXPORT"
        )).payload == old.payload
