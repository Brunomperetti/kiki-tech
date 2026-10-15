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
        assert suggestion["proposed_title"] == "Avena 500 g · Granix"
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

def test_brand_redundancy_and_boundary_rules():
    from app.services.tiendanube_enrichment_proposal_service import (
        brand_already_present, suggested_product_title,
    )
    assert brand_already_present("Jabon Sri Sri Vegetal Jazmin 100g", "Sri Sri Tattva") is False
    assert brand_already_present("Jabon Sri Sri Tattva Vegetal 100g", "Sri Sri Tattva")
    assert brand_already_present("Cafe Éxito 250g", "Exito")
    assert not brand_already_present("Chocolate 250g", "Choco")
    assert suggested_product_title("Jabón Sri Sri Tattva 100g", "Sri Sri Tattva") == "Jabón Sri Sri Tattva 100g"
    assert suggested_product_title("Avena 500 g", "Granix") == "Avena 500 g · Granix"
    assert suggested_product_title("Jabón Sri Sri Vegetal 100g", "Sri Sri Tattva") == "Jabón Sri Sri Vegetal 100g"


def test_seo_fields_not_claimed_verified():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        service = TiendanubeEnrichmentProposalService(db)
        service.catalog.repo.save_snapshot("TIENDANUBE", [
            {"slug": "avena", "sku": "A", "name": "Avena 500 g", "brand": "Granix",
             "description_present": False},
        ])
        item = service.report()["items"][0]
        assert item["seo_title"] is None
        assert item["seo_status"] == "PENDING_RESEARCH"
