import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database.models import Base, EnrichmentExternalResearch
from app.services.enrichment_external_research_service import EnrichmentExternalResearchService


def readiness_report():
    return {
        "reconciliation_run_id": 77,
        "items": [
            {
                "product": {
                    "ecomm_id": "KNOWN",
                    "sku": "K1",
                    "name": "Valeriana Natufarma 60 capsulas",
                    "brand": "Natufarma",
                    "ean": "4006381333931",
                    "stock": 2,
                    "price": 1000,
                },
                "readiness_status": "ALREADY_PUBLISHED",
                "reason_codes": [],
            },
            {
                "product": {
                    "ecomm_id": "10",
                    "sku": "A10",
                    "name": "Valeriana Sedante Natufarma X 40 Capsulas",
                    "brand": None,
                    "ean": None,
                    "stock": 8,
                    "price": 8000,
                },
                "readiness_status": "REVIEW_REQUIRED",
                "reason_codes": [],
            },
        ],
    }


def service_with_report(db):
    service = EnrichmentExternalResearchService(db)
    service.review.readiness.report = readiness_report
    return service


def send_to_external(service):
    service.review.save_decision("ECOMM:10", "EXTERNAL_RESEARCH")


def test_external_queue_starts_with_selected_review_item():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        service = service_with_report(db)
        send_to_external(service)
        queue = service.queue()

        assert queue["summary"]["total"] == 1
        assert queue["summary"]["DRAFT"] == 1
        assert queue["items"][0]["product_key"] == "ECOMM:10"
        assert queue["items"][0]["research_status"] == "DRAFT"


def test_draft_persists_source_backed_fields():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        service = service_with_report(db)
        send_to_external(service)
        saved = service.save(
            "ECOMM:10",
            "DRAFT",
            proposed_brand="Natufarma",
            source_name="Fabricante",
            source_url="https://example.com/producto",
            confidence="HIGH",
            notes="Pendiente de validar presentación exacta.",
        )

        row = db.query(EnrichmentExternalResearch).one()
        assert saved["proposed_brand"] == "Natufarma"
        assert row.source_name == "Fabricante"
        assert row.confidence == "HIGH"
        assert len(row.history) == 1


def test_accepting_evidence_requires_source_and_valid_confidence():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        service = service_with_report(db)
        send_to_external(service)

        with pytest.raises(ValueError, match="fuente y URL"):
            service.save(
                "ECOMM:10",
                "EVIDENCE_ACCEPTED",
                proposed_brand="Natufarma",
                confidence="HIGH",
            )

        accepted = service.save(
            "ECOMM:10",
            "EVIDENCE_ACCEPTED",
            proposed_brand="Natufarma",
            proposed_ean="4006381333931",
            source_name="Fabricante",
            source_url="https://example.com/producto",
            confidence="HIGH",
        )
        assert accepted["research_status"] == "EVIDENCE_ACCEPTED"
        assert accepted["proposed_ean"] == "4006381333931"


def test_invalid_gtin_is_rejected_before_persisting():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        service = service_with_report(db)
        send_to_external(service)

        with pytest.raises(ValueError, match="dígito verificador"):
            service.save(
                "ECOMM:10",
                "READY_FOR_REVIEW",
                proposed_ean="4006381333932",
                source_name="Fuente",
                source_url="https://example.com/producto",
                confidence="MEDIUM",
            )


def test_external_research_requires_explicit_review_state():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        service = service_with_report(db)
        with pytest.raises(ValueError, match="Investigar afuera"):
            service.save("ECOMM:10", "DRAFT", proposed_brand="Natufarma")
