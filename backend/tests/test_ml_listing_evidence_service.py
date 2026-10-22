from app.services.ml_listing_evidence_service import explain_ml_evidence


def group_with_vitaneral_aliases():
    return {
        "results": [
            {"product": {"ecomm_id": "11", "name": "Vitaneral vainilla",
                         "sku": "VITANERALVAINILLA",
                         "sku_aliases": ["VITANERALVAINILLA", "VITANERAL"]},
             "matched_listing_ids": ["MLA1", "MLA2", "MLA3", "MLA4"]},
            {"product": {"ecomm_id": "12", "name": "Vitaneral chocolate",
                         "sku": "VITANERALCHOCOLATE",
                         "sku_aliases": ["VITANERALCHOCOLATE", "VITANERAL"]},
             "matched_listing_ids": ["MLA1", "MLA2", "MLA3", "MLA4"]},
        ],
    }


def test_common_alias_is_ambiguous_but_exact_flavor_sku_is_only_a_candidate():
    source = [
        {"external_id": "MLA1", "sku": "VITANERAL", "title": "Vitaneral", "price": "44900"},
        {"external_id": "MLA2", "sku": "VITANERALVAINILLA", "title": "Vainilla"},
        {"external_id": "MLA3", "variant_sku": "VITANERALCHOCOLATE",
         "sku": "VITANERAL", "variation_id": "9876", "title": "Chocolate"},
    ]
    report = explain_ml_evidence(group_with_vitaneral_aliases(), source,
                                 "MERCADOLIBRE", "2026-10-22T12:00:00+00:00", False)
    by_id = {row["mla"]: row for row in report["rows"]}
    assert report["summary"]["mlas"] == 4
    assert by_id["MLA1"]["classification"] == "SHARED_ALIAS"
    assert {c["key"] for c in by_id["MLA1"]["candidates"]} == {"11", "12"}
    assert by_id["MLA1"]["price"] == "44900"
    assert by_id["MLA2"]["classification"] == "ONE_EXACT_SKU_CANDIDATE"
    assert [c["key"] for c in by_id["MLA2"]["candidates"]] == ["11"]
    assert by_id["MLA2"]["variation_id"] == ""
    assert "no trae un ID de variación" in by_id["MLA2"]["explanation"]
    assert by_id["MLA3"]["classification"] == "ONE_EXACT_SKU_CANDIDATE"
    assert by_id["MLA3"]["variation_id"] == "9876"
    assert [c["key"] for c in by_id["MLA3"]["candidates"]] == ["12"]
    assert by_id["MLA4"]["classification"] == "NOT_IN_SNAPSHOT"
    assert report["summary"]["with_variation_id"] == 1
    assert report["summary"]["ambiguous_rows"] == 2


def test_same_mla_multiple_rows_are_not_collapsed_to_one_variation():
    group = group_with_vitaneral_aliases()
    source = [
        {"external_id": "MLA1", "variant_sku": "VITANERALVAINILLA",
         "variation_id": "111"},
        {"external_id": "MLA1", "variant_sku": "VITANERALCHOCOLATE",
         "variation_id": "222"},
    ]
    report = explain_ml_evidence(group, source, "MERCADOLIBRE_API", None, False)
    rows = [row for row in report["rows"] if row["mla"] == "MLA1"]
    assert len(rows) == 2
    assert {row["variation_id"] for row in rows} == {"111", "222"}
    assert {row["candidates"][0]["key"] for row in rows} == {"11", "12"}


def test_empty_or_missing_snapshot_does_not_claim_any_mapped_variation():
    group = group_with_vitaneral_aliases()
    missing = explain_ml_evidence(group, None, "MERCADOLIBRE", None, True)
    assert not missing["available"]
    assert missing["rows"] == []
    no_sku = explain_ml_evidence(
        group, [{"external_id": "MLA1", "title": "Vitaneral"}],
        "MERCADOLIBRE", None, True,
    )
    assert no_sku["changed_since_run"] is True
    assert next(x for x in no_sku["rows"] if x["mla"] == "MLA1")["classification"] == "NO_SKU_EVIDENCE"
    assert not any(x["classification"] == "ONE_EXACT_SKU_CANDIDATE" for x in no_sku["rows"])


def test_identical_primary_sku_never_selects_arbitrary_product():
    group = {"results": [
        {"product": {"ecomm_id": "1", "sku": "5028"}, "matched_listing_ids": ["MLA1"]},
        {"product": {"ecomm_id": "2", "sku": "5028"}, "matched_listing_ids": ["MLA1"]},
    ]}
    report = explain_ml_evidence(
        group, [{"external_id": "MLA1", "sku": "5028"}], "MERCADOLIBRE", None, False,
    )
    assert report["rows"][0]["classification"] == "SHARED_EXACT_SKU"
    assert len(report["rows"][0]["candidates"]) == 2
