"""A bounded history listing must not hide the global recovery owner."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from sqlalchemy.orm import Session

from app.services.documental.source_intake_queue import SourceIntakeQueue
from app.services.documental.source_intake_storage import SourceIntakeJob
from test_documental_resumable_source_intake import fixture, prepare_job


def test_interrupted_global_owner_remains_visible_beyond_twenty_newer_manifests(tmp_path):
    engine = fixture(tmp_path)
    with Session(engine) as db:
        queue, original = prepare_job(db)
        first = db.get(SourceIntakeJob, original["id"])
        oldest = datetime(2026, 1, 1, tzinfo=timezone.utc)
        first.created_at = oldest
        items = deepcopy(first.items)
        items[0].update(state="RUNNING", claim_until=oldest.isoformat(), claim_token="SYNTHETIC-LEASE")
        first.items = items
        db.commit()
        for index in range(22):
            _, created = prepare_job(db)
            db.get(SourceIntakeJob, created["id"]).created_at = oldest + timedelta(days=index + 1)
            db.commit()
    with Session(engine) as db:
        report = SourceIntakeQueue(db, SimpleNamespace(id=2), "").listing()
        assert len(report["items"]) == 20
        assert report["items"][0]["id"] == original["id"]
        assert report["items"][0]["recoverable_items"] == 1
        # A listing never starts, retries or recovers the job on its own.
        assert report["items"][0]["items"][0]["state"] == "RUNNING"
