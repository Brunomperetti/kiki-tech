"""Opt-in doubles ONLY. Original routes, jobs, OAuth, capture and CSV services.

Imported only by create_sandbox_app(connections=True), after preflight. No socket,
HTTP client, production credential or change to a production integration module.
"""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from threading import Event
from urllib.parse import urlsplit

from sqlalchemy import select

from app.database.models import CatalogSnapshot, MercadoLibreConnection
from app.database.session import SessionLocal
from app.integrations.ecomm_app.catalog_stage import STAGE_SOURCE
from app.integrations.ecomm_app.public_api import API_PREFIX, EcommAppApiError
from app.integrations.mercadolibre.transport import Response
from app.services.mercadolibre_service import MercadoLibreService


class InventoryFixture:
    fail = False
    calls = []

    def __init__(self, token):
        assert token == "SYNTHETIC-NOT-A-CREDENTIAL"

    def _call(self, method, path, *, params, body=None):
        assert method == "GET" and path == API_PREFIX + "/productos" and body is None
        assert params == {"page": 1, "limit": 50, "sort": "sku_asc"}
        type(self).calls.append((method, path))
        Event().wait(0.5)  # bounded local latency; enough to exercise concurrent starts
        if self.fail:
            raise EcommAppApiError(
                503,
                "SYNTHETIC_UNAVAILABLE",
                "Fallo simulado; captura anterior conservada.",
            )
        with SessionLocal() as db:
            pages = db.scalar(
                select(CatalogSnapshot).where(CatalogSnapshot.source == STAGE_SOURCE)
            ).payload
            items = deepcopy(pages[0]["items"])
        assert len(items) == 6 and all(
            p["code"].startswith("SYNTHETIC-") for p in items
        )
        return {
            "items": items,
            "paginacion": {
                "page": 1,
                "per_page": 50,
                "total": len(items),
                "total_pages": 1,
            },
        }


class MLFixtureTransport:
    calls = []
    fail = False

    def request(self, method, url, *, headers=None, data=None):
        parsed = urlsplit(url)
        assert parsed.scheme == "https" and parsed.netloc == "blocked.invalid"
        type(self).calls.append((method, parsed.path))
        if self.fail:
            from app.integrations.mercadolibre.transport import MercadoLibreHTTPError

            raise MercadoLibreHTTPError(503, "Fallo sintético")
        if method == "POST" and parsed.path == "/oauth/token":
            return Response(
                200,
                {
                    "access_token": "SYNTHETIC-ACCESS",
                    "refresh_token": "SYNTHETIC-REFRESH",
                    "expires_in": 3600,
                },
            )
        assert method == "GET"
        if parsed.path == "/users/me":
            return Response(200, {"id": "SYNTHETIC-ML-ACCOUNT"})
        if parsed.path == "/users/SYNTHETIC-ML-ACCOUNT/items/search":
            return Response(200, {"results": ["MLA900000003"]})
        if parsed.path == "/items/bulk":
            return Response(
                200,
                [
                    {
                        "code": 200,
                        "body": {
                            "id": "MLA900000003",
                            "title": "Chía sintética 250 g",
                            "status": "active",
                            "seller_custom_field": "DEMO-CHIA",
                            "price": 0,
                            "attributes": [
                                {"id": "BRAND", "value_name": "Marca sintética"}
                            ],
                        },
                    }
                ],
            )
        raise AssertionError("Ruta no permitida por el doble local.")


class LocalMLService(MercadoLibreService):
    def __init__(self, db):
        super().__init__(db, transport=MLFixtureTransport())


def install():
    from app.api.routes import mercadolibre
    from app.services import ecomm_api_refresh_job_service

    # Process-local bindings only, never imported by app.main or deployment code.
    ecomm_api_refresh_job_service.EcommAppInventoryClient = InventoryFixture
    mercadolibre.MercadoLibreService = LocalMLService


def seed_connection(factory):
    with factory() as db:
        service = LocalMLService(db)
        db.add(
            MercadoLibreConnection(
                user_id="SYNTHETIC-ML-ACCOUNT",
                access_token=service._encrypt("SYNTHETIC-ACCESS"),
                refresh_token=service._encrypt("SYNTHETIC-REFRESH"),
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                connected_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )
        db.commit()
