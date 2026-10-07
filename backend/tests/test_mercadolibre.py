from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse
from urllib.error import HTTPError

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from cryptography.fernet import Fernet

from app.catalog.models import Channel
from app.database.models import Base, MercadoLibreConnection, MercadoLibreOAuthState
from app.integrations.mercadolibre.client import MercadoLibreClient
from app.integrations.mercadolibre.oauth import OAuthManager
from app.integrations.mercadolibre.transformer import transform_item
from app.integrations.mercadolibre.transport import (
    HTTPTransport,
    MercadoLibreHTTPError,
    Response,
)
from app.services.mercadolibre_service import MercadoLibreService
from app.services.reconciliation_service import ReconciliationService


TEST_ENCRYPTION_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="

def encrypted(value: str) -> str:
    return Fernet(TEST_ENCRYPTION_KEY.encode()).encrypt(value.encode()).decode()


SETTINGS = SimpleNamespace(
    ml_client_id="client-id",
    ml_client_secret="secret",
    ml_redirect_uri="https://example.com/api/mercadolibre/callback",
    ml_api_url="https://api.mercadolibre.com",
    ml_authorization_url="https://auth.mercadolibre.com.ar/authorization",
    ml_state_ttl_minutes=10,
    ml_snapshot_fresh_hours=24,
    app_encryption_key=TEST_ENCRYPTION_KEY,
)


class QueueTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return Response(200, response)


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        yield session


def test_oauth_url_contains_state_and_expected_parameters():
    query = parse_qs(
        urlparse(
            OAuthManager(SETTINGS, QueueTransport([])).authorization_url("safe-state")
        ).query
    )
    assert query == {
        "response_type": ["code"],
        "client_id": ["client-id"],
        "redirect_uri": [SETTINGS.ml_redirect_uri],
        "state": ["safe-state"],
    }


def test_invalid_oauth_state_is_rejected(db, monkeypatch):
    service = MercadoLibreService(db, QueueTransport([]))
    service.settings = SETTINGS
    with pytest.raises(ValueError, match="state"):
        service.connect("code", "invalid")


def test_token_exchange_is_form_encoded_and_users_me_is_read(db):
    transport = QueueTransport(
        [
            {"access_token": "access", "refresh_token": "refresh", "expires_in": 3600},
            {"id": 1234},
        ]
    )
    service = MercadoLibreService(db, transport)
    service.settings = SETTINGS
    state = "one-time-state"
    db.add(
        MercadoLibreOAuthState(
            state_hash=service._state_hash(state),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=2),
        )
    )
    db.commit()
    connection = service.connect("auth-code", state)
    assert connection.user_id == "1234"
    assert connection.access_token != "access"
    assert connection.refresh_token != "refresh"
    assert service._decrypt(connection.access_token) == "access"
    assert transport.calls[0][0] == "POST"
    assert (
        transport.calls[0][2]["headers"]["Content-Type"]
        == "application/x-www-form-urlencoded"
    )
    assert "client_secret=secret" in transport.calls[0][2]["data"]
    assert transport.calls[1][1].endswith("/users/me")


def test_refresh_token():
    transport = QueueTransport(
        [{"access_token": "new", "refresh_token": "next", "expires_in": 3600}]
    )
    token = MercadoLibreClient(SETTINGS, "old", transport).refresh_access_token(
        "refresh"
    )
    assert token["access_token"] == "new"
    assert "grant_type=refresh_token" in transport.calls[0][2]["data"]


def test_scan_pagination_supports_more_than_1000_items():
    first = {"results": [str(i) for i in range(1000)], "scroll_id": "next"}
    second = {"results": ["1000", "1001"], "scroll_id": "done"}
    transport = QueueTransport([first, second, {"results": [], "scroll_id": "done"}])
    ids = MercadoLibreClient(SETTINGS, "token", transport).list_item_ids("42")
    assert len(ids) == 1002
    assert "search_type=scan" in transport.calls[0][1]
    assert "scroll_id=next" in transport.calls[1][1]


def test_bulk_batches_and_uses_current_endpoint():
    transport = QueueTransport(
        [
            [{"status_code": 200, "body": {"id": str(i)}} for i in range(20)],
            [{"status_code": 200, "body": {"id": "20"}}],
        ]
    )
    items = MercadoLibreClient(SETTINGS, "token", transport).get_items_bulk(
        [str(i) for i in range(21)]
    )
    assert len(items) == 21
    assert all("/items/bulk?" in call[1] for call in transport.calls)


def test_bulk_accepts_legacy_code_200():
    transport = QueueTransport([[{"code": 200, "body": {"id": "MLA1"}}]])
    items = MercadoLibreClient(SETTINGS, "token", transport).get_items_bulk(["MLA1"])
    assert items == [{"id": "MLA1"}]


@pytest.mark.parametrize("status", [404, 500])
def test_bulk_non_200_status_raises_controlled_error(status):
    transport = QueueTransport(
        [[{"status_code": status, "body": {"message": "failed"}}]]
    )
    with pytest.raises(MercadoLibreHTTPError) as error:
        MercadoLibreClient(SETTINGS, "token", transport).get_items_bulk(["MLA1"])
    assert error.value.status_code == status


def test_bulk_without_status_does_not_assume_success():
    transport = QueueTransport([[{"body": {"id": "MLA1"}}]])
    with pytest.raises(MercadoLibreHTTPError) as error:
        MercadoLibreClient(SETTINGS, "token", transport).get_items_bulk(["MLA1"])
    assert error.value.status_code == 502


def test_bulk_incomplete_response_raises_controlled_error():
    transport = QueueTransport(
        [[{"status_code": 200, "body": {"id": "MLA1"}}]]
    )
    with pytest.raises(MercadoLibreHTTPError) as error:
        MercadoLibreClient(SETTINGS, "token", transport).get_items_bulk(
            ["MLA1", "MLA2"]
        )
    assert error.value.status_code == 502


def test_transform_product_sku_gtin_and_fields():
    listings = transform_item(
        {
            "id": "MLA1",
            "title": "Producto",
            "status": "active",
            "price": 12.5,
            "permalink": "https://item",
            "attributes": [
                {"id": "SELLER_SKU", "value_name": "SKU-1"},
                {"id": "GTIN", "value_name": "7791234567890"},
            ],
        }
    )
    assert listings[0].channel == Channel.MERCADOLIBRE_API
    assert listings[0].sku == "SKU-1"
    assert listings[0].ean == "7791234567890"
    assert listings[0].url == "https://item"


def test_transform_variation_sku_and_ean():
    listings = transform_item(
        {
            "id": "MLA2",
            "title": "Variante",
            "price": 10,
            "seller_custom_field": "PARENT",
            "variations": [
                {
                    "id": 9,
                    "price": 11,
                    "attributes": [
                        {"id": "SELLER_SKU", "value_name": "VAR-9"},
                        {"id": "EAN", "value_name": "12345678"},
                    ],
                }
            ],
        }
    )
    assert listings[0].external_id == "MLA2#9"
    assert listings[0].sku_product == "PARENT"
    assert listings[0].variant_sku == "VAR-9"
    assert listings[0].ean == "12345678"


def test_status_without_connection(db):
    assert MercadoLibreService(db).status() == {
        "connected": False,
        "user_id": None,
        "token_expiration": None,
        "token_expired": False,
        "last_sync": None,
        "listing_count": 0,
    }


def test_expired_token_refreshes_and_sync_creates_api_snapshot_history(db):
    db.add(
        MercadoLibreConnection(
            user_id="7",
            access_token=encrypted("old"),
            refresh_token=encrypted("refresh"),
            expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
            connected_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    )
    db.commit()
    transport = QueueTransport(
        [
            {"access_token": "new", "refresh_token": "new-refresh", "expires_in": 3600},
            {"results": ["MLA1"]},
            [
                {
                    "status_code": 200,
                    "body": {
                        "id": "MLA1",
                        "title": "A",
                        "price": 1,
                        "seller_custom_field": "SKU",
                    },
                }
            ],
        ]
    )
    service = MercadoLibreService(db, transport)
    service.settings = SETTINGS
    result = service.sync()
    assert result["listing_count"] == 1
    assert service.repo.snapshot("MERCADOLIBRE_API")[0]["sku"] == "SKU"
    assert service.repo.latest_ml_sync().listing_count == 1


def test_partially_successful_batch_does_not_replace_previous_snapshot(db):
    connection = MercadoLibreConnection(
        user_id="7",
        access_token=encrypted("valid"),
        refresh_token=encrypted("refresh"),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        connected_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(connection)
    db.commit()
    service = MercadoLibreService(
        db,
        QueueTransport(
            [
                {"results": ["MLA1", "MLA2"]},
                [
                    {"status_code": 200, "body": {"id": "MLA1"}},
                    {"status_code": 500, "body": {"message": "failed"}},
                ],
            ]
        ),
    )
    service.settings = SETTINGS
    previous = [{"external_id": "PREVIOUS", "channel": "MERCADOLIBRE_API"}]
    service.repo.save_snapshot("MERCADOLIBRE_API", previous)

    with pytest.raises(MercadoLibreHTTPError) as error:
        service.sync()

    assert error.value.status_code == 500
    assert service.repo.snapshot("MERCADOLIBRE_API") == previous
    assert service.repo.latest_ml_sync() is None


def test_successful_complete_sync_replaces_previous_snapshot(db):
    connection = MercadoLibreConnection(
        user_id="7",
        access_token=encrypted("valid"),
        refresh_token=encrypted("refresh"),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        connected_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(connection)
    db.commit()
    service = MercadoLibreService(
        db,
        QueueTransport(
            [
                {"results": ["MLA1"]},
                [
                    {
                        "status_code": 200,
                        "body": {
                            "id": "MLA1",
                            "title": "Current",
                            "price": 10,
                            "seller_custom_field": "CURRENT-SKU",
                        },
                    }
                ],
            ]
        ),
    )
    service.settings = SETTINGS
    service.repo.save_snapshot(
        "MERCADOLIBRE_API",
        [{"external_id": "PREVIOUS", "channel": "MERCADOLIBRE_API"}],
    )

    result = service.sync()

    snapshot = service.repo.snapshot("MERCADOLIBRE_API")
    assert result["listing_count"] == 1
    assert snapshot[0]["external_id"] == "MLA1"
    assert snapshot[0]["sku"] == "CURRENT-SKU"


def test_401_is_refreshed_once(db):
    connection = MercadoLibreConnection(
        user_id="7",
        access_token=encrypted("valid"),
        refresh_token=encrypted("refresh"),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        connected_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(connection)
    db.commit()
    transport = QueueTransport(
        [
            MercadoLibreHTTPError(401, "expired"),
            {"access_token": "new", "refresh_token": "r2", "expires_in": 3600},
            {"results": []},
        ]
    )
    service = MercadoLibreService(db, transport)
    service.settings = SETTINGS
    assert service.sync()["listing_count"] == 0
    assert service._decrypt(connection.access_token) == "new"


@pytest.mark.parametrize("status", [403, 429])
def test_external_errors_are_not_swallowed(db, status):
    db.add(
        MercadoLibreConnection(
            user_id="7",
            access_token=encrypted("valid"),
            refresh_token=encrypted("refresh"),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            connected_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    )
    db.commit()
    service = MercadoLibreService(
        db, QueueTransport([MercadoLibreHTTPError(status, "error")])
    )
    service.settings = SETTINGS
    with pytest.raises(MercadoLibreHTTPError) as error:
        service.sync()
    assert error.value.status_code == status


def test_transport_retries_rate_limit_with_controlled_delay(monkeypatch):
    calls = 0

    class SuccessfulResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return b'{"ok": true}'

    def fake_urlopen(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise HTTPError("url", 429, "limited", {"Retry-After": "1"}, None)
        return SuccessfulResponse()

    delays = []
    monkeypatch.setattr("app.integrations.mercadolibre.transport.urlopen", fake_urlopen)
    response = HTTPTransport(retries=1, sleep=delays.append).request(
        "GET", "https://example.com"
    )
    assert response.data == {"ok": True}
    assert delays == [1.0]


def test_reconciliation_auto_api_and_xlsx_fallback(db, monkeypatch):
    service = ReconciliationService(db)
    service.repo.save_snapshot("MERCADOLIBRE", [{"external_id": "XLSX"}])
    assert service._choose_ml_source("AUTO") == "MERCADOLIBRE"
    service.repo.save_snapshot("MERCADOLIBRE_API", [{"external_id": "API"}])
    assert service._choose_ml_source("AUTO") == "MERCADOLIBRE_API"
    assert service._choose_ml_source("XLSX") == "MERCADOLIBRE"



def test_category_predictor_uses_mla_domain_discovery():
    transport = QueueTransport(
        [[{"category_id": "MLA123", "category_name": "Suplementos"}]]
    )
    client = MercadoLibreClient(SETTINGS, "token", transport)
    result = client.predict_categories("Valeriana Natufarma", limit=3)

    assert result[0]["category_id"] == "MLA123"
    assert "/sites/MLA/domain_discovery/search?" in transport.calls[0][1]
    assert "limit=3" in transport.calls[0][1]


def test_category_attributes_are_read_only_get():
    transport = QueueTransport(
        [[{"id": "BRAND", "name": "Marca", "tags": {"required": True}}]]
    )
    client = MercadoLibreClient(SETTINGS, "token", transport)
    result = client.get_category_attributes("MLA123")

    assert result[0]["id"] == "BRAND"
    assert transport.calls[0][0] == "GET"
    assert transport.calls[0][1].endswith("/categories/MLA123/attributes")
