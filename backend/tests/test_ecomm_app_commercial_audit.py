"""Read-only quality audit for historically matched Ecomm-App commercial data."""
from copy import deepcopy
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
import pytest

from app.database.models import Base, CatalogSnapshot
from app.integrations.ecomm_app.catalog_stage import STAGE_SOURCE
from app.integrations.ecomm_app.commercial_audit import (
    commercial_fields_audit, _price_class,
)


def sample_data():
    stage = [{
        "version":1, "page":1, "total":6, "total_pages":1,
        "per_page":50, "captured_at":"2026-10-23T14:00:00+00:00",
        "items":[
            {
                "code":f"P{i}", "description":f"Product {i}",
                "is_combo":i in (2,5),
                "variants":[{
                    "id":i, "sku":f"S{i}", "total_stock":10,
                    "is_combo":i in (2,5), "warehouses":[{"id":2210,"stock":10}],
                }],
            } for i in range(1,7)
        ],
    }]
    old = [
        {"ecomm_id":"1","name":"A","sku":"S1","brand":"Natufarma",
         "list_price":"100","cost":"25","ean":"779000001"},
        {"ecomm_id":"2","name":"B","sku":"S2","brand":"",
         "list_price":"0","cost":"-5","ean":None},
        {"ecomm_id":"3","name":"C","sku":"S3","brand":"Sin Marca",
         "list_price":None,"price":20,"cost":"not-cost","ean":""},
        {"ecomm_id":"4","name":"D","sku":"S4","brand":"Lauri",
         "list_price":None,"cost":None,"ean":"779000002"},
        {"ecomm_id":"5","name":"E","sku":"S5","brand":None,
         "list_price":"-3","cost":"0","ean":None},
        {"ecomm_id":"6","name":"F","sku":"S6","brand":"Sundance",
         "list_price":"NaN","cost":"8","ean":None},
    ]
    return stage, old


def test_counts_are_disjoint_and_zero_or_invalid_values_are_not_healthy():
    stage, old = sample_data()
    before = deepcopy((stage, old))
    result = commercial_fields_audit(stage, old)
    assert result["mode"] == "READ_ONLY_COMMERCIAL_AUDIT"
    assert result["activation_allowed"] is False
    c = result["counts"]
    assert c["matched_ids"] == 6
    assert c["brand_present"] == 3
    assert c["brand_missing"] == 2
    assert c["brand_placeholder"] == 1
    assert c["price_positive"] == 2
    assert c["price_zero"] == 1
    assert c["price_missing"] == 1
    assert c["price_negative"] == 1
    assert c["price_invalid"] == 1
    assert c["cost_positive"] == 2
    assert c["cost_zero"] == 1
    assert c["cost_missing"] == 1
    assert c["cost_negative"] == 1
    assert c["cost_invalid"] == 1
    assert c["ean_present"] == 2
    assert c["ean_blank"] == 4
    assert c["combo_matched"] == 2
    assert c["combo_without_brand"] == 2
    assert [x["ecomm_id"] for x in result["samples"]["without_brand"]] == ["2", "3", "5"]
    assert (stage, old) == before


def test_brand_is_not_inferred_from_product_title_or_api_parent_name():
    stage, old = sample_data()
    old[1]["name"] = "Sundance Pack"
    stage[0]["items"][1]["description"] = "Sundance Pack"
    result = commercial_fields_audit(stage, old)
    assert result["counts"]["brand_missing"] == 2
    assert any(x["ecomm_id"] == "2" for x in result["samples"]["without_brand"])


def test_duplicate_ids_do_not_count_or_pick_first_arbitrarily():
    stage, old = sample_data()
    old.append({**old[0], "name":"WRONG DUPLICATE"})
    result = commercial_fields_audit(stage, old)
    assert result["counts"]["matched_ids"] == 5
    assert result["counts"]["brand_present"] == 2


def test_non_matching_legacy_and_api_items_are_excluded_from_historical_audit():
    stage, old = sample_data()
    old.append({"ecomm_id":"999","brand":"Brand","list_price":25,"cost":10})
    stage[0]["items"].append({
        "code":"API-ONLY","variants":[{"id":777,"sku":"Z","total_stock":0}],
    })
    stage[0]["total"] = 7
    result = commercial_fields_audit(stage, old)
    assert result["counts"]["matched_ids"] == 6


@pytest.mark.parametrize("value,status", [
    (None,"MISSING"),("", "MISSING"),("  ", "MISSING"),
    ("0","ZERO"),(0.0,"ZERO"),(0,"ZERO"),
    ("-1","NEGATIVE"),("n/a","INVALID"),(True,"MISSING"),
    ("NaN","INVALID"),("Infinity","INVALID"),("1e2","POSITIVE"),
])
def test_financial_value_is_classified_without_guessing(value,status):
    assert _price_class(value) == status


def test_partial_stage_and_missing_history_fail_closed():
    stage, old = sample_data()
    with pytest.raises(ValueError, match="completa"):
        commercial_fields_audit([], old)
    with pytest.raises(ValueError, match="histórico"):
        commercial_fields_audit(stage, [])


def test_audit_does_not_mutate_any_persisted_snapshot():
    stage, historical = sample_data()
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(CatalogSnapshot(source=STAGE_SOURCE,payload=stage))
        db.add(CatalogSnapshot(source="ECOMM_APP",payload=historical))
        db.add(CatalogSnapshot(source="ECOMM_APP_RAW",payload=[{"untouched": True}]))
        db.commit()
        api=db.scalar(select(CatalogSnapshot).where(CatalogSnapshot.source==STAGE_SOURCE))
        old=db.scalar(select(CatalogSnapshot).where(CatalogSnapshot.source=="ECOMM_APP"))
        report=commercial_fields_audit(api.payload,old.payload)
        assert report["counts"]["matched_ids"]==6
        assert db.scalar(select(CatalogSnapshot).where(CatalogSnapshot.source==STAGE_SOURCE)).payload==stage
        assert db.scalar(select(CatalogSnapshot).where(CatalogSnapshot.source=="ECOMM_APP")).payload==historical
        assert db.scalar(select(CatalogSnapshot).where(CatalogSnapshot.source=="ECOMM_APP_RAW")).payload==[{"untouched": True}]
    engine.dispose()
