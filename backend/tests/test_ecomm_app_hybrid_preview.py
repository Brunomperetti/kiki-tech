"""Regression tests: hybrid inventory is a read-only side-by-side inspection."""
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database.models import Base, CatalogSnapshot
from app.integrations.ecomm_app.catalog_hybrid_preview import (
    EcommHybridCatalogService, hybrid_catalog_preview,
)
from app.integrations.ecomm_app.catalog_stage import STAGE_SOURCE


def _pages(*parents):
    return [{
        "page": 1, "total": len(parents), "total_pages": 1, "per_page": 50,
        "captured_at": "2026-10-23T14:00:00+00:00",
        "items": list(parents),
    }]


def _parent(code, identifier, sku, stock, combo=None, *, warehouses=None):
    return {
        "code": code, "description": code, "is_combo": combo,
        "variants": [{
            "id": identifier, "sku": sku, "is_combo": combo,
            "total_stock": stock,
            "warehouses": warehouses if warehouses is not None else [
                {"id": 2210, "stock": stock},
            ],
        }],
    }


def _data():
    pages = _pages(
        _parent("6102100_m", 9183101, "6102100", 8, True, warehouses=[
            {"id": 2210, "stock": 6}, {"id": 17063, "stock": 2},
        ]),
        _parent("5345000_m", 9211791, "5345000", 0, True),
        _parent("Vitaneral", 8859967, "vitaneral chocolate", 27, False),
    )
    legacy = [
        {
            "ecomm_id": "9183101", "name": "Pack x2 Vitamina C Sundance",
            "sku": "VITAMINACSUNDANCE100", "brand": "Sundance",
            "list_price": "5500.00", "cost": "3000.00", "stock": 10,
            "ean": "7791234567899",
        },
        {
            "ecomm_id": "9211791", "name": "Aceto Balsámico Lauri",
            "sku": "6166", "brand": "Lauri", "list_price": 0, "cost": 0, "stock": 0,
            "ean": None,
        },
        {
            "ecomm_id": "8859967", "name": "Vitaneral Chocolate",
            "sku": "VITANERALCHOCOLATE", "price": 44690, "cost": None,
            "stock": 28, "brand": "Natufarma",
        },
        {"ecomm_id": "6963979", "name": "Geonat Omega 3", "sku": "4744", "stock": 0},
    ]
    return pages, legacy


def test_hybrid_preserves_commercial_fields_and_never_conflates_combo_sku():
    pages, legacy = _data()
    before = repr(pages), repr(legacy)
    result = hybrid_catalog_preview(pages, legacy, ["9183101", "9211791"])
    assert result["mode"] == "READ_ONLY_HYBRID_PREVIEW"
    assert result["activation_allowed"] is False
    assert result["stage_capture_finished"] == "2026-10-23T14:00:00+00:00"
    assert result["coverage"] == {
        "matched_unique_ids": 3,
        "legacy_price_present": 3,
        "legacy_cost_present": 2,
        "legacy_brand_present": 3,
        "legacy_gtin_present": 1,
        "api_stock_present": 3,
    }
    first, second = result["rows"]
    assert first["identity"] == "MATCHED_STABLE_ID"
    assert first["sku_relation"] == "SUBSTANTIVE_CHANGE"
    assert first["legacy"]["sku"] == "VITAMINACSUNDANCE100"
    assert first["legacy"]["list_price"] == "5500.00"
    assert first["api"]["sku"] == "6102100"
    assert first["api"]["total_stock"] == 8
    assert first["api"]["warehouses"] == [
        {"id": 2210, "stock": 6}, {"id": 17063, "stock": 2},
    ]
    assert first["api"]["is_combo"] is True
    assert second["legacy"]["list_price"] == 0
    assert second["legacy"]["cost"] == 0
    assert second["api"]["total_stock"] == 0
    assert before == (repr(pages), repr(legacy))


def test_historical_only_and_comparison_does_not_infer_missing_stock_as_zero():
    pages, legacy = _data()
    result = hybrid_catalog_preview(pages, legacy, ["6963979", "12345678"])
    assert result["rows"][0]["identity"] == "HISTORICAL_ONLY"
    assert result["rows"][0]["api"] is None
    assert result["rows"][1]["identity"] == "NOT_FOUND"
    assert result["rows"][1]["legacy"] is None
    assert result["rows"][1]["api"] is None


def test_api_only_has_no_invented_cost_price_or_historical_link():
    pages, legacy = _data()
    result = hybrid_catalog_preview(pages, legacy[:1], ["9211791"])
    row = result["rows"][0]
    assert row["identity"] == "API_ONLY"
    assert row["legacy"] is None
    assert row["api"]["is_combo"] is True


def test_duplicate_ids_never_choose_arbitrary_variant_or_historical_price():
    pages, legacy = _data()
    pages[0]["items"].append(_parent("ANOTHER", 9183101, "DIFFERENT", 1, False))
    pages[0]["total"] = 4
    result = hybrid_catalog_preview(pages, legacy, ["9183101"])
    row = result["rows"][0]
    assert row["identity"] == "AMBIGUOUS_DUPLICATE_ID"
    assert row["legacy"] is None
    assert row["api"] is None


@pytest.mark.parametrize("ids", [[], ["1"]*2, ["ABC"], ["1", "ABC"], ["1"]*6, ["  "], ["-3"]])
def test_invalid_selection_rejected(ids):
    pages, legacy = _data()
    with pytest.raises(ValueError):
        hybrid_catalog_preview(pages, legacy, ids)


def test_incomplete_stage_is_not_used():
    pages, legacy = _data()
    pages[0]["total_pages"] = 2
    with pytest.raises(ValueError, match="incompleta"):
        hybrid_catalog_preview(pages, legacy, ["9183101"])


def test_database_snapshots_are_read_only_after_preview():
    pages, legacy = _data()
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(CatalogSnapshot(source=STAGE_SOURCE, payload=pages))
        db.add(CatalogSnapshot(source="ECOMM_APP", payload=legacy))
        db.add(CatalogSnapshot(source="ECOMM_APP_RAW", payload=[{"original": True}]))
        db.commit()
        report = EcommHybridCatalogService(db).preview(["9183101", "8859967"])
        assert len(report["rows"]) == 2
        assert report["rows"][1]["sku_relation"] == "FORMAT_ONLY"
        assert db.scalar(select(CatalogSnapshot).where(CatalogSnapshot.source="ECOMM_APP")).payload == legacy
        assert db.scalar(select(CatalogSnapshot).where(CatalogSnapshot.source=STAGE_SOURCE)).payload == pages
        assert db.scalar(select(CatalogSnapshot).where(CatalogSnapshot.source="ECOMM_APP_RAW")).payload == [{"original": True}]
    engine.dispose()
