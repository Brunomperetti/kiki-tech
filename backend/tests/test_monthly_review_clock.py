"""Monthly review signoffs must be auditable, not postponed by ordinary saves.

Pure schedule regression plus one disposable SQLite confirmation. No provider,
external network, AI calls or customer database.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import EcommApiProductEdit, CatalogSnapshot
import app.services.ecomm_api_product_workspace_service as module
from app.services.ecomm_api_product_workspace_service import (
    EcommApiProductWorkspace, blank_fields, review_schedule,
)
from test_ecomm_api_product_workspace import setup


NOW = datetime(2026, 11, 19, 15, 0, tzinfo=timezone.utc)


def event(days_before, *, action=None, previous="DRAFT", changes=None):
    row = {
        "at": (NOW - timedelta(days=days_before)).isoformat(),
        "previous_status": previous, "new_status": "READY_FOR_CHANNELS",
        "changes": changes or {},
    }
    if action:
        row["action"] = action
    return row


def edit(history, *, status="READY_FOR_CHANNELS"):
    return SimpleNamespace(status=status, history=history)


def test_monthly_clock_counts_confirmations_not_each_ready_save(monkeypatch):
    monkeypatch.setattr(module, "_now", lambda: NOW)
    first = event(35)
    saved = event(3, previous="READY_FOR_CHANNELS", changes={
        "seo_description": {"before": "old", "after": "new"},
    })
    reviewed = event(2, action="REVIEW_CONFIRMED", previous="READY_FOR_CHANNELS")
    schedule = review_schedule(edit([first, saved]))
    assert schedule["review_due"] is True
    assert schedule["review_reason"] == "CONTENT_CHANGED"
    assert schedule["changed_since_review"] is True
    assert schedule["last_review_at"] == first["at"]
    # Explicit confirmation after checking this modified content resets clock.
    schedule = review_schedule(edit([first, saved, reviewed]))
    assert schedule["review_due"] is False
    assert schedule["review_reason"] == "CURRENT"
    assert schedule["changed_since_review"] is False
    assert schedule["last_review_at"] == reviewed["at"]
    assert schedule["next_review_at"] == (NOW + timedelta(days=28)).isoformat()


def test_repeated_save_with_no_field_changes_does_not_extend_review(monkeypatch):
    monkeypatch.setattr(module, "_now", lambda: NOW)
    events = [
        event(29), event(1, previous="READY_FOR_CHANNELS", changes={}),
    ]
    schedule = review_schedule(edit(events))
    assert schedule["last_review_at"] == events[0]["at"]
    assert schedule["next_review_at"] == (NOW + timedelta(days=1)).isoformat()
    assert schedule["review_due"] is False
    assert schedule["review_reason"] == "CURRENT"


def test_overdue_missing_unusable_dates_and_not_ready_are_fail_closed(monkeypatch):
    monkeypatch.setattr(module, "_now", lambda: NOW)
    assert review_schedule(edit([event(31)]))["review_reason"] == "OVERDUE"
    assert review_schedule(edit([event(30)]))["review_due"] is True
    assert review_schedule(edit([{"at": "invalid", "new_status": "READY_FOR_CHANNELS"}]))["review_reason"] == "NO_SIGNOFF"
    assert review_schedule(edit([]))["review_due"] is True
    assert review_schedule(edit([event(60)], status="DRAFT"))["review_due"] is False
    assert review_schedule(None)["review_reason"] == "NOT_READY"


def test_confirm_review_persists_signoff_and_updates_due_clock(tmp_path, monkeypatch):
    engine = setup(tmp_path)
    monkeypatch.setattr(module, "_now", lambda: NOW)
    monkeypatch.setattr(
        "app.core.config.get_settings",
        lambda: SimpleNamespace(
            kiki_document_channel_guard_enabled=False,
            kiki_document_channel_guard_pilot_id="",
        ),
    )
    fields = blank_fields()
    for key in module.READY_REQUIRED:
        fields[key] = "Valor comercial revisado" if key != "presentation" else "250 g"
    fields["seo_keywords"] = "producto, 250 g"
    fields["attributes"] = [{"name": "Contenido", "value": "250 g"}]
    fields["media"] = [{"kind": "IMAGE", "url": "https://example.invalid/image.jpg",
                        "source_url": "https://example.invalid/rights", "alt": "Imagen"}]
    fields["sources"] = [{
        "kind": "FABRICANTE", "verified": True,
        "name": "Proveedor ficticio",
        "url": "https://example.invalid/producto",
        "note": "Revisión del original archivado declarada en esta prueba.",
    }]
    old = event(45)
    with Session(engine) as db:
        db.add(EcommApiProductEdit(
            ecomm_id="101", source_sku="2500", fields=fields,
            source_snapshot={}, status="READY_FOR_CHANNELS",
            version=3, history=[old],
        ))
        db.commit()

    with Session(engine) as db:
        service = EcommApiProductWorkspace(db)
        assert service.get("101")["review_schedule"]["review_due"] is True
        reviewed = service.confirm_monthly_review("101", 3)
        assert reviewed["status"] == "READY_FOR_CHANNELS"
        assert reviewed["version"] == 4
        assert reviewed["review_schedule"]["review_due"] is False
        assert reviewed["review_schedule"]["last_review_at"] == NOW.isoformat()
        assert reviewed["history"][-1]["action"] == "REVIEW_CONFIRMED"
        assert reviewed["external_writes_enabled"] is False
        with pytest.raises(ValueError, match="versión"):
            service.confirm_monthly_review("101", 3)
        assert db.scalar(select(CatalogSnapshot)).payload == (
            __import__("test_ecomm_api_product_workspace").capture()
        )

    with Session(engine) as db:
        reopened = EcommApiProductWorkspace(db).get("101")
        assert reopened["version"] == 4
        assert reopened["review_schedule"]["review_reason"] == "CURRENT"
        assert reopened["review_schedule"]["next_review_at"] == (
            NOW + timedelta(days=30)
        ).isoformat()
