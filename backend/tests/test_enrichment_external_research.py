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


def test_product_without_internal_signal_can_be_researched_and_accepted():
    report = {
        "reconciliation_run_id": 88,
        "items": [
            {
                "product": {
                    "ecomm_id": "30",
                    "sku": "1002",
                    "name": "Cardo Mariano Suelta X 50 Grs",
                    "brand": None,
                    "ean": None,
                    "stock": 1,
                    "price": 1400,
                },
                "readiness_status": "REVIEW_REQUIRED",
                "reason_codes": ["EAN_MISSING", "BRAND_MISSING"],
            }
        ],
    }

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        service = EnrichmentExternalResearchService(db)
        service.review.readiness.report = lambda: report

        service.review.save_decision(
            "ECOMM:30",
            "EXTERNAL_RESEARCH",
            "Resolver datos centrales desde la cola guiada.",
        )
        saved = service.save(
            "ECOMM:30",
            "EVIDENCE_ACCEPTED",
            proposed_brand="Marca Verificada",
            proposed_ean="4006381333931",
            source_name="Ficha oficial",
            source_url="https://example.com/producto",
            confidence="MEDIUM",
        )

        assert saved["research_status"] == "EVIDENCE_ACCEPTED"
        assert saved["proposed_ean"] == "4006381333931"
        assert saved["proposed_brand"] == "Marca Verificada"


def test_gtin_not_applicable_requires_source_confidence_and_reason():
    report = {
        "reconciliation_run_id": 91,
        "items": [
            {
                "product": {
                    "ecomm_id": "30",
                    "sku": "1002",
                    "name": "Cardo Mariano Suelta X 50 Grs",
                    "brand": "Herboristeria",
                    "ean": None,
                    "stock": 1,
                    "price": 1400,
                },
                "readiness_status": "REVIEW_REQUIRED",
                "reason_codes": ["EAN_MISSING"],
            }
        ],
    }

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        service = EnrichmentExternalResearchService(db)
        service.review.readiness.report = lambda: report
        service.review.save_decision("ECOMM:30", "EXTERNAL_RESEARCH")

        with pytest.raises(ValueError, match="fuente y URL"):
            service.save(
                "ECOMM:30",
                "GTIN_NOT_APPLICABLE",
                confidence="HIGH",
                notes="Producto fraccionado.",
            )

        with pytest.raises(ValueError, match="Explicá por qué"):
            service.save(
                "ECOMM:30",
                "GTIN_NOT_APPLICABLE",
                source_name="Ficha del proveedor",
                source_url="https://example.com/cardo",
                confidence="HIGH",
            )

        saved = service.save(
            "ECOMM:30",
            "GTIN_NOT_APPLICABLE",
            proposed_brand="Herboristeria",
            source_name="Ficha del proveedor",
            source_url="https://example.com/cardo",
            confidence="MEDIUM",
            notes="Producto vendido suelto y fraccionado por peso; no tiene GTIN propio.",
        )

        assert saved["research_status"] == "GTIN_NOT_APPLICABLE"
        assert saved["proposed_ean"] is None
        assert service.queue()["summary"]["GTIN_NOT_APPLICABLE"] == 1


def test_gtin_not_applicable_rejects_a_proposed_gtin():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        service = service_with_report(db)
        send_to_external(service)

        with pytest.raises(ValueError, match="no ingreses un EAN"):
            service.save(
                "ECOMM:10",
                "GTIN_NOT_APPLICABLE",
                proposed_ean="4006381333931",
                source_name="Proveedor",
                source_url="https://example.com/producto",
                confidence="HIGH",
                notes="No aplica.",
            )


def test_bulk_gtin_not_applicable_persists_selected_products_in_one_action():
    report = {
        "reconciliation_run_id": 99,
        "items": [
            {
                "product": {
                    "ecomm_id": "30",
                    "sku": "1002",
                    "name": "Cardo Mariano Suelta X 50 Grs",
                    "brand": None,
                    "ean": None,
                    "stock": 1,
                    "price": 1400,
                },
                "readiness_status": "REVIEW_REQUIRED",
                "reason_codes": ["EAN_MISSING", "BRAND_MISSING"],
            },
            {
                "product": {
                    "ecomm_id": "31",
                    "sku": "1003",
                    "name": "Pulmonaria Suelta X 20 Grs",
                    "brand": None,
                    "ean": None,
                    "stock": 1,
                    "price": 531,
                },
                "readiness_status": "REVIEW_REQUIRED",
                "reason_codes": ["EAN_MISSING", "BRAND_MISSING"],
            },
        ],
    }

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        service = EnrichmentExternalResearchService(db)
        service.review.readiness.report = lambda: report

        result = service.bulk_mark_gtin_not_applicable(
            product_keys=["ECOMM:30", "ECOMM:31"],
            source_name="Catálogo del proveedor",
            source_url="https://example.com/catalogo",
            confidence="HIGH",
            notes="Productos comercializados sueltos y fraccionados por peso, sin GTIN propio.",
        )

        assert result["requested"] == 2
        assert result["processed"] == 2
        rows = db.query(EnrichmentExternalResearch).order_by(
            EnrichmentExternalResearch.product_key
        ).all()
        assert [row.product_key for row in rows] == ["ECOMM:30", "ECOMM:31"]
        assert all(row.status == "GTIN_NOT_APPLICABLE" for row in rows)
        assert all(row.source_name == "Catálogo del proveedor" for row in rows)
        assert all(row.history[-1]["bulk_action"] is True for row in rows)

        queue = service.queue()
        assert queue["summary"]["GTIN_NOT_APPLICABLE"] == 2


def test_bulk_gtin_not_applicable_requires_common_evidence():
    report = {
        "reconciliation_run_id": 100,
        "items": [
            {
                "product": {
                    "ecomm_id": "30",
                    "sku": "1002",
                    "name": "Cardo Mariano Suelta X 50 Grs",
                    "brand": None,
                    "ean": None,
                    "stock": 1,
                    "price": 1400,
                },
                "readiness_status": "REVIEW_REQUIRED",
                "reason_codes": ["EAN_MISSING"],
            }
        ],
    }

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        service = EnrichmentExternalResearchService(db)
        service.review.readiness.report = lambda: report

        with pytest.raises(ValueError, match="fuente y URL"):
            service.bulk_mark_gtin_not_applicable(
                product_keys=["ECOMM:30"],
                source_name="",
                source_url="",
                confidence="HIGH",
                notes="Producto suelto.",
            )

        assert db.query(EnrichmentExternalResearch).count() == 0
