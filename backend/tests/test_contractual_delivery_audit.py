"""Contractual full-catalog audit: all API variants, no manual entry or AI.

All tests use a disposable SQLite database with a complete synthetic API
capture. Neither provider credentials nor supplier websites are touched.
"""
from datetime import datetime, timedelta, timezone
from copy import deepcopy
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import CatalogSnapshot, EcommApiProductEdit
from app.services.documental.storage import ResearchBase, Document, Dossier
from app.services.contractual_delivery_audit_service import (
    build_delivery_audit, export_delivery_csv, _gap_report, CSV_HEADER,
)
from app.services.ecomm_api_product_workspace_service import blank_fields, READY_REQUIRED
from test_ecomm_api_work_queue import db_fixture


def fixture(tmp_path):
    engine = db_fixture(tmp_path)
    ResearchBase.metadata.create_all(engine)
    return engine


def test_catalogue_audit_is_complete_and_read_only(tmp_path):
    engine = fixture(tmp_path)
    with Session(engine) as db:
        saved = db.scalar(select(CatalogSnapshot).where(
            CatalogSnapshot.source == "ECOMM_APP_API_STAGE"
        ))
        capture_before = deepcopy(saved.payload)
        summary, rows = build_delivery_audit(db)
        assert summary["mode"] == "READ_ONLY_CONTRACTUAL_CATALOG_AUDIT"
        assert summary["source"] == "ECOMM_APP_API_STAGE"
        assert summary["total"] == len(rows) == 2
        assert len({row["ecomm_id"] for row in rows}) == 2
        assert summary["internal_fiches_complete"] == 0
        assert summary["fields_complete"] == 0
        assert summary["classified_variants"] == summary["total"] == 2
        assert sum(summary["quality_stage_counts"].values()) == 2
        assert summary["quality_stage_counts"]["FIND_ORIGINAL"] == 2
        assert summary["channel_certified_by_this_audit"] == 0
        assert all(row["quality_stage"] == "FIND_ORIGINAL" for row in rows)
        assert summary["gap_counts"]["NO_MANUFACTURER_DOCUMENT"] == 2
        assert summary["gap_counts"]["NO_CURRENT_APPROVED_FACTS"] == 2
        assert summary["gap_counts"]["INCOMPLETE_COMMERCIAL_FICHE"] == 2
        assert summary["gap_counts"]["SEO_MISSING"] == 2
        assert summary["gap_counts"]["IMAGE_MISSING"] == 2
        assert summary["gap_counts"]["VIDEO_NOT_DOCUMENTED"] == 2
        assert summary["external_writes_enabled"] is False
        assert summary["network_requests"] == summary["ai_requests"] == 0
        assert summary["monthly_review_confirmed"] is False
        assert all(x["delivery_certified"] is False for x in rows)
        csv_text = export_delivery_csv(rows)
        assert csv_text.startswith("\ufeff")
        assert "ecomm_id,sku,nombre_api" in csv_text
        assert csv_text.count("\n") == 3
        assert db.scalar(select(CatalogSnapshot).where(
            CatalogSnapshot.source == "ECOMM_APP_API_STAGE"
        )).payload == capture_before
        assert db.scalars(select(EcommApiProductEdit)).all() == []
        assert db.scalars(select(Document)).all() == []


def test_reviewed_real_original_with_matching_hash_counts_only_approved_facts(tmp_path):
    engine = fixture(tmp_path)
    doc_id = "local-" + "f" * 32
    with Session(engine) as db:
        body = {
            "associated_ecomm_id": "101",
            "origin_kind": "FILE",
            "parse_status": "TEXT_EXTRACTED",
            "synthetic": False,
            "original": {"sha256": "a" * 64},
            "source": {"review_state": "REVIEWED"},
        }
        db.add(Document(
            id=doc_id, version=1, digest="b" * 64, body=body, history=[],
        ))
        db.add(Dossier(
            ecomm_id="101", version=2, identity={}, identity_digest="c" * 64,
            history=[], facts=[{
                "id": "fact-1", "state": "APPROVED", "document_id": doc_id,
                "document_version": 1, "document_hash": "b" * 64,
            }, {
                "id": "fact-mismatched", "state": "APPROVED", "document_id": doc_id,
                "document_version": 2, "document_hash": "b" * 64,
            }],
        ))
        db.commit()
        summary, rows = build_delivery_audit(db)
        by_id = {r["ecomm_id"]: r for r in rows}
        assert by_id["101"]["reviewed_source_documents"] == 1
        assert by_id["101"]["approved_facts_with_current_original"] == 1
        assert "NO_MANUFACTURER_DOCUMENT" not in by_id["101"]["gaps"]
        assert "NO_CURRENT_APPROVED_FACTS" not in by_id["101"]["gaps"]
        assert by_id["102"]["approved_facts_with_current_original"] == 0
        assert summary["approved_claims_in_current_originals"] == 1
        # If a source changes or loses review, an old approval cannot pass.
        original = db.get(Document, doc_id)
        original.version = 3  # Neither fact-1 (v1) nor fact-mismatched (v2).
        db.commit()
        result, _ = build_delivery_audit(db)
        assert result["approved_claims_in_current_originals"] == 0


def test_channel_ready_is_not_certified_without_documentary_gate(tmp_path):
    engine = fixture(tmp_path)
    fields = blank_fields()
    for key in READY_REQUIRED:
        fields[key] = "Texto aprobado por operador"
    fields["attributes"] = [{"name": "Material", "value": "Dato de ejemplo"}]
    fields["media"] = [{"kind": "IMAGE", "url": "https://example.invalid/image.jpg",
                        "source_url": "https://example.invalid/rights"}]
    fields["sources"] = [{"kind": "FABRICANTE", "verified": True,
                           "name": "Fabricante", "url": "https://example.invalid/page",
                           "note": "Revisión interna de catálogo de ejemplo"}]
    fields["seo_keywords"] = "dato ejemplo"
    with Session(engine) as db:
        db.add(EcommApiProductEdit(
            ecomm_id="101", source_sku="2500", source_snapshot={},
            fields=fields, status="READY_FOR_CHANNELS", version=1, history=[],
        ))
        db.commit()
        summary, rows = build_delivery_audit(db)
        record = next(row for row in rows if row["ecomm_id"] == "101")
        assert record["internal_fiche_complete"] is True
        assert record["delivery_certified"] is False
        assert "READY_WITHOUT_VERIFIED_DOCUMENTAL_GATE" in record["gaps"]
        assert "MEDIA_RIGHTS_NOT_VERIFIED" in record["gaps"]
        assert "VIDEO_NOT_DOCUMENTED" in record["gaps"]
        assert summary["internal_fiches_complete"] == 1
        assert summary["fields_complete"] == 1
        assert record["fields_complete"] is True
        assert record["fields_percent"] == 100
        assert record["quality_stage"] == "FIND_ORIGINAL"
        assert summary["channel_certified_by_this_audit"] == 0


def test_monthly_review_is_reported_and_never_marked_confirmed():
    ago = (datetime.now(timezone.utc) - timedelta(days=45)).isoformat()
    fields = blank_fields()
    for key in READY_REQUIRED:
        fields[key] = "Dato"
    fields["attributes"] = [{"name": "A", "value": "B"}]
    fields["media"] = [{"kind": "IMAGE"}]
    fields["sources"] = [{"kind": "FABRICANTE", "verified": True}]
    fields["seo_keywords"] = "dato"
    edit = SimpleNamespace(
        source_sku="SKU-1", status="READY_FOR_CHANNELS",
        fields=fields,
        history=[{"new_status": "READY_FOR_CHANNELS", "at": ago}],
    )
    row = {
        "ecomm_id": "101", "sku": "SKU-1", "product_name": "Demo",
        "identity_issue": False, "flags": ["research_gtin_unique"],
        "source": {"variant_description": "1 kg", "barcode": "7791234567890"},
        "captured_at": ago,
    }
    result = _gap_report(row, edit, [], {}, 0)
    assert result["monthly_review_due"] is True
    assert result["next_step"] == "NO_MANUFACTURER_DOCUMENT"
    assert "MONTHLY_REVIEW_DUE" in result["gaps"]


def test_export_escapes_spreadsheet_formula_in_untrusted_api_name():
    row = {
        "ecomm_id": "101", "sku": "+evil", "name": "=HYPERLINK(1)",
        "presentation": "@SUM(1)", "api_barcode": "7791234567890",
        "captured_at": "2026-11-18", "editorial_status": "DRAFT",
        "documents": 0, "reviewed_source_documents": 0,
        "approved_facts_with_current_original": 0,
        "internal_fiche_complete": False, "image_present": False,
        "video_present": False, "monthly_review_due": False,
        "last_review_at": None, "next_review_at": None,
        "review_reason": "NOT_READY",
        "next_step": "NO_MANUFACTURER_DOCUMENT",
        "gaps": ["NO_MANUFACTURER_DOCUMENT"],
    }
    csv_text = export_delivery_csv([row])
    assert "'=HYPERLINK" in csv_text
    assert "'+evil" in csv_text
    assert "'@SUM" in csv_text
    assert tuple(CSV_HEADER)[0:3] == ("ecomm_id", "sku", "nombre_api")


def test_complete_draft_counts_fields_without_certifying_evidence_or_channels(tmp_path):
    """Natural Seed's 100% editor score must not be 100% commercially ready."""
    engine = fixture(tmp_path)
    fields = blank_fields()
    for key in READY_REQUIRED:
        fields[key] = "Valor comercial no acreditado"
    fields["attributes"] = [{"name": "Formato", "value": "250 g"}]
    fields["media"] = [{"kind": "IMAGE", "url": "https://example.invalid/a.jpg"}]
    fields["sources"] = [{
        "kind": "FABRICANTE", "verified": True, "name": "Ejemplo",
        "url": "https://example.invalid/item",
        "note": "Declaración manual, no certificado",
    }]
    fields["seo_keywords"] = "mezcla, 250 g"
    with Session(engine) as db:
        db.add(EcommApiProductEdit(
            ecomm_id="101", source_sku="2500", source_snapshot={},
            fields=fields, status="DRAFT", version=5, history=[],
        ))
        db.commit()
        report, rows = build_delivery_audit(db)
        draft = next(r for r in rows if r["ecomm_id"] == "101")
        assert draft["fields_complete"] is True
        assert draft["fields_percent"] == 100
        assert draft["internal_fiche_complete"] is False
        assert draft["delivery_certified"] is False
        assert draft["channel_certified"] is False
        assert draft["quality_stage"] == "FIND_ORIGINAL"
        assert "INCOMPLETE_COMMERCIAL_FICHE" not in draft["gaps"]
        assert report["fields_complete"] == 1
        assert report["internal_fiches_complete"] == 0
        assert report["classified_variants"] == report["total"] == 2
        assert report["channel_certified_by_this_audit"] == 0
        text = export_delivery_csv(rows)
        assert "campos_completos_sin_certificar" in text
        assert "porcentaje_campos" in text
        assert "etapa_siguiente" in text
        assert "FIND_ORIGINAL" in text


def test_exclusive_triage_stays_in_fact_review_without_approved_name_and_size():
    source = {
        "ecomm_id": "101", "sku": "SKU-1", "product_name": "Demo",
        "identity_issue": False, "flags": ["research_gtin_unique"],
        "source": {"variant_description": "250 g", "barcode": "7791234567890"},
        "captured_at": "2026-11-19",
    }
    doc = {"id": (1, "digest", "101", "REVIEWED", True)}
    # An approved characteristic alone is not a verified product identity.
    result = _gap_report(source, None, ["id"], doc, 1, {"characteristics"})
    assert result["quality_stage"] == "REVIEW_FACTS"
    assert result["approved_identity_fact_count"] == 0
    assert result["delivery_certified"] is False
    result2 = _gap_report(
        source, None, ["id"], doc, 3,
        {"product_name", "presentation", "characteristics"},
    )
    assert result2["quality_stage"] == "REVIEW_TAXONOMY"
    assert result2["approved_identity_fact_count"] == 2


def test_identity_conflict_takes_priority_over_approved_facts_or_fields():
    row = {
        "ecomm_id": "101", "sku": "SKU-1", "product_name": "Demo",
        "identity_issue": True, "flags": ["research_gtin_unique"],
        "source": {"variant_description": "250 g", "barcode": "7791234567890"},
        "captured_at": "2026-11-19",
    }
    result = _gap_report(row, None, [], {}, 0)
    assert result["quality_stage"] == "REVIEW_IDENTITY"
    assert result["delivery_certified"] is False


def test_csv_groups_by_next_action_before_sku_and_never_changes_data():
    common = {
        "name": "Producto", "presentation": "250 g",
        "api_barcode": "7791234567890", "captured_at": "2026-11-20",
        "editorial_status": "DRAFT", "documents": 0,
        "reviewed_source_documents": 0,
        "approved_facts_with_current_original": 0,
        "internal_fiche_complete": False, "fields_complete": False,
        "fields_percent": 0, "image_present": False,
        "video_present": False, "monthly_review_due": False,
        "last_review_at": None, "next_review_at": None,
        "review_reason": "NOT_READY", "next_step": "NO_MANUFACTURER_DOCUMENT",
        "gaps": ["NO_MANUFACTURER_DOCUMENT"],
    }
    needs_source = {
        **common, "ecomm_id": "101", "sku": "AAA",
        "quality_stage": "FIND_ORIGINAL",
    }
    identity_exception = {
        **common, "ecomm_id": "102", "sku": "ZZZ",
        "quality_stage": "REVIEW_IDENTITY",
    }
    taxonomy = {
        **common, "ecomm_id": "103", "sku": "ZZY",
        "quality_stage": "REVIEW_TAXONOMY",
    }
    seo = {
        **common, "ecomm_id": "104", "sku": "BBB",
        "quality_stage": "REVIEW_SEO",
    }
    editorial = {
        **common, "ecomm_id": "105", "sku": "AAB",
        "quality_stage": "COMPLETE_FIELDS",
    }
    # Deliberately choose SKU order that differs from workflow order.
    result = export_delivery_csv([
        editorial, needs_source, seo, identity_exception, taxonomy,
    ])
    lines = result.lstrip("\ufeff").splitlines()
    assert lines[1].startswith("102,ZZZ")
    assert lines[2].startswith("101,AAA")
    assert lines[3].startswith("103,ZZY")
    assert lines[4].startswith("104,BBB")
    assert lines[5].startswith("105,AAB")
    assert needs_source["quality_stage"] == "FIND_ORIGINAL"
    assert identity_exception["quality_stage"] == "REVIEW_IDENTITY"


def test_image_only_gap_is_separate_batch_not_generic_editorial_completion():
    fields = blank_fields()
    for key in READY_REQUIRED:
        fields[key] = "Campo de ejemplo"
    fields["attributes"] = [{"name": "Formato", "value": "250 g"}]
    fields["sources"] = [{"kind": "FABRICANTE", "verified": True}]
    fields["seo_keywords"] = "producto, 250 g"
    source = {
        "ecomm_id": "101", "sku": "2500", "product_name": "Demo",
        "identity_issue": False, "flags": ["research_gtin_unique"],
        "source": {"variant_description": "250 g", "barcode": "7791234567890"},
        "captured_at": "2026-11-19",
    }
    edit = SimpleNamespace(
        source_sku="2500", status="DRAFT", fields=fields, history=[],
    )
    doc = {"doc1": (1, "hash", "101", "REVIEWED", True)}
    result = _gap_report(
        source, edit, ["doc1"], doc, 2, {"product_name", "presentation"},
    )
    assert result["quality_stage"] == "ADD_IMAGE"
    assert result["fields_complete"] is False
    assert "IMAGE_MISSING" in result["gaps"]
    assert "INCOMPLETE_COMMERCIAL_FICHE" in result["gaps"]
    assert result["delivery_certified"] is False
