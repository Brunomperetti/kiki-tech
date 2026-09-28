import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from cryptography.fernet import Fernet, InvalidToken

from ..core.config import get_settings
from ..database.models import (
    MercadoLibreConnection,
    MercadoLibreOAuthState,
    MercadoLibreSync,
)
from ..integrations.mercadolibre.client import MercadoLibreClient
from ..integrations.mercadolibre.oauth import OAuthManager
from ..integrations.mercadolibre.transformer import transform_item
from ..integrations.mercadolibre.transport import HTTPTransport, MercadoLibreHTTPError
from ..repositories.catalog_repository import CatalogRepository


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


class MercadoLibreService:
    def __init__(self, db: Session, transport: HTTPTransport | None = None):
        self.db = db
        self.settings = get_settings()
        self.transport = transport or HTTPTransport()
        self.repo = CatalogRepository(db)

    def _fernet(self) -> Fernet:
        if not self.settings.app_encryption_key:
            raise ValueError("El cifrado de Mercado Libre no está configurado.")
        try:
            return Fernet(self.settings.app_encryption_key.encode())
        except (ValueError, TypeError) as exc:
            raise ValueError("El cifrado de Mercado Libre no está configurado.") from exc

    def _encrypt(self, value: str) -> str:
        return self._fernet().encrypt(value.encode()).decode()

    def _decrypt(self, value: str) -> str:
        try:
            return self._fernet().decrypt(value.encode()).decode()
        except InvalidToken as exc:
            raise ValueError("No se pudieron leer las credenciales de Mercado Libre.") from exc

    def auth_url(self) -> str:
        if not all(
            [
                self.settings.ml_client_id,
                self.settings.ml_client_secret,
                self.settings.ml_redirect_uri,
            ]
        ):
            raise ValueError("La integración de Mercado Libre no está configurada.")
        state = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        self.db.execute(
            delete(MercadoLibreOAuthState).where(
                MercadoLibreOAuthState.expires_at < now
            )
        )
        self.db.add(
            MercadoLibreOAuthState(
                state_hash=self._state_hash(state),
                expires_at=now + timedelta(minutes=self.settings.ml_state_ttl_minutes),
            )
        )
        self.db.commit()
        return OAuthManager(self.settings, self.transport).authorization_url(state)

    def connect(self, code: str, state: str) -> MercadoLibreConnection:
        now = datetime.now(timezone.utc)
        saved = self.db.scalar(
            select(MercadoLibreOAuthState).where(
                MercadoLibreOAuthState.state_hash == self._state_hash(state)
            )
        )
        if not saved or saved.used_at or _aware(saved.expires_at) <= now:
            raise ValueError("OAuth state inválido o vencido.")
        saved.used_at = now
        # Consume before contacting the provider so even a failed exchange cannot replay it.
        self.db.commit()
        token = OAuthManager(self.settings, self.transport).exchange_code(code)
        user = MercadoLibreClient(
            self.settings, token["access_token"], self.transport
        ).get_current_user()
        connection = self.repo.ml_connection()
        values = {
            "user_id": str(user["id"]),
            "access_token": self._encrypt(token["access_token"]),
            "refresh_token": self._encrypt(token["refresh_token"]),
            "expires_at": OAuthManager.expires_at(token),
            "updated_at": now,
        }
        if connection:
            for key, value in values.items():
                setattr(connection, key, value)
        else:
            connection = MercadoLibreConnection(connected_at=now, **values)
            self.db.add(connection)
        self.db.commit()
        self.db.refresh(connection)
        return connection

    def status(self) -> dict:
        connection = self.repo.ml_connection()
        sync = self.repo.latest_ml_sync()
        if not connection:
            return {
                "connected": False,
                "user_id": None,
                "token_expiration": None,
                "token_expired": False,
                "last_sync": None,
                "listing_count": 0,
            }
        return {
            "connected": True,
            "user_id": connection.user_id,
            "token_expiration": connection.expires_at,
            "token_expired": _aware(connection.expires_at)
            <= datetime.now(timezone.utc),
            "last_sync": sync.created_at if sync else None,
            "listing_count": sync.listing_count if sync else 0,
        }

    def sync(self) -> dict:
        connection = self.repo.ml_connection()
        if not connection:
            raise ValueError("Mercado Libre no está conectado.")
        self._refresh_if_needed(connection)
        client = MercadoLibreClient(
            self.settings, self._decrypt(connection.access_token), self.transport
        )
        try:
            item_ids = client.list_item_ids(connection.user_id)
            items = client.get_items_bulk(item_ids)
        except MercadoLibreHTTPError as exc:
            if exc.status_code != 401:
                raise
            self._refresh(connection)
            client = MercadoLibreClient(
                self.settings, self._decrypt(connection.access_token), self.transport
            )
            item_ids = client.list_item_ids(connection.user_id)
            items = client.get_items_bulk(item_ids)
        listings = [listing for item in items for listing in transform_item(item)]
        payload = [listing.model_dump(mode="json") for listing in listings]
        self.repo.save_snapshot("MERCADOLIBRE_API", payload)
        record = MercadoLibreSync(
            user_id=connection.user_id, listing_count=len(listings), payload=payload
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return {"listing_count": len(listings), "synced_at": record.created_at}

    def _refresh_if_needed(self, connection):
        if _aware(connection.expires_at) <= datetime.now(timezone.utc) + timedelta(
            minutes=2
        ):
            self._refresh(connection)

    def _refresh(self, connection):
        token = MercadoLibreClient(
            self.settings, self._decrypt(connection.access_token), self.transport
        ).refresh_access_token(self._decrypt(connection.refresh_token))
        connection.access_token = self._encrypt(token["access_token"])
        if token.get("refresh_token"):
            connection.refresh_token = self._encrypt(token["refresh_token"])
        connection.expires_at = OAuthManager.expires_at(token)
        connection.updated_at = datetime.now(timezone.utc)
        self.db.commit()

    @staticmethod
    def _state_hash(state: str) -> str:
        return hashlib.sha256(state.encode()).hexdigest()
