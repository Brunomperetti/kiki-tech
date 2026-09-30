import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database.models import Base, EnrichmentReviewDecision
from app.services.enrichment_review_service import EnrichmentReviewService


def readiness_item(
    *,
    ecomm_id,
    sku,
    name,
    stock=5,
    brand=None,
    ean=None,
    status="REVIEW_REQUIRED",
):
    return {
        "product": {
            "ecomm_id": ecomm_id,
            "sku": sku,
            "name": name,
            "stock": stock,
            "price": 1000,
            "brand": brand,
            "ean": ean,
        },
        "readiness_status": status,
        "reason_codes": [],
    }


def report_with_internal_evidence():
    return {
        "reconciliation_run_id": 42,
        "items": [
            readiness_item(
                ecomm_id="KNOWN-1",
                sku="K1",
                name="Valeriana Natufarma 60 capsulas",
                brand="Natufarma",
                ean="7790000000001",
                status="ALREADY_PUBLISHED",
            ),
            readiness_item(
                ecomm_id="KNOWN-2",
                sku="K2",
                name="Valeriana Geonat 60 capsulas",
                brand="Geonat",
                ean="7790000000002",
                status="ALREADY_PUBLISHED",
            ),
            readiness_item(
                ecomm_id="10",
                sku="A10",
                name="Valeriana Sedante Natufarma X 40 Capsulas",
            ),
            readiness_item(
                ecomm_id="20",
                sku="A20",
                name="Combo Natufarma Geonat",
            ),
            readiness_item(
                ecomm_id="30",
                sku="A30",
                name="Nuez pecan x 100 grs",
            ),
        ],
    }


def service_with_report(db, report):
    service = EnrichmentReviewService(db)
    service.readiness.report = lambda: report
    return service


def test_review_queue_prioritizes_internal_signal_and_counts_no_evidence():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        queue = service_with_report(db, report_with_internal_evidence()).queue()

        assert queue["summary"]["queue_total"] == 2
        assert queue["summary"]["internal_brand_candidates"] == 1
        assert queue["summary"]["internal_ambiguous"] == 1
        assert queue["summary"]["without_internal_evidence"] == 1
        assert queue["summary"]["PENDING"] == 2
        assert queue["items"][0]["priority_code"] == "P1_HIGH"
        assert queue["items"][0]["internal_evidence"]["brand_candidate"] == "Natufarma"


def test_approved_proposal_is_persisted_without_external_write():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        service = service_with_report(db, report_with_internal_evidence())
        saved = service.save_decision("ECOMM:10", "APPROVED_PROPOSAL")

        assert saved["review_status"] == "APPROVED_PROPOSAL"
        assert saved["proposed_brand"] == "Natufarma"
        row = db.query(EnrichmentReviewDecision).one()
        assert row.product_key == "ECOMM:10"
        assert row.proposed_brand == "Natufarma"
        assert row.proposed_ean is None
        assert len(row.history) == 1

        queue = service.queue()
        reviewed = next(item for item in queue["items"] if item["product_key"] == "ECOMM:10")
        assert reviewed["review_status"] == "APPROVED_PROPOSAL"
        assert queue["summary"]["APPROVED_PROPOSAL"] == 1


def test_ambiguous_evidence_cannot_be_approved_as_unique_proposal():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        service = service_with_report(db, report_with_internal_evidence())
        with pytest.raises(ValueError, match="marca candidata única"):
            service.save_decision("ECOMM:20", "APPROVED_PROPOSAL")


def test_review_can_be_sent_external_and_reopened_with_history():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        service = service_with_report(db, report_with_internal_evidence())
        service.save_decision("ECOMM:20", "EXTERNAL_RESEARCH", "Pedir etiqueta")
        reopened = service.save_decision("ECOMM:20", "PENDING")

        row = db.query(EnrichmentReviewDecision).one()
        assert reopened["review_status"] == "PENDING"
        assert len(row.history) == 2


def test_product_key_prefers_ecomm_identity():
    key = EnrichmentReviewService.product_key(
        {"ecomm_id": "9450613", "sku": "6228", "ean": "7790000000001"}
    )
    assert key == "ECOMM:9450613"
