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
        original.version = 2
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
        "next_step": "NO_MANUFACTURER_DOCUMENT",
        "gaps": ["NO_MANUFACTURER_DOCUMENT"],
    }
    csv_text = export_delivery_csv([row])
    assert "'=HYPERLINK" in csv_text
    assert "'+evil" in csv_text
    assert "'@SUM" in csv_text
    assert tuple(CSV_HEADER)[0:3] == ("ecomm_id", "sku", "nombre_api")
