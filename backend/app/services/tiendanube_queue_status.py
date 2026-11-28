"""Internal triage from the last complete Tiendanube API capture.

No provider requests, external writes, or transfer of CSV identity approvals.
A stale capture never qualifies a SKU for the fresh no-match filter.
"""
from collections import Counter
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.database.models import CatalogSnapshot

FILTERS = {
    "tn_api_candidate",
    "tn_api_no_match",
    "tn_api_conflict",
    "tn_api_unavailable",
    "tn_api_stale",
}


class TiendanubeQueueStatus:
    def __init__(self, db, settings, *, now=None):
        self.enabled = settings.kiki_tiendanube_read_enabled
        self.captured_at = None
        self.fresh = False
        self.counts = None
        if not self.enabled:
            return
        record = db.scalar(
            select(CatalogSnapshot).where(CatalogSnapshot.source == "TIENDANUBE_API")
        )
        if not record or not isinstance(record.payload, list) or len(record.payload) != 1:
            return
        capture = record.payload[0]
        if not isinstance(capture, dict) or capture.get("store_id") != settings.tiendanube_store_id:
            return
        try:
            at = datetime.fromisoformat(capture["captured_at"])
            if at.tzinfo is None:
                return
            rows = capture["rows"]
            if not isinstance(rows, list) or any(
                not isinstance(row, dict) or not isinstance(row.get("sku"), str)
                or type(row.get("product_id")) is not int or row["product_id"] <= 0
                or type(row.get("variant_id")) is not int or row["variant_id"] <= 0
                for row in rows
            ):
                return
            if (
                len({r["variant_id"] for r in rows}) != len(rows)
                or type(capture.get("products")) is not int
                or len({r["product_id"] for r in rows}) != capture["products"]
            ):
                return
            age = (now or datetime.now(timezone.utc)) - at
        except (KeyError, ValueError, TypeError, OverflowError):
            return
        self.captured_at = at.isoformat()
        self.fresh = timedelta(0) <= age <= timedelta(hours=24)
        self.counts = Counter(row["sku"].strip().casefold() for row in rows)

    def classify(self, sku, owners):
        if not self.enabled:
            return None
        key = sku.strip().casefold() if isinstance(sku, str) else ""
        matches = self.counts[key] if self.counts is not None and key else 0
        if self.counts is None:
            state = "tn_api_unavailable"
        elif not self.fresh:
            state = "tn_api_stale"
        elif not key or owners[key] != 1 or matches > 1:
            state = "tn_api_conflict"
        elif matches == 1:
            state = "tn_api_candidate"
        else:
            state = "tn_api_no_match"
        return {
            "source": "TIENDANUBE_API",
            "state": state,
            "captured_at": self.captured_at,
            "matches": matches,
            "fresh": self.fresh,
            "identity_verified": False,
        }
