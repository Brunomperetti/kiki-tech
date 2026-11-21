"""Offline-only documentary cohort planning: never trusts a brand phrase as fact."""
import csv
from io import StringIO

import pytest

from app.services.documentary_cohort_planner_service import (
    BRAND_PHRASES, MAX_COHORT, _brand_mentions,
    export_documentary_cohorts_csv, plan_cohorts_from_audit,
)


def row(ident, sku, name, *, presentation="250 g",
        barcode="7798180790097", stage="FIND_ORIGINAL",
        gap=None, captured="2026-11-20T21:03:00+00:00"):
    return {
        "ecomm_id": str(ident), "sku": str(sku), "name": name,
        "presentation": presentation, "api_barcode": barcode,
        "captured_at": captured, "quality_stage": stage,
        "gaps": gap or [],
    }


def build(rows):
    return plan_cohorts_from_audit(
        {"total": len(rows), "classified_variants": len(rows)}, rows
    )


def test_only_literal_brand_hints_grouped_and_still_unverified():
    rows = [
        row(9, "9", "Mix Semillas Natural Seed x250gr"),
        row(1, "1", "Té Saint Gottard x20 saquitos"),
        row(2, "2", "Producto sin mención textual"),
        row(3, "3", "Natural Seed y Saint Gottard - revisión"),
        row(4, "4", "Combo Natural Seed 3 unidades"),
        row(5, "5", "Natural Seed con código duplicado",
            gap=["BARCODE_RESEARCH_NOT_ELIGIBLE"]),
        row(6, "6", "Natural Seed ya documentado", stage="REVIEW_ORIGINAL"),
        row(7, "7", "Natural Seed mismo envase", stage="REVIEW_MEDIA_AND_CHANNEL"),
    ]
    before = [dict(r) for r in rows]
    data = build(rows)
    assert rows == before
    assert data["total_variants"] == 8
    assert data["eligible_to_look_up"] == 5
    assert data["grouped_variants"] == 2
    assert data["unattributed"] == 1
    assert data["ambiguous_brand_mentions"] == 1
    assert data["pack_text_suspects"] == 1
    assert data["barcode_not_eligible_for_research"] == 1
    assert data["other_quality_stages"] == 2
    assert [c["brand_phrase"] for c in data["cohorts"]] == [
        "Natural Seed", "Saint Gottard",
    ]
    assert data["cohorts"][0]["items"][0]["ecomm_id"] == "9"
    assert all(
        c["count"] <= MAX_COHORT and
        c["brand_verified"] is False and
        c["manufacturer_verified"] is False and
        c["source_urls_verified"] == 0
        for c in data["cohorts"]
    )
    assert data["external_writes_enabled"] is False
    assert data["network_requests"] == data["ai_requests"] == data["db_writes"] == 0
    assert data["can_auto_fetch"] is False


def test_lots_are_bounded_20_deterministic_with_current_capture_signature():
    rows = [
        row(i, f"{100-i:03d}", "DIMAX x 30", captured="2026-11-20T16:10:00Z")
        for i in range(1, 44)
    ]
    a = build(rows)
    b = build(list(reversed(rows)))
    assert a["capture_fingerprint"] == b["capture_fingerprint"]
    assert a["plan_fingerprint"] == b["plan_fingerprint"]
    assert [c["count"] for c in a["cohorts"]] == [20, 20, 3]
    assert [c["id"] for c in a["cohorts"]] == ["P001", "P002", "P003"]
    assert a["grouped_variants"] == 43
    new = [dict(r) for r in rows]
    new[0]["sku"] = "changed-sku"
    assert build(new)["capture_fingerprint"] != a["capture_fingerprint"]
    new[0] = dict(rows[0])
    new[0]["captured_at"] = "2026-11-20T21:03:00Z"
    assert build(new)["capture_fingerprint"] != a["capture_fingerprint"]


def test_unverified_name_never_infers_a_brand_from_fuzzy_match():
    assert _brand_mentions("Natural Seed x 250 gr") == ["Natural Seed"]
    assert _brand_mentions("NATURAL-SEED 250 gr") == ["Natural Seed"]
    assert _brand_mentions("Sáint Göttard 20 saquitos") == ["Saint Gottard"]
    assert _brand_mentions("LAUREL, hoja") == []
    assert _brand_mentions("DIMAX-VITAMIN WAY") == ["Dimax", "Vitamin Way"]
    assert len(BRAND_PHRASES) == len(set(BRAND_PHRASES))


def test_csv_escapes_formula_and_contains_only_safe_review_candidates():
    plans = build([
        row(1, "12", "Natural Seed =HYPERLINK(1)"),
        row(2, "3", "Natural Seed", presentation="Pack x 2"),
        row(3, "4", "Natural Seed", gap=["BARCODE_RESEARCH_NOT_ELIGIBLE"]),
    ])
    csv_body = export_documentary_cohorts_csv(plans)
    assert csv_body.startswith("\ufeff")
    values = list(csv.DictReader(StringIO(csv_body[1:])))
    assert len(values) == 1
    assert values[0]["ecomm_id"] == "1"
    assert values[0]["fabricante_validado"] == "NO"
    assert values[0]["url_oficial_validada"] == "NO"
    assert values[0]["huella_captura"] == plans["capture_fingerprint"]
    assert values[0]["huella_plan"] == plans["plan_fingerprint"]
    assert values[0]["nombre_api"] == "Natural Seed =HYPERLINK(1)"
    malicious = build([row("=CMD", "+HACK", "Natural Seed")])
    escaped = list(csv.reader(StringIO(
        export_documentary_cohorts_csv(malicious)[1:]
    )))
    assert escaped[1][2].startswith("'=")
    assert escaped[1][3].startswith("'+")


def test_invalid_audit_does_not_produce_partial_cohorts():
    one = row(1, 1, "Natural Seed")
    with pytest.raises(ValueError, match="incompleta|repetidas"):
        plan_cohorts_from_audit({"total": 3, "classified_variants": 3}, [one])
    with pytest.raises(ValueError, match="incompleta|repetidas"):
        plan_cohorts_from_audit(
            {"total": 2, "classified_variants": 2}, [one, dict(one)]
        )
    with pytest.raises(ValueError, match="incompleta|repetidas"):
        plan_cohorts_from_audit(
            {"total": 1, "classified_variants": 0}, [one]
        )


def test_documentary_review_changes_cohort_membership_without_changing_capture():
    products = [
        row(1, "1001", "Natural Seed Mix 250 g"),
        row(2, "1002", "Natural Seed Cereales 250 g"),
    ]
    before = build(products)
    after_rows = [dict(p) for p in products]
    # A reviewed/imported original changes quality stage, not the source API.
    after_rows[0]["quality_stage"] = "REVIEW_ORIGINAL"
    after = build(after_rows)
    assert after["capture_fingerprint"] == before["capture_fingerprint"]
    assert after["plan_fingerprint"] != before["plan_fingerprint"]
    assert after["cohorts"][0]["count"] == 1
    assert after["cohort_count"] == before["cohort_count"]
