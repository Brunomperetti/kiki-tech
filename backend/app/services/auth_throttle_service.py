import hashlib
import math
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.security import aware, utcnow
from ..database.models import AuthLoginThrottle

LOGIN_ERROR = "Usuario o contraseña incorrectos."


class AuthThrottleService:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()

    @staticmethod
    def key_hash(client_host: str, username: str) -> str:
        normalized_username = username.strip().casefold()
        return hashlib.sha256(f"{client_host}\0{normalized_username}".encode()).hexdigest()

    def check(self, key_hash: str) -> None:
        now = utcnow()
        self._cleanup(now)
        throttle = self.db.scalar(
            select(AuthLoginThrottle).where(AuthLoginThrottle.key_hash == key_hash)
        )
        if throttle and throttle.blocked_until and aware(throttle.blocked_until) > now:
            retry_after = max(
                1, math.ceil((aware(throttle.blocked_until) - now).total_seconds())
            )
            raise HTTPException(
                429, LOGIN_ERROR, headers={"Retry-After": str(retry_after)}
            )

    def failed(self, key_hash: str) -> None:
        now = utcnow()
        throttle = self.db.scalar(
            select(AuthLoginThrottle)
            .where(AuthLoginThrottle.key_hash == key_hash)
            .with_for_update()
        )
        window = timedelta(minutes=self.settings.auth_window_minutes)
        if not throttle:
            throttle = AuthLoginThrottle(
                key_hash=key_hash,
                attempts=0,
                window_started_at=now,
                updated_at=now,
            )
            self.db.add(throttle)
        elif now - aware(throttle.window_started_at) >= window:
            throttle.attempts = 0
            throttle.window_started_at = now
            throttle.blocked_until = None

        throttle.attempts += 1
        throttle.updated_at = now
        if throttle.attempts >= self.settings.auth_max_attempts:
            throttle.blocked_until = now + timedelta(
                minutes=self.settings.auth_block_minutes
            )
        self.db.commit()

    def succeeded(self, key_hash: str) -> None:
        self.db.execute(
            delete(AuthLoginThrottle).where(AuthLoginThrottle.key_hash == key_hash)
        )
        self.db.commit()

    def _cleanup(self, now) -> None:
        stale_before = now - timedelta(
            minutes=self.settings.auth_window_minutes
            + self.settings.auth_block_minutes
        )
        self.db.execute(
            delete(AuthLoginThrottle).where(
                AuthLoginThrottle.updated_at < stale_before,
                (AuthLoginThrottle.blocked_until.is_(None))
                | (AuthLoginThrottle.blocked_until <= now),
            )
        )
        self.db.commit()
