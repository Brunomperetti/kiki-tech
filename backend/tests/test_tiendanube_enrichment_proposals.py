from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database.models import Base
from app.services.tiendanube_enrichment_proposal_service import TiendanubeEnrichmentProposalService


def test_proposes_only_existing_brand_and_flags_missing_description():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        svc = TiendanubeEnrichmentProposalService(db)
        tn = [
            {"slug": "avena", "name": "Avena 500 g", "sku": "A1", "brand": "Granix",
             "category": "Alimentos", "description_present": False},
            {"slug": "arroz", "name": "Arroz Marca 1 kg", "sku": "A2", "brand": "Marca",
             "category": "Alimentos", "description_present": True},
        ]
        svc.catalog.repo.save_snapshot("TIENDANUBE", tn)
        r = svc.report()
        assert r["summary"]["proposals"] == 1
        p = r["items"][0]
        assert p["proposed_title"] == "Granix · Avena 500 g"
        assert p["description_action"] == "RESEARCH_REQUIRED"
        assert any(x["source"] == "Tiendanube CSV" for x in p["verified_product_facts"])
        assert svc.catalog.repo.snapshot("TIENDANUBE") == tn


def test_conflicting_variant_brands_never_generate_brand_title():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        svc = TiendanubeEnrichmentProposalService(db)
        svc.catalog.repo.save_snapshot("TIENDANUBE", [
            {"slug": "p", "name": "Jabon 100 g", "brand": "Marca1", "description_present": False},
            {"slug": "p", "name": "Jabon 100 g", "brand": "Marca2", "description_present": False},
        ])
        p = svc.report()["items"][0]
        assert p["title_changed"] is False
        assert p["description_action"] == "RESEARCH_REQUIRED"
