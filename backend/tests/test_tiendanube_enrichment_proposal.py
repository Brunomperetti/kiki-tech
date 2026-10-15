from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.database.models import Base
from app.services.tiendanube_enrichment_proposal_service import TiendanubeEnrichmentProposalService


def test_evidence_only_proposals_preserve_catalog():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        rows = [
            {"slug": "avena", "sku": "A1", "name": "Avena 500 g",
             "brand": "Granix", "category": "Cereales", "description_present": False},
            {"slug": "jabon", "sku": "J1", "name": "Jabon Lirio 100 g",
             "brand": "Lirio", "category": "Higiene", "description_present": True},
        ]
        service = TiendanubeEnrichmentProposalService(db)
        service.catalog.repo.save_snapshot("TIENDANUBE", rows)
        report = service.report()
        assert report["available"] is True
        suggestion = next(x for x in report["items"] if x["product_key"] == "avena")
        assert suggestion["proposed_title"] == "Granix · Avena 500 g"
        assert suggestion["description_action"] == "RESEARCH_REQUIRED"
        assert suggestion["status"] == "DRAFT_REVIEW"
        assert all(f["source"] == "Tiendanube CSV" for f in suggestion["verified_product_facts"])
        assert service.catalog.repo.snapshot("TIENDANUBE") == rows


def test_no_source_data_is_no_proposals():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        report = TiendanubeEnrichmentProposalService(db).report()
        assert report["available"] is False
        assert report["items"] == []
