"""Taxonomy/SEO reconciliation is read-only and strictly evidence gated.

Use a disposable SQLite store for saved editorial categories. No provider
network, no AI, no product edits, no Ecomm/ML/TN publication.
"""
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database.models import EcommApiProductEdit
from app.services.documental.taxonomy_alignment import (
    align_taxonomy, reviewed_internal_pairs, seo_field_audit,
)
from app.services.documental.commercial_plan import summarize_inspections


def inspected(*, taxonomy=None, saved=None, seo=None, **overrides):
    return {
        "conflicts": False,
        "stale": False,
        "approved_taxonomy": taxonomy or [],
        "existing_taxonomy": saved or {
            "category": "", "subcategory": "", "status": "NOT_STARTED",
        },
        "existing_seo_fields": seo or [],
        "supported_proposal_fields": ["seo_title", "seo_description", "seo_keywords"],
        "fields_without_support": ["media"],
        "no_documentation": False, "sufficient_evidence": True,
        "eligible": True, "approved_fact_count": 4,
        "name": "Ejemplo", "presentation": "250 g",
        "reasons": [], "review_schedule": {"review_due": False},
        **overrides,
    }


def category_facts(cat="Semillas", sub="Mix de semillas"):
    return [
        {"field": "category", "value": cat, "evidence_id": "doc-cat"},
        {"field": "subcategory", "value": sub, "evidence_id": "doc-sub"},
    ]


def test_only_ready_for_channels_edits_form_internal_reference(tmp_path):
    engine = create_engine("sqlite+pysqlite:///" + str(tmp_path / "taxonomy.db"))
    EcommApiProductEdit.__table__.create(engine)
    rows = [
        ("101", "READY_FOR_CHANNELS", "Semillas", "Mix de semillas"),
        ("102", "READY_FOR_CHANNELS", " semillas ", " MIX de semillas "),
        ("103", "DRAFT", "Suplementos", "Vitaminas"),
        ("104", "READY_FOR_REVIEW", "Productos orgánicos", "Especial"),
        ("105", "READY_FOR_CHANNELS", "Alimentos", ""),
    ]
    with Session(engine) as db:
        for ident, status, category, subcategory in rows:
            db.add(EcommApiProductEdit(
                ecomm_id=ident, source_sku="S-" + ident, source_snapshot={},
                fields={"category": category, "subcategory": subcategory},
                status=status, version=1, history=[],
            ))
        db.commit()
        existing = db.scalars(select(EcommApiProductEdit)).all()
        before = [(row.id, row.version, row.status, dict(row.fields)) for row in existing]
        pairs = reviewed_internal_pairs(db)
        assert len(pairs) == 1
        assert pairs[("semillas", "mix de semillas")]["referenced_fiches"] == 2
        assert ("suplementos", "vitaminas") not in pairs
        assert ("alimentos", "") not in pairs
        report = align_taxonomy(
            inspected(taxonomy=category_facts("SEMILLAS", "Mix de semillas")), pairs
        )
        assert report["state"] == "EXACT_REVIEWED_PAIR"
        assert report["exact_internal_reference"] == {
            "category": "Semillas", "subcategory": "Mix de semillas",
        }
        assert report["source_evidence_ids"] == ["doc-cat", "doc-sub"]
        assert report["reference_fiches"] == 2
        assert report["mapping_saved"] is False
        assert report["operator_review_required"] is True
        assert report["external_category_ids"] is None
        after = [
            (row.id, row.version, row.status, dict(row.fields))
            for row in db.scalars(select(EcommApiProductEdit)).all()
        ]
        assert before == after


def test_missing_mapping_never_suggests_new_internal_category():
    vocabulary = {("semillas", "mix de semillas"): {
        "category": "Semillas", "subcategory": "Mix de semillas",
        "referenced_fiches": 2,
    }}
    report = align_taxonomy(
        inspected(taxonomy=category_facts("Suplementos", "Vitaminas")), vocabulary
    )
    assert report["state"] == "NEEDS_MAPPING"
    assert report["exact_internal_reference"] is None
    assert report["mapping_saved"] is False
    assert report["source_approved"] == {
        "category": "Suplementos", "subcategory": "Vitaminas",
    }


def test_draft_only_reference_is_not_a_verified_taxonomy():
    result = align_taxonomy(inspected(taxonomy=category_facts()), {})
    assert result["state"] == "NO_REVIEWED_PAIRS"
    assert result["exact_internal_reference"] is None


def test_partial_or_missing_approved_facts_cannot_suggest_taxonomy():
    pair = {("semillas", "mix de semillas"): {
        "category": "Semillas", "subcategory": "Mix de semillas",
        "referenced_fiches": 1,
    }}
    without = align_taxonomy(inspected(), pair)
    assert without["state"] == "NO_APPROVED_CATEGORY"
    partial = align_taxonomy(
        inspected(taxonomy=category_facts()[:1]), pair
    )
    assert partial["state"] == "NO_APPROVED_SUBCATEGORY"


def test_approved_source_conflict_blocks_even_when_one_variant_matches():
    records = category_facts() + [{
        "field": "category", "value": "Otra categoría",
        "evidence_id": "doc-conflict",
    }]
    row = align_taxonomy(inspected(taxonomy=records), {})
    assert row["state"] == "CONFLICTING_APPROVED_FACTS"
    assert row["source_approved"] == {"category": None, "subcategory": None}
    assert row["exact_internal_reference"] is None


def test_stale_or_conflicting_identity_blocks_taxonomy_and_seo():
    pair = {("semillas", "mix de semillas"): {
        "category": "Semillas", "subcategory": "Mix de semillas",
        "referenced_fiches": 1,
    }}
    for blocker in ({"stale": True}, {"conflicts": True}):
        row = inspected(taxonomy=category_facts(), **blocker)
        assert align_taxonomy(row, pair)["state"] == "BLOCKED_EVIDENCE"
        assert all(status == "REVALIDATE" for status in seo_field_audit(row).values())


def test_existing_edit_is_not_overwritten_or_mislabeled():
    same = inspected(
        taxonomy=category_facts(),
        saved={
            "category": "Semillas", "subcategory": "Mix de semillas",
            "status": "DRAFT",
        },
    )
    assert align_taxonomy(same, {})["state"] == "ALREADY_SAVED"
    assert align_taxonomy(same, {})["exact_internal_reference"] is None
    difference = inspected(
        taxonomy=category_facts(),
        saved={
            "category": "Alimentos", "subcategory": "Cereales",
            "status": "READY_FOR_CHANNELS",
        },
    )
    assert align_taxonomy(difference, {})["state"] == "SAVED_SOURCE_MISMATCH"


def test_seo_statuses_identify_saved_supported_and_missing():
    row = inspected(
        seo=["seo_title"],
        supported_proposal_fields=["seo_description"],
    )
    report = seo_field_audit(row)
    assert report == {
        "seo_title": "ALREADY_SAVED",
        "seo_description": "EVIDENCE_BACKED",
        "seo_keywords": "NEEDS_EVIDENCE",
    }


def test_commercial_summary_exposes_taxonomy_and_zero_writes():
    vocab = {("semillas", "mix de semillas"): {
        "category": "Semillas", "subcategory": "Mix de semillas",
        "referenced_fiches": 3,
    }}
    result = summarize_inspections([
        ("101", inspected(taxonomy=category_facts())),
        ("102", inspected(taxonomy=category_facts(
            "Suplementos", "Vitaminas"
        ))),
    ], vocab)
    assert result["total"] == 2
    assert result["reviewed_internal_pairs"] == 1
    assert result["taxonomy_reference"] == "KIKI_EDITORIAL_READY_FOR_CHANNELS_ONLY"
    assert result["taxonomy_counts"] == {
        "EXACT_REVIEWED_PAIR": 1,
        "NEEDS_MAPPING": 1,
    }
    assert result["items"][0]["taxonomy_alignment"]["operator_review_required"] is True
    assert result["provider_calls"] == 0
    assert result["automatic_publications"] == 0
    assert result["external_writes_enabled"] is False
    assert result["facts_approved"] == 0
