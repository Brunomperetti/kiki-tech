"""Guard/unit contract for reusable PG18 acceptance; no live DB or HTTP."""

import pytest

from integration_sandbox.ci_stage3_pipeline_smoke import (
    CI_URL,
    LOCAL_URL,
    HOST,
    MockManufacturer,
    _gtin,
    checked_mode,
    main,
    source_url,
    synthetic_page,
)
from app.services.ecomm_api_product_workspace_service import _gtin_check_digit_valid


def test_ci_target_is_fixed_and_requires_both_explicit_ci_opt_ins():
    ci = {"GITHUB_ACTIONS": "true", "KIKI_CI_SYNTHETIC_ONLY": "1"}
    assert checked_mode(ci) == ("ci", CI_URL)
    for env in ({}, {"GITHUB_ACTIONS": "true"}, {"KIKI_CI_SYNTHETIC_ONLY": "1"}):
        with pytest.raises(ValueError):
            checked_mode(env)


@pytest.mark.parametrize(
    "change",
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
def test_ci_refuses_provider_bindings_and_alternate_destinations(change):
    with pytest.raises(ValueError):
        checked_mode(
            {"GITHUB_ACTIONS": "true", "KIKI_CI_SYNTHETIC_ONLY": "1", **change}
        )


def test_local_entry_requires_exact_existing_socket_and_never_impersonates_ci():
    local = {"KIKI_INTEGRATION_MODE": "local-synthetic", "DATABASE_URL": LOCAL_URL}
    assert checked_mode(local, local=True) == ("local", LOCAL_URL)
    for changed in (
        {"DATABASE_URL": CI_URL},
        {"GITHUB_ACTIONS": "true"},
        {"KIKI_CI_SYNTHETIC_ONLY": "1"},
    ):
        with pytest.raises(ValueError):
            checked_mode({**local, **changed}, local=True)
    with pytest.raises(SystemExit):
        main(["--database-url", "postgresql://production.invalid/client"])


def test_fixture_codes_are_valid_unique_strings_not_customer_identity():
    codes = [_gtin(index) for index in range(1, 21)]
    assert len(set(codes)) == 20
    assert all(len(code) == 13 and _gtin_check_digit_valid(code) for code in codes)
    assert HOST.endswith(".invalid")
    assert (
        source_url("8800001") == "https://fabricante-stage3.invalid/producto/8800001/"
    )
    for invalid in (None, "", "../admin", "8800001?token=x", "１"):
        with pytest.raises(ValueError):
            source_url(invalid)


def test_mock_transport_runs_existing_robots_dns_and_response_bounds():
    ident = "8800001"
    path = "/producto/" + ident + "/"
    content = synthetic_page("Arroz sintético", "250 g")
    mock = MockManufacturer({path: content})
    received, trace = mock.download(source_url(ident), HOST, max_bytes=4 * 1024 * 1024)
    assert received == content
    assert trace["robots_checked"] and trace["redirects_followed"] == 0
    assert [row["path"] for row in mock.calls] == ["/robots.txt", path]
    mock.denied_paths.add(path)
    with pytest.raises(ValueError, match="robots"):
        mock.download(source_url(ident), HOST, max_bytes=4 * 1024 * 1024)
    mock.denied_paths.clear()
    mock.addresses = ["127.0.0.1"]
    before = len(mock.calls)
    with pytest.raises(ValueError, match="DNS"):
        mock.download(source_url(ident), HOST, max_bytes=4 * 1024 * 1024)
    assert len(mock.calls) == before
