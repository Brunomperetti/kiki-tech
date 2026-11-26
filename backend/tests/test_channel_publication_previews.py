import pytest

from app.services import mercadolibre_publication_preview as ml
from app.services import tiendanube_publication_preview as tn


def sample():
    return {
        "preview_fingerprint": "a" * 64,
        "items": [{
            "ecomm_id": "123",
            "sku": "ABC",
            "workspace_version": 2,
            "commercial_fields": {"title": "Test", "description": "Description", "brand": "Brand"},
            "blockers": ["Falta evidencia aprobada."],
            "channel_taxonomy": {"state": "DRAFT"},
            "source_is_combo": False,
            "source_parent_is_combo": False,
        }],
    }


def test_ml_preview_keeps_local_and_official_checks_separate(monkeypatch):
    monkeypatch.setattr(ml, "preview_commercial_export", lambda *args: sample())
    result = ml.local_preview(None, object(), "123")
    assert result["local_blockers"]
    assert "Falta evidencia aprobada." in result["local_blockers"]
    assert result["official_category_verified"] is False
    assert result["official_payload_validated"] is False
    assert result["external_writes_enabled"] is False
    assert result["provider_calls"] == 0


def test_tn_preview_never_claims_remote_verification(monkeypatch):
    monkeypatch.setattr(tn, "preview_commercial_export", lambda *args: sample())
    monkeypatch.setattr(tn, "sources", lambda db: {"123": {"sku": "ABC"}, "456": {"sku": "abc"}})
    result = tn.local_preview(None, object(), "123")
    assert "SKU Ecomm-App ausente o repetido." in result["local_blockers"]
    assert "Falta evidencia aprobada." in result["local_blockers"]
    assert result["payload_preview"]["visibility"] == "hidden"
    assert result["remote_duplicate_check"] == "NOT_RUN"
    assert result["external_writes_enabled"] is False
    assert result["provider_calls"] == 0


class FakeStore:
    def __init__(self, pages):
        self.pages = pages

    def list_products(self, *, page, per_page):
        return self.pages[page - 1]


def test_duplicate_scan_matches_exact_normalized_sku():
    store = FakeStore([[{"id": 1, "variants": [{"id": 2, "sku": " AbC "},
                                               {"id": 3, "sku": "ABCD"}]}]])
    assert tn.duplicate_candidates(store, "abc") == [{"product_id": 1, "variant_id": 2}]


def test_duplicate_scan_rejects_missing_variant_data():
    with pytest.raises(ValueError):
        tn.duplicate_candidates(FakeStore([[{"id": 1}]]), "ABC")


def test_duplicate_scan_rejects_incomplete_read():
    rows = [{"id": i + 1, "variants": [{"id": i + 1, "sku": "OTHER"}]} for i in range(100)]
    with pytest.raises(ValueError):
        tn.duplicate_candidates(FakeStore([rows]), "ABC", max_pages=1)
