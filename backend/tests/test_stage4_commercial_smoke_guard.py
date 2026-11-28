"""No DB/network: acceptance runner refuses alternate environments pre-import."""

import pytest

from integration_sandbox.ci_stage4_commercial_smoke import (
    CI_URL,
    LOCAL_URL,
    captured_variants,
    checked_mode,
    main,
)


def test_requires_both_ci_optins_and_fixed_target():
    ci = {"GITHUB_ACTIONS": "true", "KIKI_CI_SYNTHETIC_ONLY": "1"}
    assert checked_mode(ci) == ("ci", CI_URL)
    for env in ({}, {"GITHUB_ACTIONS": "true"}, {"KIKI_CI_SYNTHETIC_ONLY": "1"}):
        with pytest.raises(ValueError):
            checked_mode(env)


@pytest.mark.parametrize(
    "binding",
    [
        {"DATABASE_URL": "postgresql://production.invalid/client"},
        {"KIKI_INTEGRATION_MODE": "local-synthetic"},
        {"ECOMM_APP_API_TOKEN": ""},
        {"KIKI_AI_API_KEY": ""},
        {"APP_ENCRYPTION_KEY": ""},
        {"PGHOST": "remote.invalid"},
        {"PGSERVICEFILE": "/private/service"},
    ],
)
def test_refuses_provider_credentials_and_alternate_db(binding):
    with pytest.raises(ValueError):
        checked_mode(
            {"GITHUB_ACTIONS": "true", "KIKI_CI_SYNTHETIC_ONLY": "1", **binding}
        )


def test_local_socket_requires_existing_marker_and_never_impersonates_ci():
    env = {"KIKI_INTEGRATION_MODE": "local-synthetic", "DATABASE_URL": LOCAL_URL}
    assert checked_mode(env, local=True) == ("local", LOCAL_URL)
    for change in (
        {"DATABASE_URL": CI_URL},
        {"GITHUB_ACTIONS": "true"},
        {"KIKI_CI_SYNTHETIC_ONLY": "1"},
    ):
        with pytest.raises(ValueError):
            checked_mode({**env, **change}, local=True)
    with pytest.raises(SystemExit):
        main(["--database-url", "postgresql://production.invalid/client"])


def test_twenty_synthetic_variants_have_unique_api_identity_not_customer_codes():
    pages = captured_variants()
    assert pages[0]["total"] == 20
    variants = [r["variants"][0] for r in pages[0]["items"]]
    assert len({r["id"] for r in variants}) == 20
    assert all(r["barcode"] is None and r["gtin"] is None for r in variants)
    assert all(r["sku"].startswith("PG18-E4-SKU-") for r in variants)


def test_import_does_not_load_app_or_initialize_database():
    import os
    import subprocess
    import sys

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; import integration_sandbox.ci_stage4_commercial_smoke; "
                "assert 'app.core.config' not in sys.modules; "
                "assert 'app.database.session' not in sys.modules; "
                "assert 'sqlalchemy' not in sys.modules; assert 'psycopg' not in sys.modules"
            ),
        ],
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stderr
