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



def test_vitaneral_real_world_spaces_and_case_are_possible_format_matches_only():
    rows = [
        {"external_id": "MLA1696309857", "sku": "vitaneral chocolate",
         "title": "Vitaneral chocolate", "price": "30000"},
        {"external_id": "MLA3030370902", "sku": "Vitaneral Vainilla",
         "title": "Vitaneral vainilla", "price": "30000"},
        {"external_id": "MLA3289072432", "sku": "Vitaneral Vainilla",
         "title": "Vitaneral vainilla", "price": "34737.25"},
        {"external_id": "MLA3289072434", "sku": "vitaneral chocolate",
         "title": "Vitaneral chocolate", "price": "34737.25"},
    ]
    group = group_with_vitaneral_aliases()
    for index, row in enumerate(group["results"]):
        row["matched_listing_ids"] = [item["external_id"] for item in rows]
    report = explain_ml_evidence(
        group, rows, "MERCADOLIBRE_API", "2026-10-05T11:18:55+00:00", False,
    )
    assert report["summary"]["mlas"] == 4
    assert report["summary"]["normalized_sku_candidate_rows"] == 4
    assert report["summary"]["exact_sku_candidate_rows"] == 0
    assert report["summary"]["ambiguous_rows"] == 0
    assert report["summary"]["with_variation_id"] == 0
    for item in report["rows"]:
        assert item["classification"] == "NORMALIZED_SKU_CANDIDATE"
        assert len(item["candidates"]) == 1
        assert item["variation_id"] == ""
        assert "No es una vinculación verificada" in item["explanation"]
        if "chocolate" in item["sku"].lower():
            assert item["candidates"][0]["key"] == "12"
        else:
            assert item["candidates"][0]["key"] == "11"


def test_normalization_collisions_block_even_a_single_literal_sku_match():
    group = {
        "results": [
            {"product": {"ecomm_id": "1", "sku": "AB C"}, "matched_listing_ids": ["MLA1"]},
            {"product": {"ecomm_id": "2", "sku": "A BC"}, "matched_listing_ids": ["MLA1"]},
        ],
    }
    for ml_sku in ("ABC", "AB C"):
        report = explain_ml_evidence(
            group, [{"external_id": "MLA1", "sku": ml_sku}], "MERCADOLIBRE", None, False
        )
        assert report["rows"][0]["classification"] == "SHARED_NORMALIZED_SKU"
        assert len(report["rows"][0]["candidates"]) == 2
        assert report["summary"]["ambiguous_rows"] == 1


def test_punctuation_is_not_deleted_from_normalization():
    group = {
        "results": [
            {"product": {"ecomm_id": "1", "sku": "AB-12"}, "matched_listing_ids": ["MLA1"]},
            {"product": {"ecomm_id": "2", "sku": "ZZ-12"}, "matched_listing_ids": ["MLA1"]},
        ],
    }
    report = explain_ml_evidence(
        group, [{"external_id": "MLA1", "sku": "AB 12"}], "MERCADOLIBRE", None, False
    )
    assert report["rows"][0]["classification"] == "NO_SKU_EVIDENCE"
    assert report["summary"]["normalized_sku_candidate_rows"] == 0
