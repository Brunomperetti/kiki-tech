"""ML/EDIMA brand lead verification: all joins are diagnostic, no writes."""
from copy import deepcopy

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database.models import Base, CatalogSnapshot
from app.integrations.ecomm_app.catalog_stage import STAGE_SOURCE
from app.integrations.ecomm_app.ml_brand_evidence import (
    EcommMlBrandEvidenceService,
    ml_brand_evidence_report,
)
from app.integrations.mercadolibre.transformer import transform_item


def fixtures():
    cases = [
        (1,"A1",None,None,None),
        (2,"B2",None,None,"MLA202"),
        (3,"C3",None,"4006381333931",None),
        (4,"BRANDED","Already branded",None,None),
        (5,"SHARED",None,None,None),
        (6,"SHARED",None,None,None),
        (7,"D7",None,None,None),
        (8,"E8",None,None,None),
        (9,"OTHER","Already known",None,"MLA888"),
    ]
    stage=[{"page":1,"per_page":50,"total":len(cases),"total_pages":1,
            "captured_at":"2026-10-23T14:00:00+00:00",
            "items":[{
                "code":sku+"_m",
                "variants":[{
                    "id":ident,"sku":sku,"is_combo":ident==1,
                    "total_stock":1,"warehouses":[{"id":2210,"stock":1}],
                }],
            } for ident,sku,_,_,_ in cases]}]
    historical=[]
    for ident,sku,brand,ean,mla in cases:
        historical.append({
            "ecomm_id":str(ident),
            "sku":sku,"sku_effective":sku,"sku_aliases":[sku],
            "name":f"Producto ejemplo {ident} 100g",
            "brand":brand,"ean":ean,"ecomm_rows":[
                {"listing_id":mla,"marketplace_id":None}
            ] if mla else [],
        })
    ml=[
        {"external_id":"MLA101#111","sku":"A1","variant_sku":"A1",
         "title":"Producto ejemplo 1 100g","brand":"Vitamin"},
        {"external_id":"MLA303","sku":"X3","ean":"4006381333931",
         "title":"Producto ejemplo 3 100g","brand":"Natural"},
        {"external_id":"MLA555","sku":"SHARED","brand":"Unknown","title":"Producto 100g"},
        {"external_id":"MLA777","sku":"D7","brand":"Brand A","title":"Producto ejemplo 7 100g"},
        {"external_id":"MLA888","sku":"E8","brand":"Brand E","title":"Producto ejemplo 8 100g"},
    ]
    edima=[
        {"external_id":"MLA101","brand":"Vitamin","title":"Producto ejemplo 1 100g","gtins":[]},
        {"external_id":"MLA202","brand":"Lauri","title":"Producto ejemplo 2 100g","gtins":[]},
        {"external_id":"MLA777","brand":"Brand B","title":"Producto ejemplo 7 100g","gtins":[]},
    ]
    return stage,historical,ml,edima


def test_existing_ml_brand_and_edima_unique_reference_or_gtin_give_review_only_leads():
    stage,historical,ml,edima=fixtures()
    before=deepcopy((stage,historical,ml,edima))
    r=ml_brand_evidence_report(stage,historical,ml,edima,"MERCADOLIBRE_API")
    assert r["activation_allowed"] is False
    assert r["mode"]=="REVIEW_ONLY_ML_BRAND_EVIDENCE"
    assert r["summary"]["unique_brand_review_leads"]==3
    assert r["summary"]["missing_historical_brand"]==7
    assert r["summary"]["combo_leads"]==1
    assert r["summary"]["conflicting_listing_brands"]==1
    assert r["summary"]["ambiguous_identifiers"]>=2
    assert {x["ecomm_id"] for x in r["candidates"]}=={"1","2","3"}
    assert {x["review_status"] for x in r["candidates"]}=={"NEEDS_HUMAN_VERIFICATION"}
    assert r["sources"]["ml_rows_with_brand"]==5
    assert r["sources"]["edima_rows_with_brand"]==3
    assert (stage,historical,ml,edima)==before


def test_old_ml_snapshot_without_brand_can_use_edima_for_unique_sku():
    stage,historical,ml,edima=fixtures()
    ml[0]["brand"]=None
    r=ml_brand_evidence_report(stage,historical,ml,edima,"MERCADOLIBRE_API")
    by_id={x["ecomm_id"]:x for x in r["candidates"]}
    assert by_id["1"]["ml_brand"]=="Vitamin"
    assert by_id["1"]["ml_source"]=="EDIMA_LINKAGE"


def test_conflicting_brand_for_same_ecomm_id_is_never_proposed():
    stage,historical,ml,edima=fixtures()
    ml.append({"external_id":"MLA103","sku":"A1","brand":"Different",
               "title":"Producto ejemplo 1 100g"})
    r=ml_brand_evidence_report(stage,historical,ml,edima,"MERCADOLIBRE_API")
    assert r["summary"]["conflicting_brands_per_ecomm_id"]==1
    assert "1" not in {x["ecomm_id"] for x in r["candidates"]}


def test_no_ml_and_no_edima_reports_missing_source_and_zero_leads():
    stage,historical,_,_=fixtures()
    r=ml_brand_evidence_report(stage,historical,[],[],"MERCADOLIBRE")
    assert r["available"] is False
    assert r["summary"]["unique_brand_review_leads"]==0
    assert r["candidates"]==[]


def test_substantive_api_sku_change_is_excluded():
    stage,historical,ml,edima=fixtures()
    stage[0]["items"][0]["variants"][0]["sku"]="DIFFERENT"
    r=ml_brand_evidence_report(stage,historical,ml,edima,"MERCADOLIBRE_API")
    assert "1" not in {x["ecomm_id"] for x in r["candidates"]}


def test_ml_sku_and_ean_conflict_rejects_weak_mla():
    stage,historical,ml,edima=fixtures()
    ml[0]["ean"]="4006381333931"  # belongs to ID 3 while SKU A1 belongs to ID 1
    r=ml_brand_evidence_report(stage,historical,ml,edima,"MERCADOLIBRE_API")
    assert "1" not in {x["ecomm_id"] for x in r["candidates"]}


def test_partial_stage_rejected_and_repeated_ecomm_id_blocks_lead():
    stage,historical,ml,edima=fixtures()
    stage[0]["total_pages"]=2
    with pytest.raises(ValueError,match="completa"):
        ml_brand_evidence_report(stage,historical,ml,edima,"MERCADOLIBRE_API")
    stage[0]["total_pages"]=1
    historical.append(deepcopy(historical[0]))
    r=ml_brand_evidence_report(stage,historical,ml,edima,"MERCADOLIBRE_API")
    assert "1" not in {x["ecomm_id"] for x in r["candidates"]}


def test_ml_api_transformer_preserves_explicit_brand_but_does_not_infer_title():
    item={
        "id":"MLA345","title":"Aromas marca XYZ 50 ml","status":"active",
        "price":100,
        "attributes":[
            {"id":"BRAND","value_name":"Marca Real"},
            {"id":"SELLER_SKU","value_name":"SKU1"},
        ],
    }
    listing=transform_item(item)[0]
    assert listing.brand=="Marca Real"
    assert listing.sku=="SKU1"
    assert transform_item({**item,"attributes":[]})[0].brand is None


def test_service_only_reads_sqlite_snapshots_without_writes():
    stage,historical,ml,edima=fixtures()
    engine=create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        for source,payload in [
            (STAGE_SOURCE,stage),("ECOMM_APP",historical),
            ("MERCADOLIBRE_API",ml),("EDIMA_LINKAGE",edima),
            ("TIENDANUBE",[{"sku":"TN"}]),
        ]:
            db.add(CatalogSnapshot(source=source,payload=payload))
        db.commit()
        report=EcommMlBrandEvidenceService(db).report()
        assert report["summary"]["unique_brand_review_leads"]==3
        assert report["source_dates"]["ml_snapshot"]
        for source,payload in [
            (STAGE_SOURCE,stage),("ECOMM_APP",historical),
            ("MERCADOLIBRE_API",ml),("EDIMA_LINKAGE",edima),
            ("TIENDANUBE",[{"sku":"TN"}]),
        ]:
            assert db.scalar(select(CatalogSnapshot).where(CatalogSnapshot.source==source)).payload==payload
    engine.dispose()


def test_ambiguous_ml_reasons_are_reported_without_weakening_exclusions():
    stage, historical, ml, edima = fixtures()
    unchanged = deepcopy((stage, historical, ml, edima))
    report = ml_brand_evidence_report(stage, historical, ml, edima, "MERCADOLIBRE_API")
    counts = report["diagnostics"]["counts"]
    assert counts["shared_sku"] >= 1
    assert counts["identity_signal_conflicts"] >= 1
    assert counts["ml_rows_with_brand_disagreements"] == 1
    assert counts["ml_rows_ambiguous"] >= 2
    assert counts["distinct_mlas_ambiguous"] >= 2
    assert all(x["classification"] == "HUMAN_REVIEW_ONLY" for x in report["diagnostics"]["examples"])
    assert {x["ecomm_id"] for x in report["candidates"]} == {"1", "2", "3"}
    assert (stage, historical, ml, edima) == unchanged


def test_shared_mla_with_unique_variant_sku_is_only_a_hint():
    stage, historical, ml, edima = fixtures()
    historical[0]["ecomm_rows"] = [{"listing_id": "MLA101"}]
    historical[1]["ecomm_rows"] = [{"listing_id": "MLA101"}]
    report = ml_brand_evidence_report(stage, historical, ml, edima, "MERCADOLIBRE_API")
    detail = report["diagnostics"]["counts"]
    assert detail["shared_historical_mla"] >= 1
    assert detail["shared_mla_with_unique_variant_sku"] >= 1
    assert report["diagnostics"]["examples"][0]["unique_variant_sku_present"] is True
    assert "1" not in {x["ecomm_id"] for x in report["candidates"]}
    assert report["activation_allowed"] is False


def test_missing_source_diagnostics_have_zero_counts_and_no_examples():
    stage, historical, _, _ = fixtures()
    report = ml_brand_evidence_report(stage, historical, [], [], "MERCADOLIBRE")
    assert report["diagnostics"]["counts"]["ml_rows_ambiguous"] == 0
    assert report["diagnostics"]["examples"] == []


def test_read_only_service_returns_diagnostics_and_preserves_database():
    stage, historical, ml, edima = fixtures()
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        for source, payload in [
            (STAGE_SOURCE, stage),
            ("ECOMM_APP", historical),
            ("MERCADOLIBRE_API", ml),
            ("EDIMA_LINKAGE", edima),
        ]:
            db.add(CatalogSnapshot(source=source, payload=payload))
        db.commit()
        report = EcommMlBrandEvidenceService(db).report()
        assert "diagnostics" in report
        assert report["diagnostics"]["counts"]["ml_rows_ambiguous"] >= 2
        for source, payload in [
            (STAGE_SOURCE, stage),
            ("ECOMM_APP", historical),
            ("MERCADOLIBRE_API", ml),
            ("EDIMA_LINKAGE", edima),
        ]:
            stored = db.scalar(select(CatalogSnapshot).where(CatalogSnapshot.source == source))
            assert stored.payload == payload
    engine.dispose()
