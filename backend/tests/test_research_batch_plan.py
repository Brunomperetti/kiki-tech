"""Batch planning covers full Ecomm catalog without network, AI or edits."""
from copy import deepcopy

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import CatalogSnapshot, EcommApiProductEdit
from app.services.research_batch_plan_service import (
    BUCKETS, MAX_BATCH, build_research_batch_plan,
)
from test_ecomm_api_work_queue import db_fixture
from test_research_manifest_service import eligible


def test_batch_plan_classifies_every_variant_and_exposes_only_eligible_gtin(tmp_path):
    engine = db_fixture(tmp_path)
    with Session(engine) as db:
        stage, export = eligible(db)
        source_before = deepcopy(stage.payload)
        export_before = deepcopy(export.payload)
        result = build_research_batch_plan(db, limit=1)
        assert result["source"] == "ECOMM_APP_API_STAGE"
        assert result["total_variants"] == 2
        assert result["classified_variants"] == 2
        assert set(result["buckets"]) == set(BUCKETS)
        assert sum(result["buckets"].values()) == 2
        assert result["eligible_total"] == 1
        assert result["buckets"]["research_candidate"] == 1
        assert result["buckets"]["pack_review"] == 1
        assert result["batch_size"] == 1
        product = result["items"][0]
        assert product["ecomm_id"] == "101"
        assert product["sku"] == "2500"
        assert product["gtin_lookup_hint"] == "7798353193212"
        assert product["presentation_original"] == "30 cápsulas"
        assert product["source_url"] is None
        assert product["manufacturer_verified"] is False
        assert product["facts_approved"] is False
        assert result["manufacturer_urls_discovered"] == 0
        assert result["network_requests"] == result["ai_requests"] == 0
        assert result["can_auto_fetch"] is False
        assert result["external_writes_enabled"] is False
        assert result["next_offset"] is None
        assert build_research_batch_plan(db, limit=1, offset=1)["items"] == []
        assert db.scalar(select(CatalogSnapshot).where(
            CatalogSnapshot.source == "ECOMM_APP_API_STAGE"
        )).payload == source_before
        assert db.scalar(select(CatalogSnapshot).where(
            CatalogSnapshot.source == "ECOMM_APP_GTIN_EXPORT"
        )).payload == export_before
        assert db.scalars(select(EcommApiProductEdit)).all() == []


def test_no_valid_unique_excel_code_yields_manual_research_not_fabrication(tmp_path):
    engine = db_fixture(tmp_path)
    with Session(engine) as db:
        plan = build_research_batch_plan(db)
        assert plan["total_variants"] == 2
        assert plan["eligible_total"] == 0
        assert plan["items"] == []
        assert plan["buckets"]["gtin_lookup_unavailable"] == 1
        assert plan["buckets"]["pack_review"] == 1
        assert sum(plan["buckets"].values()) == 2


def test_duplicate_sku_blocks_eligible_gtin_even_with_export_present(tmp_path):
    engine = db_fixture(tmp_path)
    with Session(engine) as db:
        stage, _ = eligible(db)
        mutated = deepcopy(stage.payload)
        mutated[0]["items"][1]["variants"][0]["sku"] = "2500"
        stage.payload = mutated
        db.commit()
        plan = build_research_batch_plan(db)
        assert plan["eligible_total"] == 0
        assert plan["buckets"]["identity_review"] == 2
        assert plan["items"] == []


@pytest.mark.parametrize("limit,offset", [
    (0, 0), (MAX_BATCH + 1, 0), (2.5, 0),
    (True, 0), (10, -1), (10, 10001), (10, False),
])
def test_invalid_plan_batch_or_offset_is_rejected(limit, offset, tmp_path):
    engine = db_fixture(tmp_path)
    with Session(engine) as db:
        with pytest.raises(ValueError, match="investigación"):
            build_research_batch_plan(db, limit=limit, offset=offset)


def test_missing_capture_does_not_produce_partial_research_cohort(tmp_path):
    engine = db_fixture(tmp_path)
    with Session(engine) as db:
        stage = db.scalar(select(CatalogSnapshot).where(
            CatalogSnapshot.source == "ECOMM_APP_API_STAGE"
        ))
        stage.payload = deepcopy(stage.payload)
        stage.payload[0]["total_pages"] = 2
        db.commit()
        with pytest.raises(ValueError, match="incompleta"):
            build_research_batch_plan(db)
