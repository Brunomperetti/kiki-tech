"""Secondary Tiendanube cross-catalog evidence stays unconfirmed and read-only."""
from copy import deepcopy

from app.integrations.ecomm_app.tn_brand_secondary import diagnose_tn_brand_gaps


def sample():
    pairs = [
        (1, "A1", "Vitamina Magnesio Natural 60 Capsulas", None, ""),
        (2, "B2", "Gel organico natural 100 ml", None, "4006381333931"),
        (3, "BRANDED", "Jabon Lavanda Natural 100 g", "Known", ""),
        (4, "MISSING", "Aceite vegetal organico 500 ml", None, ""),
    ]
    stage = [{"page":1,"total":4,"per_page":50,"total_pages":1,
        "items":[{"code":sku+"_m", "variants":[{"id":ident,"sku":sku,"is_combo":False}]}
                 for ident,sku,_,_,_ in pairs]}]
    old = [{"ecomm_id":str(ident),"sku":sku,"name":name,"brand":brand,"ean":ean}
           for ident,sku,name,brand,ean in pairs]
    tn = [
        {"slug":"name","sku":"X1","name":"Vitamina Magnesio Natural 60 Capsulas","brand":"Natural","ean_raw":""},
        {"slug":"ean","sku":"X2","name":"Otro gel 100 ml","brand":"Natural","ean_raw":"4006381333931"},
        {"slug":"known","sku":"BRANDED","name":"Jabon Lavanda Natural 100 g","brand":"Known","ean_raw":""},
    ]
    return stage,old,tn


def test_catalog_overlap_explained_without_assigning_any_brand():
    stage,old,tn=sample()
    before=deepcopy((stage,old,tn))
    r=diagnose_tn_brand_gaps(stage,old,tn)
    s=r["summary"]
    assert s["tn_rows"]==3
    assert s["ecomm_ids_with_existing_brand_and_tn_sku"]==1
    assert s["review_leads"]==2
    assert {x["match_basis"] for x in r["leads"]}=={"VALID_UNIQUE_EAN","UNIQUE_EXACT_FULL_NAME"}
    assert all(x["review_status"]=="NOT_CONFIRMED" for x in r["leads"])
    assert (stage,old,tn)==before


def test_duplicate_title_blocks_and_never_infers_from_partial_title():
    stage,old,tn=sample()
    tn.append({**tn[0],"slug":"copy","sku":"X3"})
    r=diagnose_tn_brand_gaps(stage,old,tn)
    assert {x["ecomm_id"] for x in r["leads"]}=={"2"}
    tn[1]["ean_raw"]="4006381333932"
    r=diagnose_tn_brand_gaps(stage,old,tn)
    assert r["summary"]["review_leads"]==0


def test_wrong_variant_sku_and_missing_tn_brand_block_leads():
    stage,old,tn=sample()
    stage[0]["items"][0]["variants"][0]["sku"]="NEW-SKU"
    tn[1]["brand"]=""
    r=diagnose_tn_brand_gaps(stage,old,tn)
    assert r["summary"]["review_leads"]==0
