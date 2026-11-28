"""Isolated provider doubles: no tokens, network, stock or price mutations."""
from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import SecretStr
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database.models import ImportJobRecord, CatalogSnapshot
from app.integrations.tiendanube.client import TiendanubeClient
from app.services import tiendanube_controlled_submission as service

EID = "9439612"
USER = SimpleNamespace(id=7)


def settings(enabled=False):
    return SimpleNamespace(kiki_tiendanube_read_enabled=True, kiki_tiendanube_writes_enabled=enabled,
                           kiki_v2_writes_enabled=True, tiendanube_store_id="123",
                           tiendanube_access_token=SecretStr("test-only-not-a-real-token"),
                           tiendanube_user_agent="KIKI isolated fixture")


def remote(pid=98, sku="108"):
    return {"id": pid, "name": {"es": "Arroz 500 g"}, "brand": "Marca de prueba",
            "visibility": "hidden", "published": False,
            "variants": [{"id": pid * 10, "sku": sku, "barcode": "7730114100015"}]}


def flat(product):
    v = product["variants"][0]
    return {"product_id": product["id"], "variant_id": v["id"], "sku": v["sku"],
            "barcode": v["barcode"], "brand": product["brand"], "name": product["name"]["es"],
            "visibility": product["visibility"], "published": product["published"]}


@pytest.fixture
def case(tmp_path, monkeypatch):
    engine = create_engine("sqlite:///" + str(tmp_path / "ledger.sqlite"))
    ImportJobRecord.__table__.create(engine)
    CatalogSnapshot.__table__.create(engine)
    review = {"blocked": 0, "preview_fingerprint": "a" * 64, "items": [{
        "ecomm_id": EID, "sku": "108", "workspace_version": 6, "source_is_combo": False,
        "source_parent_is_combo": False, "blockers": [], "gtin_original": "7730114100015",
        "commercial_fields": {"title": "Arroz 500 g", "description": "Descripción con evidencia aprobada.",
                              "brand": "Marca de prueba"}}]}
    calls = []
    def commercial(db, session, channel, ids):
        assert channel == "tn" and ids == [EID]
        return deepcopy(review)
    monkeypatch.setattr(service, "preview_commercial_export", commercial)
    with Session(engine) as db:
        db.add(CatalogSnapshot(source="TIENDANUBE_API", payload=[{
            "store_id": "123", "products": 0, "rows": [], "pages": 1,
            "captured_at": datetime.now(timezone.utc).isoformat()}]))
        db.commit()
    yield engine, review, calls
    engine.dispose()


def preview(db, operation="CREATE_HIDDEN", **kwargs):
    return service.prepare_submission(db, USER, settings(), request_key=kwargs.pop("request_key", str(uuid4())),
        ecomm_id=EID, operation=operation, identity_checks=sorted(service.CHECKS),
        reason="Revisé manualmente identidad, presentación, cantidad y código.", **kwargs)


def send(db, item, transport, enabled=True):
    return service.send_submission(db, USER, settings(enabled), item["id"],
        expected_revision=item["revision"], expected_preview_fingerprint=item["preview_fingerprint"],
        confirm=True, transport=transport)


def provider(calls, rows=None, failure=None):
    def fake(method, url, **kwargs):
        calls.append((method, url, deepcopy(kwargs.get("payload"))))
        if method == "GET":
            assert kwargs["include_total"] is True
            return rows or [], str(len(rows or []))
        if failure:
            raise failure
        assert method in {"POST", "PUT"}
        assert not any(key in kwargs["payload"] for key in ("stock", "price", "cost", "inventory_levels", "published"))
        return remote()
    return fake


def test_default_off_before_any_provider_call_and_no_credential_in_ledger(case):
    engine, _, calls = case
    with Session(engine) as db:
        item = preview(db)
        with pytest.raises(PermissionError):
            send(db, item, provider(calls), enabled=False)
        assert calls == []
        assert "test-only-not-a-real-token" not in str(db.scalar(select(ImportJobRecord)).diagnostics)
        assert service.get_submission(db, item["id"])["state"] == "PREVIEW"


def test_hidden_creation_persisted_and_idempotent_no_repeat(case):
    engine, _, calls = case
    with Session(engine) as db:
        key = str(uuid4())
        item = preview(db, request_key=key)
        assert preview(db, request_key=key)["id"] == item["id"]
        result = send(db, item, provider(calls))
        assert result["state"] == "SUCCEEDED"
        assert result["target_product_id"] == "98" and result["target_variant_id"] == "980"
        assert result["provider_calls"] == 2
        assert calls[-1][2]["visibility"] == "hidden"
        assert send(db, item, provider(calls))["state"] == "SUCCEEDED"
        assert len(calls) == 2
        second = preview(db)
        with pytest.raises(ValueError, match="envío previo"):
            send(db, second, provider(calls))
        assert len(calls) == 2


def test_update_exact_external_ids_payload_excludes_variants_and_visibility(case):
    engine, _, calls = case
    row = remote()
    with Session(engine) as db:
        capture = db.scalar(select(CatalogSnapshot))
        body = deepcopy(capture.payload)
        body[0].update({"products": 1, "rows": [flat(row)]})
        capture.payload = body
        db.commit()
        item = preview(db, "UPDATE_CONTENT", target_product_id="98", target_variant_id="980")
        assert item["blockers"] == []
        result = send(db, item, provider(calls, [row]))
        assert result["state"] == "SUCCEEDED"
        assert calls[-1][0] == "PUT" and calls[-1][1].endswith("/products/98")
        assert set(calls[-1][2]) == {"name", "description", "brand"}


@pytest.mark.parametrize("change", ["evidence", "capture", "expired", "revision"])
def test_changed_preview_blocks_before_network(case, change):
    engine, review, calls = case
    with Session(engine) as db:
        item = preview(db)
        if change == "evidence":
            review["preview_fingerprint"] = "b" * 64
        elif change == "capture":
            capture = db.scalar(select(CatalogSnapshot))
            capture.payload = [{**capture.payload[0], "rows": [flat(remote())], "products": 1}]
            db.commit()
        elif change == "expired":
            job = db.get(ImportJobRecord, item["id"])
            job.unknown_columns = {**job.diagnostics, "expires_at": "2000-01-01T00:00:00+00:00"}
            db.commit()
        else:
            item["revision"] += 1
        with pytest.raises(ValueError):
            send(db, item, provider(calls))
        assert calls == []


@pytest.mark.parametrize("failure", [TimeoutError("secret should not be persisted"), ValueError("sensitive response")])
def test_uncertain_write_is_terminal_and_never_retried(case, failure):
    engine, _, calls = case
    with Session(engine) as db:
        item = preview(db)
        result = send(db, item, provider(calls, failure=failure))
        assert result["state"] == "UNKNOWN"
        assert result["error_code"] == "PROVIDER_OUTCOME_UNKNOWN"
        assert "secret" not in str(result) and "sensitive response" not in str(result)
        assert send(db, item, provider(calls))["state"] == "UNKNOWN"
        assert len(calls) == 2


def test_process_lost_after_receipt_does_not_dispatch_again(case):
    engine, _, calls = case
    with Session(engine) as db:
        item = preview(db)
        job = db.get(ImportJobRecord, item["id"])
        job.status, job.processed = "RUNNING", job.processed + 1
        db.commit()
    with Session(engine) as db:
        assert send(db, item, provider(calls))["state"] == "RUNNING"
        assert calls == []


def test_remote_candidate_and_identity_change_block_writes(case):
    engine, _, calls = case
    with Session(engine) as db:
        item = preview(db)
        result = send(db, item, provider(calls, [remote()]))
        assert result["state"] == "BLOCKED"
        assert result["error_code"] == "REMOTE_DUPLICATE_OR_INCOMPLETE_IDENTITY"
        assert [call[0] for call in calls] == ["GET"]


def test_no_cross_variant_idempotency_reuse_or_automatic_link(case):
    engine, _, calls = case
    with Session(engine) as db:
        key = str(uuid4())
        preview(db, request_key=key)
        with pytest.raises(ValueError, match="otra selección"):
            preview(db, request_key=key, operation="UPDATE_CONTENT", target_product_id="98", target_variant_id="980")
        with pytest.raises(ValueError):
            preview(db, target_product_id="None")
        assert calls == []


def test_human_checks_and_strict_export_blockers_are_not_bypassed(case):
    engine, review, calls = case
    with Session(engine) as db:
        with pytest.raises(ValueError):
            service.prepare_submission(db, USER, settings(), request_key=str(uuid4()), ecomm_id=EID,
                operation="CREATE_HIDDEN", identity_checks=["barcode"], reason="Revisé el código exclusivamente.")
        review["blocked"] = 1
        review["items"][0]["blockers"] = ["Falta licencia vigente y taxonomía aprobada"]
        item = preview(db)
        assert item["state"] == "BLOCKED" and item["blockers"]
        with pytest.raises(ValueError):
            send(db, item, provider(calls))
        assert calls == []


def test_new_client_update_uses_same_fixed_host_and_is_off_by_default():
    calls = []
    client = TiendanubeClient("123", "test", user_agent="test", transport=provider(calls))
    with pytest.raises(PermissionError):
        client.update_product_content("98", name="Arroz", description="Descripción")
    assert calls == []


def test_local_identity_changes_during_remote_preflight_abort_before_write(case):
    engine, review, calls = case
    fake = provider(calls)
    def transport(*args, **kwargs):
        result = fake(*args, **kwargs)
        review["preview_fingerprint"] = "b" * 64
        return result
    with Session(engine) as db:
        item = preview(db)
        result = send(db, item, transport)
        assert result["state"] == "BLOCKED" and result["error_code"] == "LOCAL_EVIDENCE_CHANGED"
        assert [call[0] for call in calls] == ["GET"]


def test_same_target_different_ecomm_variant_cannot_be_sent_again(case):
    engine, _, calls = case
    with Session(engine) as db:
        item = preview(db)
        # Simulate an already-authorized unknown dispatch by another exact variant.
        prior = db.get(ImportJobRecord, item["id"])
        audit = deepcopy(prior.diagnostics)
        audit.update({"ecomm_id": "1234567", "target_product_id": "98", "payload": {"name": {"es": "Otra variante"}}})
        db.add(ImportJobRecord(source=service.SOURCE, filename="123:1234567", records=1,
                              processed=2, status="UNKNOWN", unknown_columns=audit))
        capture = db.scalar(select(CatalogSnapshot))
        capture.payload = [{**capture.payload[0], "products": 1, "rows": [flat(remote())]}]
        db.commit()
        update = preview(db, "UPDATE_CONTENT", target_product_id="98", target_variant_id="980")
        with pytest.raises(ValueError, match="envío previo"):
            send(db, update, provider(calls, [remote()]))
        assert calls == []


def test_capture_staleness_and_foreign_store_do_not_authorize_export(case):
    engine, _, calls = case
    with Session(engine) as db:
        capture = db.scalar(select(CatalogSnapshot))
        original = deepcopy(capture.payload)
        capture.payload = [{**original[0], "captured_at": "2020-01-01T00:00:00+00:00"}]
        db.commit()
        with pytest.raises(ValueError, match="vencida"):
            preview(db)
        capture.payload = [{**original[0], "store_id": "999"}]
        db.commit()
        with pytest.raises(ValueError, match="esta tienda"):
            preview(db)
        assert calls == []


def test_unsafe_remote_visibility_or_missing_variant_receipt_is_unknown(case):
    engine, _, calls = case
    def fake(method, url, **kwargs):
        calls.append(method)
        if method == "GET":
            return [], "0"
        return {"id": 98, "visibility": "visible", "published": True}
    with Session(engine) as db:
        result = send(db, preview(db), fake)
        assert result["state"] == "UNKNOWN" and calls == ["GET", "POST"]


def test_get_and_mutation_routes_require_session_csrf_and_default_flags(case):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.routes import tiendanube_controlled_submission as routes
    engine, _, _ = case
    app = FastAPI()
    app.include_router(routes.router)
    cfg = settings()
    cfg.kiki_v2_enabled = cfg.kiki_channel_workspace_enabled = cfg.kiki_document_workspace_enabled = True
    app.dependency_overrides[routes.get_settings] = lambda: cfg
    # available calls get_settings directly, so patch via isolated monkeypatch context.
    from unittest.mock import patch
    def database():
        with Session(engine) as db:
            yield db
    app.dependency_overrides[routes.get_db] = database
    with patch.object(routes, "get_settings", lambda: cfg), TestClient(app) as client:
        base = "/api/ecomm-app/workspace/channels/tn/submissions"
        assert client.get(base, params={"ecomm_id": EID}).status_code == 401
        assert client.post(base + "/preview", json={}).status_code == 401
        assert client.post(base + "/1/send", json={}).status_code == 401
        app.dependency_overrides[routes.require_session] = lambda: USER
        assert client.get(base, params={"ecomm_id": EID}).status_code == 200
        # Session alone does not bypass CSRF on any mutation.
        assert client.post(base + "/preview", json={}).status_code == 403
        cfg.kiki_v2_enabled = False
        assert client.get(base, params={"ecomm_id": EID}).status_code == 403


def test_actual_reviewed_editor_document_taxonomy_licence_flows_to_hidden_receipt(tmp_path, monkeypatch):
    """Existing real services + local fictional documents, not production data."""
    from test_documental_channel_readiness_guard import prepare, install_fake_source, complete_fields, setting, IDENT
    from test_stage4_channel_preparation import prepare_reviewed, edit_for
    from app.services.ecomm_api_product_workspace_service import EcommApiProductWorkspace
    from app.services.documental.storage import Dossier
    import app.services.documental.research as research
    monkeypatch.setattr(research, "get_settings", lambda: setting())
    engine, _ = prepare(tmp_path)
    calls = []
    with Session(engine) as db:
        install_fake_source(db)
        EcommApiProductWorkspace(db).save(IDENT, complete_fields(), "READY_FOR_CHANNELS", 0, session=USER)
        prepare_reviewed(db)
        db.add(CatalogSnapshot(source="TIENDANUBE_API", payload=[{
            "store_id": "123", "products": 0, "rows": [], "pages": 1,
            "captured_at": datetime.now(timezone.utc).isoformat()}]))
        db.commit()
        saved_fields = deepcopy(edit_for(db).fields)
        saved_history = deepcopy(edit_for(db).history)
        evidence_history = deepcopy(db.get(Dossier, IDENT).history)
        item = service.prepare_submission(db, USER, settings(), request_key=str(uuid4()), ecomm_id=IDENT,
            operation="CREATE_HIDDEN", identity_checks=sorted(service.CHECKS),
            reason="Contraste humano del documento ficticio para esta única presentación.")
        assert item["blockers"] == [] and item["state"] == "PREVIEW"
        def fake(method, url, **kwargs):
            calls.append(method)
            if method == "GET":
                return [], "0"
            assert kwargs["payload"]["variants"] == [{"sku": "9995"}]
            assert kwargs["payload"]["visibility"] == "hidden"
            return {"id": 987, "visibility": "hidden", "published": False,
                    "variants": [{"id": 9870, "sku": "9995"}]}
        result = send(db, item, fake)
        assert result["state"] == "SUCCEEDED" and calls == ["GET", "POST"]
        assert edit_for(db).fields == saved_fields and edit_for(db).history == saved_history
        assert db.get(Dossier, IDENT).history == evidence_history
    engine.dispose()


@pytest.mark.parametrize("change", ["gtin", "brand", "presentation", "pack", "multi_variant"])
def test_update_identity_mismatches_are_blocked_even_with_manual_checks(case, change):
    engine, _, calls = case
    row = flat(remote())
    if change == "gtin":
        row["barcode"] = "7794940000796"
    elif change == "brand":
        row["brand"] = "Otra marca"
    elif change == "presentation":
        row["name"] = "Arroz 250 g"
    elif change == "pack":
        row["name"] = "Pack x6 Arroz 500 g"
    with Session(engine) as db:
        capture = db.scalar(select(CatalogSnapshot))
        rows = [row, {**row, "variant_id": 981}] if change == "multi_variant" else [row]
        capture.payload = [{**capture.payload[0], "products": 1, "rows": rows}]
        db.commit()
        item = preview(db, "UPDATE_CONTENT", target_product_id="98", target_variant_id="980")
        assert item["state"] == "BLOCKED"
        with pytest.raises(ValueError):
            send(db, item, provider(calls))
        assert calls == []


def test_capture_changed_during_remote_wait_is_not_silently_accepted(case):
    engine, _, calls = case
    fake = provider(calls)
    def transport(*args, **kwargs):
        with Session(engine) as other:
            capture = other.scalar(select(CatalogSnapshot))
            capture.payload = [{**capture.payload[0], "captured_at": "2099-01-01T00:00:00+00:00"}]
            other.commit()
        return fake(*args, **kwargs)
    with Session(engine) as db:
        result = send(db, preview(db), transport)
        assert result["state"] == "BLOCKED"
        assert [call[0] for call in calls] == ["GET"]
