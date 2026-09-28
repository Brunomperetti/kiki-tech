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
from app.database.models import AdminSession, Base
from app.database.session import get_db
from app.main import app


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
