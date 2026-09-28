import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, HTTPException, Request
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..database.models import AdminSession
from ..database.session import get_db
from .config import get_settings

SESSION_COOKIE = "kiki_session"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def csrf_token(session_hash: str) -> str:
    secret = get_settings().app_session_secret
    if not secret:
        raise HTTPException(503, "La autenticación interna no está configurada.")
    return hmac.new(secret.encode(), session_hash.encode(), hashlib.sha256).hexdigest()


def verify_credentials(username: str, password: str) -> bool:
    settings = get_settings()
    username_ok = bool(settings.kiki_admin_username) and hmac.compare_digest(
        username, settings.kiki_admin_username
    )
    password_ok = False
    if settings.kiki_admin_password_hash:
        try:
            password_ok = PasswordHasher().verify(
                settings.kiki_admin_password_hash, password
            )
        except (VerificationError, InvalidHashError):
            pass
    return username_ok and password_ok


def create_session(db: Session) -> tuple[str, AdminSession]:
    now = utcnow()
    db.execute(delete(AdminSession).where(AdminSession.expires_at <= now))
    token = secrets.token_urlsafe(48)
    record = AdminSession(
        token_hash=token_hash(token),
        created_at=now,
        expires_at=now + timedelta(hours=get_settings().session_ttl_hours),
        last_seen_at=now,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return token, record


def require_session(request: Request, db: Session = Depends(get_db)) -> AdminSession:
    raw_token = request.cookies.get(SESSION_COOKIE)
    if not raw_token:
        raise HTTPException(401, "Autenticación requerida.")
    supplied_hash = token_hash(raw_token)
    record = db.scalar(
        select(AdminSession).where(AdminSession.token_hash == supplied_hash)
    )
    now = utcnow()
    if not record or not hmac.compare_digest(record.token_hash, supplied_hash):
        raise HTTPException(401, "Autenticación requerida.")
    if aware(record.expires_at) <= now:
        db.delete(record)
        db.commit()
        raise HTTPException(401, "La sesión venció.")
    record.last_seen_at = now
    db.commit()
    request.state.admin_session = record
    return record


def require_csrf(
    request: Request, session: AdminSession = Depends(require_session)
) -> AdminSession:
    supplied = request.headers.get("X-CSRF-Token", "")
    if not supplied or not hmac.compare_digest(supplied, csrf_token(session.token_hash)):
        raise HTTPException(403, "Token CSRF inválido.")
    return session
