"""Safe Ecomm stage vs historical inventory comparison (read-only)."""
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database.models import Base, CatalogSnapshot
from app.integrations.ecomm_app.catalog_comparison import (
    EcommAppStageComparisonService, compare_stage_to_legacy,
)
from app.integrations.ecomm_app.catalog_stage import STAGE_SOURCE


def _page(products):
    return {
        "version": 1,
        "page": 1,
        "total": len(products),
        "total_pages": 1,
        "per_page": 50,
        "captured_at": "2026-10-23T14:00:00+00:00",
        "items": products,
    }


def _parent(code, *variants, combo=False):
    return {
        "code": code, "description": code, "is_combo": combo,
        "total_stock": sum(item["total_stock"] for item in variants),
        "variants": list(variants),
    }


def _variant(identifier, sku, stock, *, combo=False):
    return {
        "id": identifier, "sku": sku, "total_stock": stock,
        "is_combo": combo, "warehouses": [{"id": 2210, "stock": stock}],
    }


def test_vitaneral_stable_ids_distinguish_pack_and_flavors_without_stock_writes():
    stage = [_page([
        _parent("Vitaneral Vainilla100_m", _variant(9181206, "Vitaneral Vainilla100", 10, combo=True), combo=True),
        _parent("Vitaneral", _variant(8859967, "vitaneral chocolate", 27),
                _variant(8859966, "Vitaneral Vainilla", 22)),
    ])]
    historical = [
        {"ecomm_id": "8859967", "sku": "VITANERALCHOCOLATE", "stock": "28", "name": "Chocolate"},
        {"ecomm_id": "8859966", "sku": "VITANERALVAINILLA", "stock": "32", "name": "Vainilla"},
    ]
    report = compare_stage_to_legacy(stage, historical)
    t = report["totals"]
    assert t["historical_products"] == 2
    assert t["api_products_parent"] == 2
    assert t["api_variants"] == 3
    assert t["matched_stable_ids"] == 2
    assert t["historical_no_stable_id_match"] == 0
    assert t["api_no_stable_id_match"] == 1  # x2 combo, not regular Vainilla
    assert t["same_id_format_sku_changed"] == 2
    assert t["same_id_different_sku"] == 0
    assert t["stock_differences_informational"] == 2
    assert len(report["samples"]["api_without_id_match"]) == 1
    assert report["samples"]["api_without_id_match"][0]["api_id"] == "9181206"
    assert report["samples"]["api_without_id_match"][0]["is_combo"] is True


def test_unique_sku_with_different_ids_is_only_candidate_not_matched_identity():
    stage = [_page([_parent("P", _variant(200, "ABC", 1))])]
    historical = [{"ecomm_id": "100", "sku": "ABC", "stock": 1}]
    report = compare_stage_to_legacy(stage, historical)
    t = report["totals"]
    assert t["matched_stable_ids"] == 0
    assert t["historical_no_stable_id_match"] == 1
    assert t["api_no_stable_id_match"] == 1
    assert t["candidate_sku_only"] == 1
    assert report["samples"]["candidate_by_sku"][0]["basis"] == "SAME_SKU_DIFFERENT_ID"


def test_equal_id_sku_differences_are_classified_without_false_identity_change():
    stage = [_page([_parent("P", _variant(100, "Ab C", 0))])]
    historical = [{"ecomm_id": "100", "sku": "ABC", "stock": "0"}]
    report = compare_stage_to_legacy(stage, historical)
    assert report["totals"]["matched_stable_ids"] == 1
    assert report["totals"]["same_id_format_sku_changed"] == 1
    assert report["totals"]["stock_differences_informational"] == 0


def test_duplicate_id_never_counts_as_stable_match():
    stage = [_page([
        _parent("P1", _variant(100, "SKU-A", 2)),
        _parent("P2", _variant(100, "SKU-B", 1)),
    ])]
    historical = [{"ecomm_id": "100", "sku": "SKU-A", "stock": 2}]
    report = compare_stage_to_legacy(stage, historical)
    assert report["totals"]["matched_stable_ids"] == 0
    assert report["totals"]["duplicate_stage_ids"] == 1
    assert report["totals"]["api_no_stable_id_match"] == 2


def test_incomplete_stage_and_missing_historical_are_rejected():
    with pytest.raises(ValueError, match="incompleta"):
        compare_stage_to_legacy([], [{"ecomm_id": "1", "sku": "X"}])
    with pytest.raises(ValueError, match="histórico"):
        compare_stage_to_legacy([_page([_parent("P", _variant(1, "A", 1))])], [])


def test_report_reads_db_only_and_historical_payload_remains_identical():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    stage = [_page([_parent("P", _variant(1, "A", 2))])]
    historical = [{"ecomm_id": "1", "sku": "A", "stock": 1}]
    with Session(engine) as db:
        db.add(CatalogSnapshot(source="ECOMM_APP", payload=historical))
        db.add(CatalogSnapshot(source=STAGE_SOURCE, payload=stage))
        db.add(CatalogSnapshot(source="ECOMM_APP_RAW", payload=[{"original": True}]))
        db.commit()
        report = EcommAppStageComparisonService(db).report()
        assert report["totals"]["matched_stable_ids"] == 1
        assert report["totals"]["stock_differences_informational"] == 1
        assert db.scalar(select(CatalogSnapshot).where(CatalogSnapshot.source == "ECOMM_APP")).payload == historical
        assert db.scalar(select(CatalogSnapshot).where(CatalogSnapshot.source == STAGE_SOURCE)).payload == stage
        assert db.scalar(select(CatalogSnapshot).where(CatalogSnapshot.source == "ECOMM_APP_RAW")).payload == [{"original": True}]
    engine.dispose()
