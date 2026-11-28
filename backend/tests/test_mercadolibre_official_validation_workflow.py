"""Actual existing ML client, fake transport, disposable ledger; no real tokens."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database.models import ImportJobRecord, MercadoLibreConnection
from app.integrations.mercadolibre.client import MercadoLibreClient
from app.integrations.mercadolibre.transport import Response
from app.services import mercadolibre_official_validation as service

EID = "9439612"
USER = SimpleNamespace(id=1)


def settings(enabled=False):
    return SimpleNamespace(kiki_ml_official_validation_enabled=enabled, kiki_v2_writes_enabled=True,
                           ml_api_url="https://api.mercadolibre.com")


def parameters():
    return {"seller_id": "123", "category_id": "MLA1400", "price": 1234.5,
            "currency_id": "ARS", "available_quantity": 1, "condition": "new",
            "buying_mode": "buy_it_now", "listing_type_id": "gold_special", "attributes": []}


@pytest.fixture
def case(tmp_path, monkeypatch):
    engine = create_engine("sqlite:///" + str(tmp_path / "validation.sqlite"))
    ImportJobRecord.__table__.create(engine)
    MercadoLibreConnection.__table__.create(engine)
    # No facts selected for attributes; strict export itself is separately
    # proven by Stage4 tests. This fixture isolates official validation policy.
    from app.services.documental.storage import Dossier
    Dossier.__table__.create(engine)
    review = {"preview_fingerprint": "a" * 64, "items": [{"blockers": [],
        "channel_taxonomy": {"target_pair": {"category": "Alimentos", "subcategory": "Arroz"}},
        "field_evidence": {}, "commercial_fields": {"title": "Arroz 500 g", "media": [{"kind": "IMAGE", "url": "https://marca-prueba.invalid/arroz.jpg"}]}}]}
    monkeypatch.setattr(service, "preview_commercial_export", lambda *_a, **_k: deepcopy(review))
    with Session(engine) as db:
        db.add(MercadoLibreConnection(id=1, user_id="123", access_token="encrypted-fixture",
            refresh_token="encrypted-fixture-never-used", expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
            connected_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc)))
        db.commit()
    yield engine, review
    engine.dispose()


class Transport:
    def __init__(self, *, result=204, owner=123, category="Arroz", attrs=None, failure=False):
        self.calls = []
        self.result, self.owner, self.category = result, owner, category
        self.attrs, self.failure = attrs or [], failure

    def request(self, method, url, *, headers=None, data=None):
        assert "/oauth" not in url and not (method == "POST" and url.endswith("/items"))
        self.calls.append((method, url, data))
        if url.endswith("/users/me"):
            return Response(200, {"id": self.owner})
        if url.endswith("/attributes"):
            return Response(200, self.attrs)
        if "/categories/" in url:
            return Response(200, {"id": "MLA1400", "path_from_root": [{"name": "Alimentos"}, {"name": self.category}]})
        assert method == "POST" and url.endswith("/items/validate")
        if self.failure:
            raise TimeoutError("SECRET_BODY_MUST_NOT_LOG")
        return Response(self.result, {})


class Factory:
    def __init__(self):
        self.calls = 0
    def __call__(self, db):
        return self
    def _client(self, connection):
        self.calls += 1
        return MercadoLibreClient(settings(), "fixture-not-a-real-token", transport=Transport())
    def _run(self, *_a, **_kw):
        pytest.fail("Automatic token refresh must not be used")
    def _refresh(self, *_a, **_kw):
        pytest.fail("Token refresh must not be used")


def preview(db, **overrides):
    data = dict(request_key=str(uuid4()), ecomm_id=EID, parameters=parameters(),
                reason="Revisé los parámetros auténticos y autorizo únicamente validar, sin publicar.")
    data.update(overrides)
    return service.prepare(db, USER, settings(), **data)


def validate(db, item, transport, *, enabled=True, factory=None):
    return service.validate(db, USER, settings(enabled), item["id"], expected_revision=item["revision"],
        expected_preview_fingerprint=item["preview_fingerprint"], confirm=True,
        service_factory=factory or Factory(), transport=transport)


def test_default_off_never_reads_credential_or_calls_client(case):
    engine, _ = case
    with Session(engine) as db:
        item, factory, transport = preview(db), Factory(), Transport()
        with pytest.raises(PermissionError):
            validate(db, item, transport, enabled=False, factory=factory)
        assert transport.calls == [] and factory.calls == 0


def test_existing_validate_item_invoked_once204_only_no_publication_or_token_changes(case):
    engine, _ = case
    with Session(engine) as db:
        connection = db.get(MercadoLibreConnection, 1)
        before = (connection.access_token, connection.refresh_token, connection.expires_at)
        item, transport = preview(db), Transport()
        result = validate(db, item, transport)
        assert result["state"] == "VALIDATED" and result["official_payload_validated"] is True
        assert result["publication_created"] is False and result["provider_calls"] == 4
        assert [call[0] for call in transport.calls] == ["GET", "GET", "GET", "POST"]
        assert validate(db, item, transport)["state"] == "VALIDATED" and len(transport.calls) == 4
        assert (connection.access_token, connection.refresh_token, connection.expires_at) == before
        assert "fixture-not-a-real-token" not in str(db.scalar(select(ImportJobRecord)).diagnostics)


@pytest.mark.parametrize("change", ["expired", "seller"])
def test_token_expiration_and_seller_owner_checked_before_client(case, change):
    engine, _ = case
    with Session(engine) as db:
        item, factory, transport = preview(db), Factory(), Transport()
        connection = db.get(MercadoLibreConnection, 1)
        if change == "expired":
            connection.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        else:
            connection.user_id = "999"
        db.commit()
        with pytest.raises(ValueError):
            validate(db, item, transport, factory=factory)
        assert factory.calls == 0 and transport.calls == []


@pytest.mark.parametrize("transport,expected", [
    (Transport(result=200), "REJECTED"), (Transport(result=400), "REJECTED"),
    (Transport(owner=999), "BLOCKED"), (Transport(category="Otro producto"), "BLOCKED"),
    (Transport(attrs=[{"id": "MODEL", "tags": {"required": True}}]), "BLOCKED"),
    (Transport(failure=True), "UNKNOWN"),
])
def test_rejections_missing_official_attributes_owner_category_and_unknown_response_do_not_retry(case, transport, expected):
    engine, _ = case
    with Session(engine) as db:
        item = preview(db)
        result = validate(db, item, transport)
        assert result["state"] == expected and result["official_payload_validated"] is False
        count = len(transport.calls)
        if expected in {"REJECTED", "UNKNOWN"}:
            assert validate(db, item, transport)["state"] == expected
        else:
            with pytest.raises(ValueError):
                validate(db, item, transport)
        assert len(transport.calls) == count and "SECRET_BODY" not in str(result)


def test_missing_parameters_and_unbacked_attribute_are_blocked_without_fiction(case):
    engine, _ = case
    with Session(engine) as db:
        item = preview(db, parameters={})
        assert item["state"] == "BLOCKED" and item["blockers"]
        with pytest.raises(ValueError):
            validate(db, item, Transport())
        data = parameters()
        data["attributes"] = [{"id": "BRAND", "value_name": "Marca no aprobada", "fact_id": "a" * 24}]
        assert preview(db, parameters=data)["state"] == "BLOCKED"


def test_current_workspace_and_evidence_version_change_prevents_remote_call(case):
    engine, review = case
    with Session(engine) as db:
        item, transport = preview(db), Transport()
        review["preview_fingerprint"] = "b" * 64
        with pytest.raises(ValueError):
            validate(db, item, transport)
        assert transport.calls == []


@pytest.mark.parametrize("method,path", [("POST", "/items"), ("POST", "/oauth/token"), ("PUT", "/items/MLA1"), ("GET", "/users/123"), ("GET", "/categories/MLA1400?x=1")])
def test_transport_boundary_cannot_call_mutations_oauth_or_unapproved_routes(method, path):
    delegate = Transport()
    boundary = service.ValidationGuard(delegate)
    with pytest.raises(ValueError):
        boundary.request(method, "https://api.mercadolibre.com" + path)
    assert delegate.calls == []


def test_revoked_evidence_or_edited_draft_during_official_post_never_turns_green(case):
    engine, review = case
    class RevokingTransport(Transport):
        def request(self, method, url, **kwargs):
            result = super().request(method, url, **kwargs)
            if method == "POST":
                review["preview_fingerprint"] = "c" * 64
            return result
    with Session(engine) as db:
        transport = RevokingTransport()
        result = validate(db, preview(db), transport)
        assert len(transport.calls) == 4
        assert result["state"] == "BLOCKED" and result["official_payload_validated"] is False
        assert result["error_code"] == "LOCAL_CHANGED_AFTER_OFFICIAL_VALIDATION"


@pytest.mark.parametrize("scenario", ["redirect", "private_dns", "peer", "oversize", "tls"])
def test_pinned_transport_rejects_redirects_dns_rebinding_size_and_tls_without_real_network(scenario):
    class Resolver:
        def resolve(self, host):
            assert host == "api.mercadolibre.com"
            return ["127.0.0.1" if scenario == "private_dns" else "93.184.216.34"]
    class Reply:
        status = 302 if scenario == "redirect" else 200
        def getheader(self, name, default=None):
            return "application/json" if name == "Content-Type" else default
        def read(self, size):
            assert size == 524289
            return b"x" * size if scenario == "oversize" else b'{"id":123}'
    class Connection:
        timeout = None
        def __init__(self, host, ip):
            self.closed = False
            self.sock = SimpleNamespace(getpeername=lambda: ("93.184.216.35" if scenario == "peer" else ip, 443))
        def connect(self):
            if scenario == "tls":
                import ssl
                raise ssl.SSLCertVerificationError("test certificate invalid")
        def request(self, *args, **kwargs):
            pass
        def getresponse(self):
            return Reply()
        def close(self):
            self.closed = True
    transport = service.ValidationTransport(resolver=Resolver(), connection_factory=Connection)
    with pytest.raises((ValueError, OSError)):
        transport.request("GET", "https://api.mercadolibre.com/users/me")


def test_auth_csrf_and_feature_gates_on_new_routes(case):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from unittest.mock import patch
    from app.api.routes import mercadolibre_official_validation as routes
    engine, _ = case
    cfg = settings()
    cfg.kiki_v2_enabled = cfg.kiki_channel_workspace_enabled = cfg.kiki_document_workspace_enabled = True
    app = FastAPI()
    app.include_router(routes.router)
    def database():
        with Session(engine) as db:
            yield db
    app.dependency_overrides[routes.get_db] = database
    with patch.object(routes, "get_settings", lambda: cfg), TestClient(app) as client:
        base = "/api/ecomm-app/workspace/channels/ml/validations"
        assert client.get(base, params={"ecomm_id": EID}).status_code == 401
        assert client.post(base + "/preview", json={}).status_code == 401
        app.dependency_overrides[routes.require_session] = lambda: USER
        assert client.get(base, params={"ecomm_id": EID}).status_code == 200
        assert client.post(base + "/preview", json={}).status_code == 403
        assert client.post(base + "/1/validate", json={}).status_code == 403
        cfg.kiki_channel_workspace_enabled = False
        assert client.get(base, params={"ecomm_id": EID}).status_code == 403


@pytest.mark.parametrize("field,expected", [("brand", "PREVIEW"), ("presentation", "BLOCKED")])
def test_brand_official_attribute_requires_current_cited_brand_fact_not_arbitrary_approved_value(case, field, expected):
    from app.services.documental.storage import Dossier
    engine, review = case
    ident = "a" * 24
    review["items"][0]["field_evidence"] = {"brand": [{"fact_id": ident}]}
    with Session(engine) as db:
        db.add(Dossier(ecomm_id=EID, version=1, identity={}, identity_digest="a" * 64,
                       facts=[{"id": ident, "field": field, "value": "Marca aprobada", "state": "APPROVED"}], history=[]))
        db.commit()
        params = parameters()
        params["attributes"] = [{"id": "BRAND", "value_name": "Marca aprobada", "fact_id": ident}]
        item = preview(db, parameters=params)
        assert item["state"] == expected
        if expected == "PREVIEW":
            transport = Transport(attrs=[{"id": "BRAND", "tags": {"required": True}}])
            assert validate(db, item, transport)["state"] == "VALIDATED"
