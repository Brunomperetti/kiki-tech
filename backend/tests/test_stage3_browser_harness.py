"""Pure private-harness boundaries; no database/network/provider initialization."""

from copy import deepcopy
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest

from integration_sandbox.policy import route_allowed
from integration_sandbox.stage3_fixtures import (
    HOST,
    RETRY_ONCE_ID,
    VARIANTS,
    fixture_manufacturer,
    initialize,
    source_url,
)

BASE = "/api/ecomm-app/workspace/"
JOB = "00000000-0000-0000-0000-000000000001"


@pytest.mark.parametrize(
    "method,suffix",
    [
        ("GET", "sources/intake-jobs"),
        ("GET", "sources/intake-jobs/" + JOB),
        ("GET", "sources/intake-jobs/" + JOB + "/report"),
        ("GET", "sources/intake-jobs/" + JOB + "/exceptions.csv"),
        ("POST", "sources/intake-jobs/exact-urls"),
        *[
            ("POST", "sources/intake-jobs/" + JOB + "/" + action)
            for action in ("step", "retry", "recover", "cancel", "complete")
        ],
        ("POST", "900003/evidence/facts/review-batch"),
        ("POST", "900006/documents/local-" + "a" * 32 + "/identity-review"),
    ],
)
def test_stage3_routes_require_separate_explicit_harness_profile(method, suffix):
    path = BASE + suffix
    assert route_allowed(method, path, production_compat=True, stage3=True)
    assert not route_allowed(method, path)
    assert not route_allowed(method, path, production_compat=True)
    assert not route_allowed(method, path, stage3=True)
    assert not route_allowed(
        method, path, production_compat=True, stage3=True, connections=True
    )


@pytest.mark.parametrize(
    "method,path",
    [
        ("POST", BASE + "sources/intake-jobs"),  # no sitemap/network path
        ("PUT", BASE + "sources/intake-jobs/" + JOB),
        ("DELETE", BASE + "sources/intake-jobs/" + JOB),
        ("GET", BASE + "sources/intake-jobs/not-a-uuid/report"),
        ("POST", BASE + "sources/intake-jobs/" + JOB + "/publish"),
        ("POST", BASE + "7518949/evidence/facts/review-batch"),
        ("POST", "/api/mercadolibre/sync"),
        ("POST", "/api/tiendanube/import-csv"),
        ("POST", "/api/ecomm-app/stage/manual/start"),
    ],
)
def test_stage3_cannot_open_production_ids_providers_or_other_methods(method, path):
    assert not route_allowed(method, path, production_compat=True, stage3=True)


def test_manufacturer_is_known_fabricated_data_and_only_one_http_retry():
    manufacturer = fixture_manufacturer()
    assert set(VARIANTS) == {"900003", "900004", "900005", "900006"}
    path = urlsplit(source_url(RETRY_ONCE_ID)).path
    assert manufacturer.get(HOST, "93.184.216.34", path, 10000).status == 503
    second = manufacturer.get(HOST, "93.184.216.34", path, 10000)
    assert second.status == 200
    assert b"Archivo ficticio" in second.body
    with pytest.raises(AssertionError):
        manufacturer.resolve("fabricante-productivo.invalid")


@pytest.mark.parametrize("attempts,consumed", [(0, False), (1, True), (3, True)])
def test_restart_preserves_jobs_and_does_not_rearm_a_consumed_failure(
    attempts, consumed
):
    items = [{"ecomm_id": RETRY_ONCE_ID, "attempts": attempts}]
    original = deepcopy(items)

    class Database:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def scalars(self, statement):
            return [items]

    application = SimpleNamespace(state=SimpleNamespace())
    initialize(application, Database)
    path = urlsplit(source_url(RETRY_ONCE_ID)).path
    assert (path not in application.state.stage3_manufacturer.fail_once) == consumed
    assert items == original


@pytest.mark.parametrize(
    "kwargs",
    [
        {"stage3": True},
        {"stage3": True, "production_compat": True, "autonomous": True},
        {"stage3": True, "production_compat": True, "connections": True},
    ],
)
def test_stage3_rejects_mixed_modes_before_db_preflight(kwargs, monkeypatch):
    import integration_sandbox.bootstrap as module

    def forbidden():
        raise AssertionError("Invalid mode cannot reach database preflight")

    monkeypatch.setattr(module, "preflight", forbidden)
    with pytest.raises(RuntimeError, match="Etapa 3"):
        module.create_sandbox_app(**kwargs)
