"""Read-only Ecomm adoption readiness: stable IDs do not authorize cutover."""
from app.integrations.ecomm_app.catalog_adoption import build_adoption_plan
from app.integrations.ecomm_app.catalog_comparison import compare_stage_to_legacy


def _report():
    return {
        "totals": {
            "historical_products": 3029,
            "api_variants": 3127,
            "matched_stable_ids": 3028,
            "same_id_same_sku": 3016,
            "same_id_format_sku_changed": 10,
            "same_id_different_sku": 2,
            "historical_no_stable_id_match": 1,
            "api_no_stable_id_match": 99,
            "api_only_combo_yes": 32,
            "api_only_combo_no": 67,
            "api_only_combo_unknown": 0,
            "stock_differences_informational": 1132,
            "duplicate_legacy_ids": 0,
        }
    }


def _stage(complete=True):
    return {
        "complete": complete,
        "first_page_at": "2026-10-23T11:00:00+00:00",
        "last_page_at": "2026-10-23T11:20:00+00:00",
        "quality": {
            "parents_without_variants": 0,
            "invalid_variants": 0,
            "without_variant_id": 0,
            "without_sku": 0,
            "without_total_stock": 0,
            "duplicate_variant_ids": 0,
        },
    }


def test_actual_kiki_counts_are_planned_not_misrepresented_as_new_products():
    plan = build_adoption_plan(_report(), _stage())
    assert plan["mode"] == "PLANNING_ONLY"
    assert plan["activation_allowed"] is False
    assert plan["mapped_by_stable_id"] == 3028
    assert plan["mapped_with_identical_sku"] == 3016
    assert plan["mapped_with_format_difference"] == 10
    assert plan["mapped_with_substantive_sku_change"] == 2
    tasks = {task["key"]: task for task in plan["tasks"]}
    assert tasks["SUBSTANTIVE_SKU"]["count"] == 2
    assert tasks["LEGACY_ONLY"]["count"] == 1
    assert tasks["API_ONLY"]["count"] == 99
    assert tasks["API_ONLY"]["combo_yes"] == 32
    assert tasks["API_ONLY"]["combo_no"] == 67
    assert tasks["FORMAT_ONLY"]["priority"] == "INFO"
    gates = {gate["key"]: gate for gate in plan["gates"]}
    assert gates["STAGED_CATALOG"]["status"] == "PASS"
    assert gates["IDENTIFIERS"]["status"] == "PASS"
    assert gates["EXCEPTIONS"]["status"] == "BLOCKED"
    assert gates["PRICING_AND_CHANNELS"]["status"] == "PENDING"
    assert gates["FRESHNESS_AND_ROLLBACK"]["status"] == "PENDING"


def test_even_perfect_ids_and_skus_cannot_authorize_full_catalog_replacement():
    report = _report()
    report["totals"].update({
        "historical_no_stable_id_match": 0,
        "api_no_stable_id_match": 0,
        "same_id_different_sku": 0,
    })
    plan = build_adoption_plan(report, _stage())
    gates = {gate["key"]: gate for gate in plan["gates"]}
    assert gates["EXCEPTIONS"]["status"] == "PASS"
    assert gates["PRICING_AND_CHANNELS"]["status"] == "PENDING"
    assert plan["activation_allowed"] is False


def test_broken_snapshot_quality_is_blocked_and_no_auto_go_live():
    stage = _stage(False)
    stage["quality"]["without_variant_id"] = 3
    report = _report()
    report["totals"]["duplicate_legacy_ids"] = 1
    plan = build_adoption_plan(report, stage)
    gates = {gate["key"]: gate for gate in plan["gates"]}
    assert gates["STAGED_CATALOG"]["status"] == "BLOCKED"
    assert gates["IDENTIFIERS"]["status"] == "BLOCKED"
    assert plan["activation_allowed"] is False


def test_integrated_comparison_embeds_read_only_adoption_plan():
    stage_pages = [{
        "version": 1, "page": 1, "total": 2, "total_pages": 1,
        "per_page": 50, "captured_at": "2026-10-23T11:00:00+00:00",
        "items": [
            {
                "code": "A", "variants": [{"id": 100, "sku": "ABC", "total_stock": 3}],
            },
            {
                "code": "B", "is_combo": True,
                "variants": [{"id": 200, "sku": "PACK2", "is_combo": True, "total_stock": 1}],
            },
        ],
    }]
    original = [{"ecomm_id": "100", "sku": "ABC", "stock": 2}]
    before = repr(stage_pages), repr(original)
    report = compare_stage_to_legacy(stage_pages, original)
    plan = report["adoption_plan"]
    assert plan["mapped_by_stable_id"] == 1
    assert report["totals"]["api_no_stable_id_match"] == 1
    assert plan["tasks"][2]["combo_yes"] == 1
    assert plan["activation_allowed"] is False
    assert before == (repr(stage_pages), repr(original))
