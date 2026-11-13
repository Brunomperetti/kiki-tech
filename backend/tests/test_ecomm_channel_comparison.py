"""Captured DTOs only: no credentials, provider calls, imported spreadsheets or jobs."""

from datetime import datetime, timedelta, timezone
from time import perf_counter

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.database.models import Base, CatalogSnapshot, InventoryLinkageDecision
from app.services.ecomm_channel_coverage_service import build_channel_coverage
from app.services.ecomm_channel_listings import listings
from app.services.ecomm_api_work_queue_service import build_queue

NOW = datetime.now(timezone.utc)


def product(
    ident=1,
    sku="SYNTH-1",
    *,
    name="Semillas de chía",
    size="250 g",
    code=None,
    combo=False,
):
    return {
        "description": name,
        "brand": "Marca sintética",
        "is_combo": combo,
        "variants": [
            {
                "id": ident,
                "sku": sku,
                "description": size,
                "is_combo": combo,
                "barcode": code,
            }
        ],
    }


def pages(products):
    return [
        {
            "page": 1,
            "total": len(products),
            "total_pages": 1,
            "per_page": len(products),
            "captured_at": NOW.isoformat(),
            "items": products,
        }
    ]


def ml(ident="MLA10001", sku="SYNTH-1", *, title="Semillas de chía 250 g", code=None):
    return {
        "external_id": ident,
        "sku": sku,
        "sku_effective": sku,
        "title": title,
        "brand": "Marca sintética",
        "ean": code,
        "status": "active",
    }


def tn(slug="chia", sku="SYNTH-1", *, name="Semillas de chía", size="250 g", code=None):
    return {
        "slug": slug,
        "sku": sku,
        "name": name,
        "brand": "Marca sintética",
        "ean_raw": code,
        "variant": [{"property": "Peso", "value": size}],
    }


@pytest.fixture
def db(tmp_path):
    engine = create_engine("sqlite:///" + str(tmp_path / "synthetic.db"))
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def captures(db, products, ml_rows=None, tn_rows=None, hours=0):
    for source, data in [
        ("ECOMM_APP_API_STAGE", pages(products)),
        ("MERCADOLIBRE_API", ml_rows),
        ("TIENDANUBE", tn_rows),
    ]:
        if data is not None:
            db.add(
                CatalogSnapshot(
                    source=source, payload=data, updated_at=NOW - timedelta(hours=hours)
                )
            )
    db.commit()
    return build_channel_coverage(db, pages(products), api_validation=True, now=NOW)


def test_exact_sku_keeps_candidate_and_comparison_evidence_never_approves(db):
    m = captures(db, [product()], [ml()], [tn()])
    for channel in ["ml", "tn"]:
        row = m["items_by_id"]["1"][channel]
        assert row["comparison_state"] == "candidates"
        assert "SKU_EXACT" in row["candidates"][0]["match_reasons"]
        assert not row["identity_verified"] and not row["confirmed_listing"]
        assert row["candidates"][0]["comparison"]["ecomm_presentation"] == "250 g"
        assert m["summary"]["comparison"][channel]["variant_states"]["candidates"] == 1


def test_missing_or_different_sku_can_use_valid_gtin_without_linking(db):
    m = captures(
        db,
        [product(code="12345670")],
        [ml(sku=None, code="12345670")],
        [tn(sku="DIFFERENT", code="12345670")],
    )
    for channel in ["ml", "tn"]:
        c = m["items_by_id"]["1"][channel]["candidates"][0]
        assert "VALID_GTIN_EXACT" in c["match_reasons"]
        assert not c["identity_verified"]
    assert m["summary"]["comparison"]["ml"]["records_without_sku"] == 1


def test_exact_brand_title_can_find_record_without_sku_or_ean(db):
    m = captures(db, [product()], [ml(sku=None)], [tn(sku=None)])
    for channel in ["ml", "tn"]:
        assert m["items_by_id"]["1"][channel]["candidates_total"] == 1
        assert (
            "TITLE_EXACT"
            in m["items_by_id"]["1"][channel]["candidates"][0]["match_reasons"]
        )


def test_repeated_sku_and_same_ean_keep_distinct_ids_and_candidates(db):
    m = captures(
        db,
        [product(1, code="12345670"), product(2, size="500 g", code="12345670")],
        [ml(code="12345670")],
        [],
    )
    assert set(m["items_by_id"]) == {"1", "2"}
    assert all(r["ml"]["candidates_total"] == 1 for r in m["items_by_id"].values())
    assert all(not r["ml"]["confirmed_listing"] for r in m["items_by_id"].values())
    assert m["summary"]["comparison"]["ml"]["variant_states"]["conflicts"] == 2
    assert m["summary"]["comparison"]["ml"]["captured_records"] == 1
    assert m["summary"]["comparison"]["ml"]["candidate_pairs"] == 2


def test_pack_two_does_not_validate_individual_even_with_same_sku(db):
    m = captures(db, [product()], [ml(title="Semillas de chía Pack x2 de 250 g")])
    row = m["items_by_id"]["1"]["ml"]
    assert row["comparison_state"] == "conflicts"
    assert "SALE_TYPE_CONFLICT" in row["candidates"][0]["discrepancies"]
    assert not row["candidates"][0]["can_review"]


def test_barcode_gtin_conflict_and_channel_gtin_conflict_block(db):
    prod = product(code="12345670")
    prod["variants"][0]["gtin"] = "12345685"
    m = captures(db, [prod], [ml(code="12345670")])
    assert m["items_by_id"]["1"]["ml"]["evidence_state"] == "IDENTITY_CONFLICT"
    assert not m["items_by_id"]["1"]["ml"]["candidates"][0]["can_review"]


def test_stale_capture_exposes_candidates_but_never_current_confirmation(db):
    m = captures(db, [product()], [ml()], [tn()], hours=100)
    for channel in ["ml", "tn"]:
        c = m["items_by_id"]["1"][channel]
        assert c["comparison_state"] == "stale"
        assert c["candidates_total"] == 1
        assert not c["candidates"][0]["can_review"]
        assert m["summary"]["comparison"][channel]["freshness"]["age_hours"] == 100


def test_absent_channel_and_no_match_have_different_explanations(db):
    m = captures(db, [product()], [ml(sku="OTHER", title="Lentejas 1 kg")])
    assert m["items_by_id"]["1"]["ml"]["comparison_state"] == "no_match"
    assert m["items_by_id"]["1"]["tn"]["comparison_state"] == "insufficient"
    assert "No existe captura" in m["items_by_id"]["1"]["tn"]["no_candidates_reason"]


def test_unsearchable_channel_does_not_assert_no_match(db):
    m = captures(db, [product()], [{"external_id": "MLA10001"}])
    assert m["items_by_id"]["1"]["ml"]["comparison_state"] == "insufficient"
    assert "captura no contiene" in m["items_by_id"]["1"]["ml"]["no_candidates_reason"]


def test_listing_rows_offer_candidates_without_verified_identity(db):
    captures(db, [product()], [ml()], [tn()])
    for channel in ["ml", "tn"]:
        result = listings(db, channel, linkage="candidates")
        assert result["items"][0]["candidate_ecomm_ids"] == ["1"]
        assert result["items"][0]["ecomm_ids"] == []
        assert not result["items"][0]["confirmed_listing"]


def test_3001_variants_exact_reconciliation_and_constant_queries(db):
    size = 3001
    products = [product(i + 1, f"SYNTH-{i}") for i in range(size)]
    mls = [ml(f"MLA{100000+i}", f"SYNTH-{i}") for i in range(2844)]
    tns = [tn(f"synthetic-{i}", f"SYNTH-{i}") for i in range(550)]
    # Code-backed candidates should not expand into the whole brand/family.
    for i, prod in enumerate(products):
        prod["description"] += f" serie {i}"
    for i, row in enumerate(mls):
        row["title"] = f"Semillas de chía serie {i} 250 g"
    for i, row in enumerate(tns):
        row["name"] = f"Semillas de chía serie {i}"
    for source, data in [
        ("ECOMM_APP_API_STAGE", pages(products)),
        ("MERCADOLIBRE_API", mls),
        ("TIENDANUBE", tns),
    ]:
        db.add(CatalogSnapshot(source=source, payload=data, updated_at=NOW))
    db.commit()
    statements = []

    def trace(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(db.bind, "before_cursor_execute", trace)
    began = perf_counter()
    m = build_channel_coverage(db, pages(products), api_validation=True, now=NOW)
    duration = perf_counter() - began
    event.remove(db.bind, "before_cursor_execute", trace)
    assert len(statements) == 4
    assert all(s.lstrip().upper().startswith("SELECT") for s in statements)
    for channel, records in [("ml", 2844), ("tn", 550)]:
        stats = m["summary"]["comparison"][channel]
        assert sum(stats["variant_states"].values()) == size
        assert stats["captured_records"] == records
        assert stats["variant_states"]["candidates"] == records
        assert stats["variant_states"]["no_match"] == size - records
        assert stats["verified_records"] == 0
        assert (
            stats["records_with_candidates"] + stats["records_without_candidate"]
            == records
        )
    assert duration < 20
    print(
        f"Synthetic benchmark: {size} variants, 2844 ML rows, 550 TN rows; {len(statements)} SELECTs; {duration:.3f}s"
    )


def test_duplicate_variant_ids_rejected_instead_of_double_counted(db):
    with pytest.raises(ValueError, match="repetido"):
        captures(db, [product(), product()], [ml()])


def test_queue_comparison_filters_equal_exclusive_totals(db):
    captures(db, [product(), product(2, "OTHER", name="Lentejas")], [ml()], [])
    queue = build_queue(db, sort="capture")
    for channel in ["ml", "tn"]:
        for state in [
            "verified",
            "candidates",
            "conflicts",
            "no_match",
            "insufficient",
            "stale",
        ]:
            name = f"{channel}_comparison_{state}"
            result = build_queue(db, sort="capture", filter_name=name)
            assert (
                result["total"]
                == queue["channel_coverage"]["summary"]["comparison"][channel][
                    "variant_states"
                ][state]
            )


def test_manual_approval_history_preserved_after_new_matching_and_source_change(db):
    from app.services.ecomm_api_channel_evidence import PROFILE
    from sqlalchemy import select

    products = [product()]
    matrix = captures(db, products, [ml()])
    item = matrix["items_by_id"]["1"]
    candidate = item["ml"]["candidates"][0]
    history = [{"decision": "APPROVED", "reason": "Explicit synthetic operator review"}]
    review = InventoryLinkageDecision(
        external_id="API_ML:MLA10001",
        ecomm_id="1",
        decision="APPROVED",
        source_snapshot={"profile": PROFILE, "fingerprint": candidate["token"]},
        product_snapshot=item["identity"],
        history=history,
    )
    db.add(review)
    db.commit()
    result = build_channel_coverage(db, pages(products), api_validation=True, now=NOW)
    assert result["items_by_id"]["1"]["ml"]["confirmed_listing"]
    assert result["summary"]["comparison"]["ml"]["variant_states"]["verified"] == 1
    snap = db.scalar(
        select(CatalogSnapshot).where(CatalogSnapshot.source == "MERCADOLIBRE_API")
    )
    snap.payload = [ml(sku="DIFFERENT", title="Contenido cambiado 500 g")]
    db.commit()
    result = build_channel_coverage(db, pages(products), api_validation=True, now=NOW)
    candidate = result["items_by_id"]["1"]["ml"]["candidates"][0]
    assert candidate["match_reasons"] == ["PREVIOUS_MANUAL_REVIEW"]
    assert not candidate["identity_verified"] and not candidate["review_current"]
    assert candidate["history"] == history
    assert review.history == history and review.decision == "APPROVED"


def test_listing_without_master_does_not_claim_absence_of_candidates(db):
    from sqlalchemy import delete

    captures(db, [product()], [ml()])
    db.execute(
        delete(CatalogSnapshot).where(CatalogSnapshot.source == "ECOMM_APP_API_STAGE")
    )
    db.commit()
    result = listings(db, "ml")
    assert not result["master_available"]
    assert result["items"][0]["evidence_state"] == "INSUFFICIENT_EVIDENCE"
    assert result["items"][0]["candidate_ecomm_ids"] == []


def test_3201_shared_titles_do_not_expand_exact_code_candidates_quadratically(db):
    size = 3201
    # Same commercial title/brand/size does not merge distinct variant codes.
    products = [product(i + 1, f"SYNTH-{i}") for i in range(size)]
    rows = [ml(f"MLA{200000+i}", f"SYNTH-{i}") for i in range(size)]
    began = perf_counter()
    result = captures(db, products, rows, [])
    elapsed = perf_counter() - began
    stats = result["summary"]["comparison"]["ml"]
    assert stats["candidate_pairs"] == size
    assert stats["records_with_candidates"] == size
    assert stats["variant_states"]["candidates"] == size
    assert all(r["ml"]["candidates_total"] == 1 for r in result["items_by_id"].values())
    assert not any(r["ml"]["confirmed_listing"] for r in result["items_by_id"].values())
    assert elapsed < 20
    print(
        f"Synthetic shared-title benchmark: {size} variants; {size} candidate pairs; {elapsed:.3f}s"
    )
