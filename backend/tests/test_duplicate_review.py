from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database.duplicate_review import DuplicateReviewDecision
from app.database.models import Base, ReconciliationRun
from app.services.duplicate_review_service import DuplicateReviewService
from app.services.publication_readiness_service import PublicationReadinessService


def duplicate_result(ecomm_id, sku, aliases, *, matched=0, listing_id=None):
    return {
        "product": {
            "ecomm_id": ecomm_id,
            "sku": sku,
            "sku_effective": sku,
            "sku_aliases": aliases,
            "ean": "7790000000001" if ecomm_id == "1" else "7790000000002",
            "brand": "Marca",
            "name": f"Producto {ecomm_id}",
            "stock": 10,
            "price": 1000,
        },
        "listing": {"external_id": listing_id, "sku": sku, "title": f"Producto {ecomm_id}"} if listing_id else None,
        "matched_listing_count": matched,
        "matched_listing_ids": [listing_id] if listing_id else [],
        "multiple_ml_listings": False,
        "status": "POSSIBLE_DUPLICATE",
        "confidence": 1,
        "reason": "El identificador está compartido por productos Ecomm distintos.",
        "match_method": "SKU" if matched else "NONE",
        "issues": [{"field": "sku", "severity": "ERROR", "code": "SKU_DUPLICATE", "message": "SKU duplicado"}],
    }


def add_run(db, *, matched=False):
    results = [
        duplicate_result("1", "2562000", ["2562000", "2562"], matched=1 if matched else 0, listing_id="MLA1" if matched else None),
        duplicate_result("2", "2562", ["2562"], matched=1 if matched else 0, listing_id="MLA2" if matched else None),
    ]
    run = ReconciliationRun(results=results, summary={"mercadolibre_source": "MERCADOLIBRE"})
    db.add(run)
    db.commit()
    return run


def test_duplicate_queue_groups_products_by_shared_alias_and_persists_history():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        add_run(db)
        service = DuplicateReviewService(db)
        queue = service.queue()
        assert queue["summary"]["groups_total"] == 1
        assert queue["summary"]["products_affected"] == 2
        group = queue["items"][0]
        assert "2562" in group["shared_identifiers"]

        saved = service.save_decision(group["group_key"], "VARIANTS", "Sabores distintos")
        assert saved["review_decision"] == "VARIANTS"
        row = db.query(DuplicateReviewDecision).one()
        assert len(row.history) == 1

        reopened = service.save_decision(group["group_key"], "PENDING")
        assert reopened["review_decision"] == "PENDING"
        assert len(db.query(DuplicateReviewDecision).one().history) == 2


def test_resolved_distinct_products_stop_duplicate_block_but_bulk_rule_still_applies():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        add_run(db)
        service = DuplicateReviewService(db)
        group = service.queue()["items"][0]
        service.save_decision(group["group_key"], "DISTINCT_PRODUCTS")

        report = PublicationReadinessService(db).report()
        assert report["summary"]["BLOCKED"] == 0
        assert report["summary"]["READY_CORE_DATA"] == 1
        assert report["summary"]["EXCLUDED_BULK"] == 1


def test_resolved_variants_keep_exact_ml_matches_as_published_but_confirmed_duplicate_stays_blocked():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        add_run(db, matched=True)
        service = DuplicateReviewService(db)
        group = service.queue()["items"][0]
        service.save_decision(group["group_key"], "VARIANTS")
        report = PublicationReadinessService(db).report()
        assert report["summary"]["ALREADY_PUBLISHED"] == 2

        service.save_decision(group["group_key"], "DUPLICATE_CONFIRMED")
        report = PublicationReadinessService(db).report()
        assert report["summary"]["BLOCKED"] == 2
