"""Read-only live stock checks never confuse parent SKU siblings with variant IDs."""
from copy import deepcopy

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database.models import Base, CatalogSnapshot
from app.integrations.ecomm_app.catalog_stage import STAGE_SOURCE
from app.integrations.ecomm_app.live_stock_check import (
    EcommLiveStockService, verify_current_stock,
)
from app.integrations.ecomm_app.public_api import API_PREFIX, EcommAppApiError


def page():
    return [{
        "page": 1, "total": 2, "total_pages": 1, "per_page": 50,
        "captured_at": "2026-10-23T14:00:00+00:00",
        "items": [
            {"code": "6102100_m", "variants": [
                {"id": 9183101, "sku": "6102100", "is_combo": True,
                 "total_stock": 26, "warehouses": [
                     {"id": 2210, "stock": 21}, {"id": 17063, "stock": 5},
                 ]},
            ]},
            {"code": "5345000_m", "variants": [
                {"id": 9211791, "sku": "5345000", "is_combo": True,
                 "total_stock": 375, "warehouses": [
                     {"id": 2210, "stock": 365}, {"id": 17063, "stock": 10},
                 ]},
            ]},
        ],
    }]


def legacy():
    return [
        {"ecomm_id": "9183101", "sku": "VITAMINACSUNDANCE100", "stock": 40, "cost": 1},
        {"ecomm_id": "9211791", "sku": "6166", "stock": 5, "cost": 1},
        {"ecomm_id": "6963979", "sku": "4744", "stock": 0, "cost": 1},
    ]


class StubVendor:
    def __init__(self, *, response=None):
        self.calls = []
        self.response = response if response is not None else {
            "items": [
                {"code": "6102100_m", "variants": [
                    {"id": 9183101, "sku": "6102100", "total_stock": 27,
                     "warehouses": [
                         {"id": 2210, "stock": 22}, {"id": 17063, "stock": 5},
                     ]},
                    # A sibling from same parent must never be attributed
                    # to the requested SKU/variant.
                    {"id": 444, "sku": "SIBLING", "total_stock": 999},
                ]},
                {"code": "5345000_m", "variants": [
                    {"id": 9211791, "sku": "5345000", "total_stock": 375,
                     "warehouses": [
                         {"id": 2210, "stock": 365}, {"id": 17063, "stock": 10},
                     ]},
                ]},
            ],
        }

    def _call(self, method, path, *, params=None, body=None):
        assert method == "POST"
        assert path == f"{API_PREFIX}/productos/consulta"
        assert params is None
        self.calls.append(body["skus"])
        return self.response


def test_exact_sku_and_id_plus_warehouses_verified_zero_writes():
    stage, historical = page(), legacy()
    before = deepcopy(stage), deepcopy(historical)
    vendor = StubVendor()
    result = verify_current_stock(stage, historical, ["9183101", "9211791"], vendor)
    assert vendor.calls == [["6102100", "5345000"]]
    assert result["activation_allowed"] is False
    assert result["queried_skus"] == 2
    first, second = result["rows"]
    assert first["status"] == "IDENTITY_AND_STOCK_VERIFIED"
    assert first["historical_stock"] == 40
    assert first["captured_stock"] == 26
    assert first["current_stock"] == 27
    assert first["is_combo"] is True
    assert second["status"] == "IDENTITY_AND_STOCK_VERIFIED"
    assert second["current_stock"] == 375
    assert stage == before[0] and historical == before[1]


def test_historical_only_never_requests_derived_sku_from_vendor():
    vendor = StubVendor()
    result = verify_current_stock(page(), legacy(), ["6963979"], vendor)
    assert vendor.calls == []
    assert result["rows"][0]["status"] == "NOT_ELIGIBLE"
    assert result["rows"][0]["current_stock"] is None


def test_exact_sku_with_wrong_id_is_explicit_mismatch_not_stock():
    response = {"items": [
        {"code": "P", "variants": [
            {"id": 9999999, "sku": "6102100", "total_stock": 400,
             "warehouses": [{"id": 2210, "stock": 400}]},
        ]},
    ]}
    result = verify_current_stock(page(), legacy(), ["9183101"], StubVendor(response=response))
    row = result["rows"][0]
    assert row["status"] == "ID_MISMATCH"
    assert row["current_stock"] is None


def test_duplicate_exact_sku_is_ambiguous_even_with_one_matching_id():
    response = {"items": [{"variants": [
        {"id": 9183101, "sku": "6102100", "total_stock": 27},
        {"id": 99999, "sku": "6102100", "total_stock": 1000},
    ]}]}
    row = verify_current_stock(page(), legacy(), ["9183101"], StubVendor(response=response))["rows"][0]
    assert row["status"] == "AMBIGUOUS_SKU"
    assert row["current_stock"] is None


def test_warehouse_mismatch_blocks_stock_validation():
    response = {"items": [{"variants": [
        {"id": 9183101, "sku": "6102100", "total_stock": 70,
         "warehouses": [{"id": 2210, "stock": 50}]},
    ]}]}
    row = verify_current_stock(page(), legacy(), ["9183101"], StubVendor(response=response))["rows"][0]
    assert row["status"] == "WAREHOUSE_TOTAL_CONFLICT"
    assert row["current_stock"] == 70


def test_numeric_zero_is_valid_current_stock_with_zero_deposit():
    response = {"items": [{"variants": [
        {"id": 9183101, "sku": "6102100", "total_stock": 0,
         "warehouses": [{"id": 2210, "stock": 0}]},
    ]}]}
    row = verify_current_stock(page(), legacy(), ["9183101"], StubVendor(response=response))["rows"][0]
    assert row["status"] == "IDENTITY_AND_STOCK_VERIFIED"
    assert row["current_stock"] == 0


@pytest.mark.parametrize("variants,status", [
    ([], "SKU_NOT_FOUND"),
    ([{"id": 9183101, "sku": "6102100", "total_stock": None}], "STOCK_NOT_REPORTED"),
    ([{"id": 9183101, "sku": "6102100", "total_stock": 1}], "WAREHOUSES_NOT_REPORTED"),
])
def test_missing_sku_or_stock_never_looks_like_zero(variants, status):
    response = {"items": [{"variants": variants}]}
    row = verify_current_stock(page(), legacy(), ["9183101"], StubVendor(response=response))["rows"][0]
    assert row["status"] == status
    assert row["current_stock"] is None


def test_bad_vendor_shape_does_not_claim_success():
    with pytest.raises(EcommAppApiError, match="productos reconocibles"):
        verify_current_stock(page(), legacy(), ["9183101"], StubVendor(response={"other": []}))


def test_database_snapshots_untouched_even_after_vendor_check():
    stage, historical = page(), legacy()
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(CatalogSnapshot(source=STAGE_SOURCE, payload=stage))
        db.add(CatalogSnapshot(source="ECOMM_APP", payload=historical))
        db.add(CatalogSnapshot(source="ECOMM_APP_RAW", payload=[{"untouched": True}]))
        db.commit()
        result = EcommLiveStockService(db, StubVendor()).verify(["9211791"])
        assert result["rows"][0]["status"] == "IDENTITY_AND_STOCK_VERIFIED"
        assert db.scalar(select(CatalogSnapshot).where(CatalogSnapshot.source == STAGE_SOURCE)).payload == stage
        assert db.scalar(select(CatalogSnapshot).where(CatalogSnapshot.source == "ECOMM_APP")).payload == historical
        assert db.scalar(select(CatalogSnapshot).where(CatalogSnapshot.source == "ECOMM_APP_RAW")).payload == [{"untouched": True}]
    engine.dispose()
