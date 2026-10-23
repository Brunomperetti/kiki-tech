"""Conservative Ecomm–Tiendanube brand leads, no automatic identity claims."""
from copy import deepcopy

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database.models import Base, CatalogSnapshot
from app.integrations.ecomm_app.catalog_stage import STAGE_SOURCE
from app.integrations.ecomm_app.tn_brand_evidence import (
    EcommTnBrandEvidenceService,
    brand_evidence_report,
)


def fixture():
    variants = [
        (1, "ABC1", True),
        (2, "AMBIGUOUS", False),
        (3, "TNDUP", False),
        (4, "NEW-SKU", True),
        (5, "NOBRAND", False),
        (6, "HASBRAND", False),
        (8, "NOT-IN-TN", False),
    ]
    pages = [{
        "page": 1, "total": len(variants), "per_page": 50,
        "total_pages": 1, "captured_at": "2026-10-23T14:00:00+00:00",
        "items": [
            {
                "code": f"{sku}_m", "description": f"Parent {sku}",
                "is_combo": combo,
                "variants": [{
                    "id": id_, "sku": sku, "is_combo": combo,
                    "total_stock": 1, "warehouses": [{"id": 2210, "stock": 1}],
                }],
            } for id_, sku, combo in variants
        ],
    }]
    old = [
        {"ecomm_id": str(i), "name": f"Product {i}", "sku": sku, "brand": brand}
        for i, sku, brand in [
            (1, "abc1", None),
            (2, "AMBIGUOUS", ""),
            (3, "TNDUP", None),
            (4, "OLD-SKU", None),
            (5, "NOBRAND", None),
            (6, "HASBRAND", "Known"),
            (7, "AMBIGUOUS", "Another"),  # collision even without API ID 7
            (8, "NOT-IN-TN", None),
        ]
    ]
    tn = [
        {"slug":"a","sku":"ABC1","brand":"Sundance","name":"Sundance Product"},
        {"slug":"b","sku":"AMBIGUOUS","brand":"Brand","name":"Same SKU different Ecomm owners"},
        {"slug":"c","sku":"TNDUP","brand":"X","name":"Duplicate TN row"},
        {"slug":"c","sku":"TNDUP","brand":"X","name":"Duplicate TN variant"},
        {"slug":"d","sku":"OLD-SKU","brand":"Brand","name":"Outdated SKU in API"},
        {"slug":"e","sku":"NOBRAND","brand":"","name":"No brand here"},
        {"slug":"f","sku":"HASBRAND","brand":"Known","name":"Already complete in Ecomm"},
    ]
    return pages, old, tn


def test_exact_unique_match_is_a_review_lead_and_ambiguous_cases_fail_closed():
    pages, old, tn = fixture()
    before = deepcopy((pages, old, tn))
    result = brand_evidence_report(pages, old, tn)
    assert result["mode"] == "REVIEW_ONLY_TN_BRAND_EVIDENCE"
    assert result["activation_allowed"] is False
    s = result["summary"]
    assert s["missing_brand_unique_id"] == 6
    assert s["candidate_unique_exact_sku"] == 1
    assert s["combo_candidate"] == 1
    assert s["ambiguous_ecomm_sku"] == 1
    assert s["ambiguous_tn_sku"] == 1
    assert s["api_sku_changed"] == 1
    assert s["tn_brand_empty"] == 1
    assert s["no_exact_tn_sku"] == 1
    row = result["candidates"][0]
    assert row["ecomm_id"] == "1"
    assert row["brand_from_tn"] == "Sundance"
    assert row["review_status"] == "NEEDS_HUMAN_VERIFICATION"
    assert row["ecomm_sku"] == "abc1" and row["api_sku"] == "ABC1"
    assert row["is_combo"] is True
    assert (pages, old, tn) == before


def test_no_tn_snapshot_returns_no_candidates_not_fabricated_brands():
    pages, old, _ = fixture()
    result = brand_evidence_report(pages, old, [])
    assert result["available"] is False
    assert result["candidates"] == []
    assert result["activation_allowed"] is False


def test_same_sku_but_different_case_is_allowed_only_with_unique_ids():
    pages, old, tn = fixture()
    tn[0]["sku"] = "abc1"
    assert len(brand_evidence_report(pages, old, tn)["candidates"]) == 1
    # Whitespace *inside* SKU is meaningful, so no implicit normalization.
    tn[0]["sku"] = "AB C1"
    assert len(brand_evidence_report(pages, old, tn)["candidates"]) == 0


def test_placeholder_tn_brand_is_not_valid_evidence():
    pages, old, tn = fixture()
    tn[0]["brand"] = "Sin marca"
    result = brand_evidence_report(pages, old, tn)
    assert result["summary"]["candidate_unique_exact_sku"] == 0
    assert result["summary"]["tn_brand_empty"] == 2


def test_repeated_stable_id_blocks_evidence():
    pages, old, tn = fixture()
    old.append({**old[0], "name":"Different product"})
    result = brand_evidence_report(pages, old, tn)
    assert result["summary"]["candidate_unique_exact_sku"] == 0


def test_partial_copy_is_rejected():
    pages, old, tn = fixture()
    pages[0]["total_pages"] = 2
    with pytest.raises(ValueError, match="completa"):
        brand_evidence_report(pages, old, tn)


def test_sqlalchemy_snapshot_rows_are_never_mutated_by_report():
    pages, old, tn = fixture()
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(CatalogSnapshot(source=STAGE_SOURCE, payload=pages))
        db.add(CatalogSnapshot(source="ECOMM_APP", payload=old))
        db.add(CatalogSnapshot(source="TIENDANUBE", payload=tn))
        db.add(CatalogSnapshot(source="ECOMM_APP_RAW", payload=[{"original": True}]))
        db.commit()
        report = EcommTnBrandEvidenceService(db).report()
        assert report["summary"]["candidate_unique_exact_sku"] == 1
        assert db.scalar(select(CatalogSnapshot).where(CatalogSnapshot.source == STAGE_SOURCE)).payload == pages
        assert db.scalar(select(CatalogSnapshot).where(CatalogSnapshot.source == "ECOMM_APP")).payload == old
        assert db.scalar(select(CatalogSnapshot).where(CatalogSnapshot.source == "TIENDANUBE")).payload == tn
        assert db.scalar(select(CatalogSnapshot).where(CatalogSnapshot.source == "ECOMM_APP_RAW")).payload == [{"original": True}]
    engine.dispose()
