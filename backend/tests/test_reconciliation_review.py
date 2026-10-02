from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database.models import Base, ReconciliationRun
from app.database.reconciliation_review import ReconciliationReviewDecision
from app.services.publication_readiness_service import PublicationReadinessService
from app.services.reconciliation_review_service import ReconciliationReviewService


def review_result():
    return {
        "product": {
            "ecomm_id": "100",
            "sku": "ABC100",
            "ean": "7791234567890",
            "brand": "Marca Test",
            "name": "Omega 3 Marca Test 60 Capsulas",
            "stock": 20,
            "price": 10000,
        },
        "listing": {
            "external_id": "MLA123",
            "sku": "ML-ABC100",
            "title": "Omega 3 Marca Test x 60 Capsulas",
            "status": "active",
        },
        "matched_listing_count": 1,
        "matched_listing_ids": ["MLA123"],
        "multiple_ml_listings": False,
        "status": "REVIEW_REQUIRED",
        "confidence": 0.91,
        "reason": "Coincidencia aproximada por título; requiere confirmación humana.",
        "match_method": "TITLE",
        "matched_identifier": None,
        "issues": [],
    }


def make_run(db):
    run = ReconciliationRun(
        results=[review_result()],
        summary={"mercadolibre_source": "MERCADOLIBRE", "total_products": 1},
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def test_review_queue_starts_pending_and_persists_confirmed_match():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        make_run(db)
        service = ReconciliationReviewService(db)

        queue = service.queue()
        assert queue["summary"]["PENDING"] == 1
        assert queue["items"][0]["product_key"] == "ECOMM:100"

        saved = service.save_decision("ECOMM:100", "CONFIRMED_MATCH", "Misma presentación")
        assert saved["review_decision"] == "CONFIRMED_MATCH"

        row = db.query(ReconciliationReviewDecision).one()
        assert row.decision == "CONFIRMED_MATCH"
        assert row.matched_listing_ids == ["MLA123"]
        assert len(row.history) == 1

        queue = service.queue()
        assert queue["summary"]["CONFIRMED_MATCH"] == 1
        assert queue["summary"]["PENDING"] == 0


def test_confirmed_match_moves_readiness_to_already_published():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        make_run(db)
        ReconciliationReviewService(db).save_decision("ECOMM:100", "CONFIRMED_MATCH")

        report = PublicationReadinessService(db).report()
        assert report["summary"]["ALREADY_PUBLISHED"] == 1
        assert report["summary"]["REVIEW_REQUIRED"] == 0
        assert report["items"][0]["manual_reconciliation_decision"] == "CONFIRMED_MATCH"
        assert report["items"][0]["original_reconciliation_status"] == "REVIEW_REQUIRED"


def test_not_match_turns_review_case_into_candidate_and_can_be_reopened():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        make_run(db)
        service = ReconciliationReviewService(db)
        service.save_decision("ECOMM:100", "NOT_MATCH", "La presentación no coincide")

        report = PublicationReadinessService(db).report()
        assert report["summary"]["READY_CORE_DATA"] == 1
        assert report["summary"]["REVIEW_REQUIRED"] == 0
        assert report["items"][0]["reconciliation_status"] == "CANDIDATE_TO_PUBLISH"

        reopened = service.save_decision("ECOMM:100", "PENDING")
        assert reopened["review_decision"] == "PENDING"
        row = db.query(ReconciliationReviewDecision).one()
        assert len(row.history) == 2

        report = PublicationReadinessService(db).report()
        assert report["summary"]["REVIEW_REQUIRED"] == 1
