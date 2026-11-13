"""Relative-to-capture differences and bounded review export; no provider I/O."""

import csv
import io
from datetime import timedelta

import pytest
from sqlalchemy import event

from app.database.models import InventoryLinkageDecision
from app.services.ecomm_api_channel_evidence import PROFILE
from app.services.ecomm_channel_coverage_service import build_channel_coverage
from app.services.ecomm_channel_export import export_differences, safe_cell
from app.services.ecomm_api_work_queue_service import build_queue
import test_ecomm_channel_comparison as comparison_fixtures
from test_ecomm_channel_comparison import product, ml, tn, pages, captures, NOW


db = comparison_fixtures.db


def test_expiry_never_removes_candidates_or_not_found_variants(db):
    products = [product(), product(2, "OTHER", name="Lentejas")]
    captures(db, products, [ml()], [tn()])
    fresh = build_channel_coverage(db, pages(products), api_validation=True, now=NOW)
    old = build_channel_coverage(
        db, pages(products), api_validation=True, now=NOW + timedelta(hours=100)
    )
    for channel in ["ml", "tn"]:
        before, after = [m["summary"]["comparison"][channel] for m in (fresh, old)]
        assert before["variant_states"] == after["variant_states"]
        assert after["variant_states"]["candidates"] == 1
        assert after["variant_states"]["no_match"] == 1
        assert (
            before["variants_with_candidates"] == after["variants_with_candidates"] == 1
        )
        assert after["stale_variants"] == 2
        assert after["variant_states"]["stale"] == 0
        assert after["deprecated_state_keys"] == ["stale"]
        assert sum(after["variant_states"].values()) == 2
        assert not old["items_by_id"]["1"][channel]["candidates"][0]["can_review"]
        assert not old["items_by_id"]["2"][channel][
            "current_publication_absence_proven"
        ]


def test_expired_human_link_is_preserved_but_does_not_confirm_current_listing(db):
    products = [product()]
    report = captures(db, products, [ml(), ml("MLA10002")])["items_by_id"]["1"]
    candidate = report["ml"]["candidates"][0]
    history = [{"decision": "APPROVED", "reason": "Synthetic explicit human decision"}]
    record = InventoryLinkageDecision(
        external_id="API_ML:MLA10001",
        ecomm_id="1",
        decision="APPROVED",
        product_snapshot=report["identity"],
        source_snapshot={"profile": PROFILE, "fingerprint": candidate["token"]},
        history=history,
    )
    db.add(record)
    db.commit()
    result = build_channel_coverage(
        db, pages(products), api_validation=True, now=NOW + timedelta(hours=100)
    )
    row = result["items_by_id"]["1"]["ml"]
    assert row["pending_candidates_count"] == 0
    assert (
        result["summary"]["comparison"]["ml"]["variants_with_pending_candidates"] == 0
    )
    assert row["identity_verified"]
    assert not row["confirmed_listing"]
    assert row["evidence_state"] == "VERIFIED_LINK"
    assert result["summary"]["comparison"]["ml"]["confirmed_publications"] == 0
    assert row["candidates"][0]["history"] == record.history == history
    assert not row["candidates"][0]["can_review"]


def test_current_capture_still_does_not_prove_current_publication_absence(db):
    report = captures(db, [product()], [ml(sku="NO-MATCH", title="Lentejas 1 kg")])
    row = report["items_by_id"]["1"]["ml"]
    assert row["freshness"]["fresh"]
    assert row["comparison_state"] == "no_match"
    assert row["evidence_state"] == "NO_MATCH_IN_CAPTURE"
    assert row["capture_completeness"] == "NOT_PROVEN_BY_STORED_CONTRACT"
    assert not row["current_publication_absence_proven"]


def test_csv_matches_table_filter_preserves_variant_ids_and_read_only(db):
    captures(
        db,
        [product(), product(2, "NOT-FOUND", name="Lentejas")],
        [ml()],
        [tn()],
        hours=100,
    )
    statements = []

    def trace(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(db.bind, "before_cursor_execute", trace)
    try:
        content, count = export_differences(db, "ml")
    finally:
        event.remove(db.bind, "before_cursor_execute", trace)
    assert all(s.lstrip().upper().startswith("SELECT") for s in statements)
    assert len(statements) <= 6
    assert content.startswith(b"\xef\xbb\xbf")
    rows = list(csv.DictReader(io.StringIO(content.decode("utf-8-sig")), delimiter=";"))
    assert count == len(rows) == 1
    assert rows[0]["ecomm_id"] == "2"
    assert rows[0]["sku"] == "NOT-FOUND"
    assert rows[0]["estado_comparacion"] == "no_match"
    assert rows[0]["captura_vigente"] == "False"
    assert rows[0]["ausencia_publicacion_actual_acreditada"] == "NO_ACREDITADA"
    assert rows[0]["captura_completa_acreditada"] == "NO_ACREDITADA"
    assert "No encontrado en esta captura" in rows[0]["siguiente_paso"]
    table = build_queue(db, sort="capture", filter_name="ml_comparison_no_match")
    assert [r["ecomm_id"] for r in table["items"]] == [r["ecomm_id"] for r in rows]


def test_export_found_captures_ids_titles_and_discrepancies_even_when_stale(db):
    captures(
        db, [product()], [ml(title="Semillas de chía Pack x2 de 250 g")], hours=100
    )
    content, count = export_differences(db, "ml", "found")
    row = list(csv.DictReader(io.StringIO(content.decode("utf-8-sig")), delimiter=";"))[
        0
    ]
    assert count == 1
    assert row["ml_ids"] == "MLA10001"
    assert row["estado_comparacion"] == "conflicts"
    assert "SALE_TYPE_CONFLICT" in row["discrepancias"]
    assert row["evidencia"] == "SKU_EXACT"


@pytest.mark.parametrize(
    "value", ["=HYPERLINK(1)", "+cmd", "-1+2", "@SUM(1)", " \t=1", "\r=1", "\ufeff=1"]
)
def test_csv_formula_injection_is_escaped(value):
    assert safe_cell(value).startswith("'")
    assert safe_cell("0000123") == "0000123"


def test_export_bounds_fail_explicitly_never_truncate(db, monkeypatch):
    captures(db, [product()], [ml()])
    with pytest.raises(ValueError, match="4.096"):
        safe_cell("x" * 4097)
    import app.services.ecomm_channel_export as module

    monkeypatch.setattr(module, "MAX_EXPORT_BYTES", 10)
    with pytest.raises(ValueError, match="10 MiB"):
        export_differences(db, "ml", "found")
    for channel, state in [("other", "all"), ("ml", "publish")]:
        with pytest.raises(ValueError):
            export_differences(db, channel, state)


def test_export_query_and_unavailable_channel_never_fabricate_missing(db):
    captures(db, [product(), product(2, "OTHER")], [ml()], None)
    content, count = export_differences(db, "ml", "all", "OTHER")
    assert count == 1 and "OTHER" in content.decode("utf-8-sig")
    _, count = export_differences(db, "tn", "no_match")
    assert count == 0
    _, count = export_differences(db, "tn", "insufficient")
    assert count == 2


def test_queue_found_stale_and_primary_filters_remain_independent(db):
    captures(
        db, [product(), product(2, "OTHER", name="Lentejas")], [ml()], [tn()], hours=100
    )
    assert build_queue(db, filter_name="ml_found")["total"] == 1
    assert build_queue(db, filter_name="ml_comparison_stale")["total"] == 2
    assert build_queue(db, filter_name="ml_found+ml_comparison_stale")["total"] == 1
    row = build_queue(db, filter_name="ml_found")["items"][0]["channel_coverage"]["ml"]
    assert row["matches_preview"][0]["id"] == "MLA10001"
    assert "token" not in row["matches_preview"][0]
    assert "history" not in row["matches_preview"][0]
    tn_row = build_queue(db, filter_name="tn_found")["items"][0]["channel_coverage"][
        "tn"
    ]
    assert tn_row["matches_preview"][0]["slug"] == "chia"
    content, count = export_differences(db, "tn", "found")
    exported = list(
        csv.DictReader(io.StringIO(content.decode("utf-8-sig")), delimiter=";")
    )
    assert count == 1 and exported[0]["tn_identificadores_url"] == "chia"


def test_csv_exports_more_than_a_table_page_without_truncating(db):
    captures(
        db,
        [product(i + 1, f"SYNTH-{i}") for i in range(61)],
        [ml(sku="UNRELATED", title="Lentejas 1 kg")],
    )
    content, count = export_differences(db, "ml", "no_match")
    rows = list(csv.DictReader(io.StringIO(content.decode("utf-8-sig")), delimiter=";"))
    assert count == len(rows) == 61
    assert [r["ecomm_id"] for r in rows] == [str(i + 1) for i in range(61)]


def test_pending_is_independent_of_conflicts_expiry_and_prior_resolved_decisions(db):
    products = [product()]
    matrix = captures(
        db, products, [ml(title="Semillas de chía Pack x2 de 250 g")], hours=100
    )
    stats = matrix["summary"]["comparison"]["ml"]
    assert (
        stats["variants_with_candidates"]
        == stats["variants_with_pending_candidates"]
        == 1
    )
    assert stats["variant_states"]["conflicts"] == 1
    assert stats["variant_states"]["candidates"] == 0
    assert build_queue(db, filter_name="ml_pending_candidates")["total"] == 1
    _, count = export_differences(db, "ml", "pending")
    assert count == 1
    record = matrix["items_by_id"]["1"]
    candidate = record["ml"]["candidates"][0]
    db.add(
        InventoryLinkageDecision(
            external_id="API_ML:MLA10001",
            ecomm_id="1",
            decision="REVOKED",
            product_snapshot=record["identity"],
            source_snapshot={"profile": PROFILE, "fingerprint": candidate["token"]},
            history=[{"decision": "REVOKED"}],
        )
    )
    db.commit()
    matrix = build_channel_coverage(db, pages(products), api_validation=True, now=NOW)
    stats = matrix["summary"]["comparison"]["ml"]
    assert stats["variants_with_candidates"] == 1
    assert stats["variants_with_pending_candidates"] == 0
    assert not matrix["items_by_id"]["1"]["ml"]["confirmed_listing"]
