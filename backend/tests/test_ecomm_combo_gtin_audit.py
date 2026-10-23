"""Combo and repeated GTIN evidence can explain ambiguity, not prove components."""
from copy import deepcopy

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database.models import Base, CatalogSnapshot
from app.integrations.ecomm_app.catalog_stage import STAGE_SOURCE
from app.integrations.ecomm_app.ml_brand_evidence import (
    EcommMlBrandEvidenceService,
)
from app.integrations.ecomm_app.combo_gtin_audit import combo_gtin_conflict_audit


GTIN = "4006381333931"


def records():
    # Actual KIKI family example uses 5028/5028000/5028999;
    # here the GTIN owner set is only diagnostic, not membership in a pack.
    ids = [
        ("1", "5028000", True, False, None),
        ("2", "5028", False, False, GTIN),
        ("3", "5028999", False, None, GTIN),
        ("4", "9980", False, False, None),
    ]
    legacy = []
    matched = {}
    owners_sku = {}
    owners_ean = {GTIN: {"2", "3"}}
    for ident, sku, flag, parentflag, gtin in ids:
        old = {
            "ecomm_id": ident, "sku": sku, "sku_effective": sku,
            "sku_aliases": [sku], "name": f"Producto {sku} 100 g",
            "ean": gtin, "brand": None,
        }
        variant = {"id": int(ident), "sku": sku, "is_combo": flag}
        legacy.append(old)
        matched[ident] = (old, variant)
        owners_sku[sku] = {ident}
    stage = [{
        "page": 1, "per_page": 50, "total": 4, "total_pages": 1,
        "captured_at": "2026-10-23T14:00:00+00:00",
        "items": [
            {"code": sku+"_m", "is_combo": parentflag,
             "variants": [{"id": int(ident), "sku": sku, "is_combo": flag,
                           "total_stock": 1, "warehouses": [{"id": 2210, "stock": 1}]}]}
            for ident, sku, flag, parentflag, _ in ids
        ],
    }]
    ml = [
        {"external_id": "MLA111", "sku": "5028000", "ean": GTIN,
         "title": "Pack especial 100 g", "brand": "Marca A"},
        {"external_id": "MLA112", "sku": "5028000", "ean": GTIN,
         "title": "Pack especial 100 g", "brand": "Marca A"},
        {"external_id": "MLA113", "sku": "9980", "ean": GTIN,
         "title": "Otro producto 100 g", "brand": "Marca B"},
    ]
    return stage, legacy, matched, owners_sku, owners_ean, ml


def test_combo_flag_and_family_are_diagnostic_only_group_duplicate_mlas():
    pages, old, matched, by_sku, by_gtin, ml = records()
    before = deepcopy((pages, old, matched, by_sku, by_gtin, ml))
    result = combo_gtin_conflict_audit(
        matched, by_sku, by_gtin, {}, ml, {}, pages,
    )
    c = result["counts"]
    assert c["contradictory_ml_rows"] == 3
    assert c["sku_outside_gtin_owners_rows"] == 3
    assert c["distinct_sku_ids"] == 2
    assert c["distinct_gtins"] == 1
    assert c["distinct_mlas"] == 3
    assert c["distinct_sku_gtin_cases"] == 2
    assert c["sku_variant_combo_yes_rows"] == 2
    assert c["sku_variant_combo_no_rows"] == 1
    assert c["possible_combo_component_pattern_rows"] == 2
    assert c["numeric_family_hint_rows"] == 2
    assert result["components_available_in_snapshot"] is False
    assert result["activation_allowed"] is False
    assert len(result["examples"]) == 2
    first = result["examples"][0]
    assert first["category"] == "COMBO_SKU_WITH_NONCOMBO_GTIN_OWNER"
    assert first["ecomm_sku"] == "5028000"
    assert first["mla_count"] == 2
    assert first["numeric_sku_family_hint"] is True
    assert first["component_membership_confirmed"] is False
    assert first["review_status"] == "DIAGNOSTIC_ONLY"
    assert {x["ecomm_id"] for x in first["gtin_owners"]} == {"2", "3"}
    assert (pages, old, matched, by_sku, by_gtin, ml) == before


def test_mla_reference_conflict_without_gtin_owner_conflict_is_separate():
    pages, old, matched, by_sku, by_gtin, ml = records()
    # SKU 5028 is among GTIN owners, but an MLA historical reference
    # points to another Ecomm ID. It must not become a component.
    ml = [{"external_id": "MLA114", "sku": "5028", "ean": GTIN, "brand": "Marca"}]
    report = combo_gtin_conflict_audit(
        matched, by_sku, by_gtin, {"MLA114": {"3"}}, ml, {}, pages,
    )
    c = report["counts"]
    assert c["contradictory_ml_rows"] == 1
    assert c["sku_outside_gtin_owners_rows"] == 0
    assert c["mla_reference_conflict_rows"] == 1
    assert report["examples"][0]["reason_codes"] == ["HISTORICAL_MLA_CONFLICT"]


def test_not_combo_flagged_does_not_claim_component_relationship():
    pages, old, matched, by_sku, by_gtin, ml = records()
    report = combo_gtin_conflict_audit(
        matched, by_sku, by_gtin, {}, [ml[-1]], {}, pages,
    )
    case = report["examples"][0]
    assert case["category"] == "SKU_NOT_FLAGGED_COMBO"
    assert case["numeric_sku_family_hint"] is False
    assert report["counts"]["possible_combo_component_pattern_rows"] == 0
    assert case["component_membership_confirmed"] is False


def test_absent_combo_flag_and_absent_historical_stable_id_remain_unknown():
    pages, old, matched, by_sku, by_gtin, ml = records()
    pages[0]["items"][0]["variants"][0]["is_combo"] = None
    matched["1"][1]["is_combo"] = None
    report = combo_gtin_conflict_audit(
        matched, by_sku, by_gtin, {}, [ml[0]], {}, pages,
    )
    assert report["counts"]["sku_variant_combo_unknown_rows"] == 1
    assert report["counts"]["possible_combo_component_pattern_rows"] == 0
    assert report["examples"][0]["category"] == "SKU_COMBO_FLAG_UNKNOWN"


def test_invalid_barcode_no_brand_and_conflicting_brands_are_ignored():
    pages, old, matched, by_sku, by_gtin, ml = records()
    variants = [
        {**ml[0], "ean": "4006381333932"},
        {**ml[0], "brand": None, "external_id": "MLA115"},
        {**ml[0], "brand": "Different"},
    ]
    result = combo_gtin_conflict_audit(
        matched, by_sku, by_gtin, {}, variants,
        {"MLA111": {"Marca A"}}, pages,
    )
    assert result["counts"]["contradictory_ml_rows"] == 0
    assert result["examples"] == []


def test_report_and_db_snapshot_remain_read_only():
    pages, old, matched, by_sku, by_gtin, ml = records()
    # Ecomm historical GTIN is repeated by ID 2 and 3, ML snapshot repeats it,
    # and ID 1 is the combo signal, but no source data may change.
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        entries = [
            (STAGE_SOURCE, pages),
            ("ECOMM_APP", old),
            ("MERCADOLIBRE_API", ml),
            ("EDIMA_LINKAGE", [{"external_id": "MLA111", "brand": "Marca A"}]),
        ]
        for source, payload in entries:
            db.add(CatalogSnapshot(source=source, payload=payload))
        db.commit()
        result = EcommMlBrandEvidenceService(db).report()
        assert result["combo_gtin_audit"]["activation_allowed"] is False
        assert result["combo_gtin_audit"]["counts"]["contradictory_ml_rows"] >= 1
        for source, payload in entries:
            row = db.scalar(select(CatalogSnapshot).where(CatalogSnapshot.source == source))
            assert row.payload == payload
    engine.dispose()
