"""The Ecomm manual read grant must not enable other commercial connections.

These tests are local/synthetic. No Render access, provider calls, migrations,
publication or changes to scheduled refreshes.
"""
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.routes import v2
from app.core.config import Settings
from app.database.models import Base


def settings(**overrides):
    values = dict(
        _env_file=None,
        kiki_v2_enabled=True,
        kiki_v2_writes_enabled=True,
        kiki_v2_connections_enabled=False,
        ecomm_app_api_token="SYNTHETIC-READ-ONLY-CREDENTIAL",
        kiki_ai_enabled=False,
        kiki_v2_ai_generation_enabled=False,
    )
    values.update(overrides)
    return Settings(**values)


def test_manual_ecomm_refresh_allowed_without_enabling_other_connections():
    config = settings()
    with patch.object(v2, "get_settings", return_value=config):
        assert v2.manual_ecomm_refresh_permitted(config) is True
        assert v2.guard_request(
            "/api/ecomm-app/stage/manual/start", "POST", None
        ) is None
        assert v2.guard_request(
            "/api/ecomm-app/stage/auto/status", "GET", None
        ) is None
        for forbidden in (
            "/api/mercadolibre/auth-url",
            "/api/mercadolibre/sync",
            "/api/tiendanube/import-csv",
        ):
            with pytest.raises(HTTPException) as error:
                v2.guard_request(forbidden, "POST", None)
            assert error.value.status_code == 403, forbidden


@pytest.mark.parametrize("overrides", [
    {"kiki_v2_enabled": False},
    {"kiki_v2_writes_enabled": False},
    {"ecomm_app_api_token": ""},
    {"ecomm_app_api_token": "   "},
])
def test_manual_refresh_fails_closed_without_existing_grants(overrides):
    config = settings(**overrides)
    with patch.object(v2, "get_settings", return_value=config):
        assert not v2.manual_ecomm_refresh_permitted(config)
        with pytest.raises(HTTPException) as error:
            v2.guard_request("/api/ecomm-app/stage/manual/start", "POST", None)
        assert error.value.status_code in {403, 404}


def test_v2_capabilities_include_only_ecomm_manual_refresh_when_enabled():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db, patch.object(
            v2, "get_settings", return_value=settings()
        ):
            caps = v2.capabilities(db, reader_probe=False)
            assert caps["enabled"] is True
            assert caps["writes"] is True
            assert caps["ecomm_manual_refresh"] is True
            assert caps["connections"] is False
            assert caps["openai_generation"] is False
            assert caps["external_research"] is False
        with Session(engine) as db, patch.object(
            v2, "get_settings", return_value=settings(ecomm_app_api_token="")
        ):
            assert v2.capabilities(db, reader_probe=False)[
                "ecomm_manual_refresh"
            ] is False
    finally:
        engine.dispose()
