"""Saved manual editor -> existing ledger -> provider double. No documents/AI."""
from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import CatalogSnapshot, ImportJobRecord
from app.services.ecomm_api_product_workspace_service import EcommApiProductWorkspace
from app.services import tiendanube_controlled_submission as service
from test_ecomm_api_product_workspace import setup
from test_tiendanube_controlled_submission import settings, USER


@pytest.fixture
def case(tmp_path):
    engine = setup(tmp_path)
    with Session(engine) as db:
        row = db.scalar(select(CatalogSnapshot))
        pages = deepcopy(row.payload)
        pages[0]["items"][0]["is_combo"] = False
        pages[0]["items"][0]["variants"][0]["barcode"] = "7794940000796"
        row.payload = pages
        db.commit()
        EcommApiProductWorkspace(db).save("101", {
            "title": "Magnesio con Potasio 30 cápsulas", "brand": "Marca revisada",
            "description": "Texto manual <script>no ejecutar</script>",
            "seo_title": "Título SEO revisado"}, "DRAFT", 0, session=USER)
    yield engine
    engine.dispose()


def prepare(db):
    return service.prepare_submission(db, USER, settings(), request_key=str(uuid4()),
        ecomm_id="101", operation="CREATE_HIDDEN", review_mode="MANUAL",
        identity_checks=sorted(service.CHECKS), reason="Datos revisados manualmente contra esta variante individual.")


def send(db, draft, transport):
    return service.send_submission(db, USER, settings(True), draft["id"],
        expected_revision=draft["revision"], expected_preview_fingerprint=draft["preview_fingerprint"],
        confirm=True, transport=transport)


def provider(calls, rows=None, error=None):
    def transport(method, url, **kw):
        calls.append((method, kw.get("payload")))
        if method == "GET":
            return rows or [], str(len(rows or []))
        if error:
            raise error
        assert method == "POST" and kw["payload"]["published"] is False
        assert "stock" not in str(kw["payload"]) and "price" not in kw["payload"]
        return {"id": 876, "published": False, "variants": [{"id": 8761, "sku": "2500"}]}
    return transport


def test_saved_draft_without_documentation_hidden_creation_reload_and_no_repeat(case):
    calls = []
    with Session(case) as db:
        before = EcommApiProductWorkspace(db).get("101")
        item = prepare(db)
        assert item["state"] == "PREVIEW" and not item["blockers"]
        assert item["payload_preview"]["variants"] == [{"sku": "2500", "barcode": "7794940000796"}]
        assert "&lt;script&gt;" in item["payload_preview"]["description"]["es"]
        assert item["payload_preview"]["seo_title"] == {"es": "Título SEO revisado"}
        result = send(db, item, provider(calls))
        assert result["state"] == "SUCCEEDED" and result["target_product_id"] == "876"
        assert result["product_admin_url"].endswith("/876")
        assert EcommApiProductWorkspace(db).get("101") == before
        assert len(calls) == 2
    with Session(case) as db:
        assert service.get_submission(db, item["id"])["state"] == "SUCCEEDED"
        assert send(db, item, provider(calls))["state"] == "SUCCEEDED"
        assert len(calls) == 2


def test_optional_description_seo_categories_evidence_not_required(case):
    with Session(case) as db:
        EcommApiProductWorkspace(db).save("101", {"title": "Magnesio con Potasio 30 cápsulas"}, "DRAFT", 1, session=USER)
        item = prepare(db)
        assert item["state"] == "PREVIEW"
        assert set(item["payload_preview"]) == {"name", "published", "variants"}


@pytest.mark.parametrize("change", ["duplicate_sku", "duplicate_ean", "invalid_gtin", "code_conflict", "combo", "sku_changed"])
def test_identity_blockers_cannot_be_bypassed_by_manual_attestation(case, change):
    with Session(case) as db:
        row = db.scalar(select(CatalogSnapshot))
        pages = deepcopy(row.payload)
        first, second = [p["variants"][0] for p in pages[0]["items"]]
        if change == "duplicate_sku":
            second["sku"] = first["sku"]
        elif change == "duplicate_ean":
            second["gtin"] = first["barcode"]
        elif change == "invalid_gtin":
            first["barcode"] = "1234567890123"
        elif change == "code_conflict":
            first["gtin"] = "7730114100015"
        elif change == "combo":
            first["is_combo"] = True
        else:
            first["sku"] = "changed"
        row.payload = pages
        db.commit()
        item = prepare(db)
        assert item["state"] == "BLOCKED" and item["blockers"]


@pytest.mark.parametrize("reason", ["same_sku", "same_ean", "same_name", "incomplete"])
def test_live_duplicate_or_incomplete_identity_blocks_before_post(case, reason):
    calls = []
    row = {"id": 98, "name": {"es": "Otro producto"}, "variants": [{"id": 981, "sku": "other"}]}
    if reason == "same_sku":
        row["variants"][0]["sku"] = "2500"
    elif reason == "same_ean":
        row["variants"][0]["barcode"] = "7794940000796"
    elif reason == "same_name":
        row["name"]["es"] = "Magnesio con Potasio 30 cápsulas"
    else:
        row["name"]["es"] = ""
        row["variants"][0]["sku"] = ""
    with Session(case) as db:
        result = send(db, prepare(db), provider(calls, [row]))
        assert result["state"] == "BLOCKED"
        assert [c[0] for c in calls] == ["GET"]


def test_timeout_is_unknown_and_never_retried(case):
    calls = []
    with Session(case) as db:
        item = prepare(db)
        assert send(db, item, provider(calls, error=TimeoutError("private")))["state"] == "UNKNOWN"
        assert send(db, item, provider(calls))["state"] == "UNKNOWN"
        assert len(calls) == 2
        assert "private" not in str(db.scalar(select(ImportJobRecord)).diagnostics)


def test_saved_editor_change_during_live_preflight_blocks_post(case):
    calls = []
    def changed(method, url, **kw):
        calls.append(method)
        with Session(case) as other:
            EcommApiProductWorkspace(other).save("101", {"title": "Nombre nuevo"}, "DRAFT", 1, session=USER)
        return [], "0"
    with Session(case) as db:
        result = send(db, prepare(db), changed)
        assert result["state"] == "BLOCKED" and result["error_code"] == "LOCAL_EVIDENCE_CHANGED"
        assert calls == ["GET"]


def test_stale_cached_capture_does_not_require_a_separate_refresh(case):
    with Session(case) as db:
        db.add(CatalogSnapshot(source="TIENDANUBE_API", payload=[{"store_id": "123", "rows": [],
            "captured_at": datetime(2020, 1, 1, tzinfo=timezone.utc).isoformat()}]))
        db.commit()
        calls = []
        result = send(db, prepare(db), provider(calls))
        assert result["state"] == "SUCCEEDED" and calls[0][0] == "GET"


@pytest.mark.parametrize("code", [401, 403, 422, 429])
def test_definitive_provider_rejection_reports_status_without_exposing_body(case, code):
    from app.integrations.tiendanube.client import TiendanubeError
    calls = []
    with Session(case) as db:
        result = send(db, prepare(db), provider(calls, error=TiendanubeError(code)))
        assert result["state"] == "FAILED" and result["error_code"] == f"PROVIDER_HTTP_{code}"
        assert [call[0] for call in calls] == ["GET", "POST"]


@pytest.mark.parametrize("change", ["published", "extra_field", "missing_name", "two_variants"])
def test_manual_client_allowlist_rejects_unsafe_payload_before_network(change):
    from app.integrations.tiendanube.client import TiendanubeClient
    calls = []
    client = TiendanubeClient("123", "synthetic-only", user_agent="isolated test",
        writes_enabled=True, transport=provider(calls))
    payload = {"name": {"es": "Producto"}, "published": False, "variants": [{"sku": "test"}]}
    if change == "published":
        payload["published"] = True
    elif change == "extra_field":
        payload["stock"] = 10
    elif change == "missing_name":
        del payload["name"]
    else:
        payload["variants"].append({"sku": "other"})
    with pytest.raises(ValueError):
        client.create_hidden_product_payload(payload)
    assert calls == []


def test_manual_client_rejects_visible_or_unverifiable_success_response():
    from app.integrations.tiendanube.client import TiendanubeClient, TiendanubeError
    payload = {"name": {"es": "Producto"}, "published": False, "variants": [{"sku": "test"}]}
    for response in ({"id": 1, "published": True}, {"id": 1}, {"published": False}):
        client = TiendanubeClient("123", "synthetic-only", user_agent="isolated test",
            writes_enabled=True, transport=lambda *args, **kwargs: response)
        with pytest.raises(TiendanubeError) as failure:
            client.create_hidden_product_payload(payload)
        assert failure.value.outcome_unknown is True
