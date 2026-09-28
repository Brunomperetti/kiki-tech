from datetime import timedelta

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.core.config import Settings
from app.core.security import aware, utcnow
from app.database.models import AdminSession, AuthLoginThrottle, Base
from app.database.session import get_db
from app.main import app, create_app


@pytest.fixture
def auth_client():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override_db():
        with factory() as db:
            yield db

    settings = get_settings()
    old = {
        "kiki_admin_username": settings.kiki_admin_username,
        "kiki_admin_password_hash": settings.kiki_admin_password_hash,
        "app_session_secret": settings.app_session_secret,
    }
    settings.kiki_admin_username = "admin"
    settings.kiki_admin_password_hash = PasswordHasher().hash("correct horse")
    settings.app_session_secret = "unit-test-session-secret"
    app.dependency_overrides[get_db] = override_db
    with TestClient(app, base_url="https://testserver") as client:
        yield client, factory
    app.dependency_overrides.clear()
    for key, value in old.items():
        setattr(settings, key, value)


def login(client, username="admin", password="correct horse"):
    return client.post("/api/auth/login", json={"username": username, "password": password})


def test_login_cookie_session_and_safe_response(auth_client):
    client, factory = auth_client
    response = login(client)
    assert response.status_code == 200
    assert response.json()["username"] == "admin"
    assert "password" not in response.text.lower()
    assert "kiki_session=" in response.headers["set-cookie"]
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "Secure" in response.headers["set-cookie"]
    assert "SameSite=none" in response.headers["set-cookie"]
    with factory() as db:
        session = db.scalar(select(AdminSession))
        assert session and len(session.token_hash) == 64
        assert client.cookies["kiki_session"] != session.token_hash
    assert client.get("/api/auth/me").status_code == 200


@pytest.mark.parametrize("username,password", [("admin", "wrong"), ("other", "correct horse")])
def test_login_failures_are_generic(auth_client, username, password):
    response = login(auth_client[0], username, password)
    assert response.status_code == 401
    assert response.json()["detail"] == "Usuario o contraseña incorrectos."


def test_missing_and_expired_sessions_are_unauthorized(auth_client):
    client, factory = auth_client
    assert client.get("/api/dashboard").status_code == 401
    login(client)
    with factory() as db:
        session = db.scalar(select(AdminSession))
        session.expires_at = utcnow() - timedelta(seconds=1)
        db.commit()
    assert client.get("/api/auth/me").status_code == 401
    with factory() as db:
        assert db.scalar(select(AdminSession)) is None


def test_csrf_and_logout_revoke_immediately(auth_client):
    client, _ = auth_client
    csrf = login(client).json()["csrf_token"]
    assert client.get("/api/dashboard").status_code == 200
    assert client.post("/api/reconciliations").status_code == 403
    assert client.post("/api/reconciliations", headers={"X-CSRF-Token": "bad"}).status_code == 403
    allowed = client.post("/api/reconciliations", headers={"X-CSRF-Token": csrf})
    assert allowed.status_code == 201
    assert client.post("/api/auth/logout").status_code == 403
    response = client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf})
    assert response.status_code == 200
    assert client.get("/api/auth/me").status_code == 401


def test_health_public_and_ml_mutations_protected(auth_client):
    client, _ = auth_client
    assert client.get("/health").status_code == 200
    assert client.post("/api/mercadolibre/auth-url").status_code == 401
    assert client.post("/api/mercadolibre/sync").status_code == 401
    assert client.get("/api/mercadolibre/callback?code=x&state=invented").status_code == 400


def test_session_has_fixed_expiration(auth_client):
    client, factory = auth_client
    login(client)
    with factory() as db:
        session = db.scalar(select(AdminSession))
        original_expiry = aware(session.expires_at)
    client.get("/api/auth/me")
    with factory() as db:
        session = db.scalar(select(AdminSession))
        assert aware(session.expires_at) == original_expiry
        assert aware(session.last_seen_at) <= original_expiry


def test_cors_requires_explicit_origins_and_credentials_are_enabled():
    with pytest.raises(ValueError, match="explícitos"):
        Settings(cors_origins="*")
    cors = next(
        middleware
        for middleware in app.user_middleware
        if middleware.cls.__name__ == "CORSMiddleware"
    )
    assert cors.kwargs["allow_credentials"] is True
    assert "*" not in cors.kwargs["allow_origins"]


def test_login_allows_five_failures_then_rate_limits(auth_client):
    client, factory = auth_client
    for _ in range(5):
        response = login(client, password="wrong")
        assert response.status_code == 401
        assert response.json()["detail"] == "Usuario o contraseña incorrectos."
    blocked = login(client, password="wrong")
    assert blocked.status_code == 429
    assert blocked.json()["detail"] == "Usuario o contraseña incorrectos."
    assert int(blocked.headers["Retry-After"]) > 0
    with factory() as db:
        throttle = db.scalar(select(AuthLoginThrottle))
        assert throttle.attempts == 5
        assert len(throttle.key_hash) == 64
        assert "admin" not in throttle.key_hash


def test_login_block_expires(auth_client):
    client, factory = auth_client
    for _ in range(5):
        login(client, password="wrong")
    with factory() as db:
        throttle = db.scalar(select(AuthLoginThrottle))
        throttle.blocked_until = utcnow() - timedelta(seconds=1)
        throttle.window_started_at = utcnow() - timedelta(minutes=16)
        db.commit()
    response = login(client)
    assert response.status_code == 200


def test_successful_login_resets_failures(auth_client):
    client, factory = auth_client
    for _ in range(3):
        assert login(client, password="wrong").status_code == 401
    assert login(client).status_code == 200
    with factory() as db:
        assert db.scalar(select(AuthLoginThrottle)) is None
    for _ in range(5):
        assert login(client, password="wrong").status_code == 401


def test_unknown_username_uses_same_throttle_policy_and_message(auth_client):
    client, _ = auth_client
    for _ in range(5):
        response = login(client, username="does-not-exist")
        assert response.status_code == 401
        assert response.json()["detail"] == "Usuario o contraseña incorrectos."
    response = login(client, username="does-not-exist")
    assert response.status_code == 429
    assert response.json()["detail"] == "Usuario o contraseña incorrectos."


def test_api_docs_disabled_by_default_and_explicitly_enabled():
    disabled_paths = {route.path for route in app.routes}
    assert "/docs" not in disabled_paths
    assert "/redoc" not in disabled_paths
    assert "/openapi.json" not in disabled_paths

    enabled = create_app(Settings(enable_api_docs=True, _env_file=None))
    enabled_paths = {route.path for route in enabled.routes}
    assert {"/docs", "/redoc", "/openapi.json"} <= enabled_paths
