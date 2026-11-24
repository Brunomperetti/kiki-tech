"""Stage-3 report/export boundaries; synthetic state only, zero provider traffic."""

from copy import deepcopy

import pytest

from app.services.documental.source_intake_report import (
    _state,
    export_intake_exceptions,
)


@pytest.mark.parametrize(
    "legacy,phase,inspection,fields,document,expected",
    [
        ("PENDING", "PENDING", {}, {}, False, "RESEARCH"),
        ("PENDING", "PENDING", {}, {"title": {}}, False, "RESEARCH"),
        ("RUNNING", "PENDING", {}, {}, False, "RESEARCH"),
        ("IMPORTED", "EXTRACTED", {}, {}, True, "REVIEW_REQUIRED"),
        ("IMPORTED", "EXTRACTED", {}, {"title": {}}, True, "READY"),
        ("IMPORTED", "EXTRACTED", {"conflicts": True}, {"title": {}}, True, "BLOCKED"),
        ("IMPORTED", "EXTRACTED", {"stale": True}, {"title": {}}, True, "BLOCKED"),
        ("BLOCKED", "FAILED", {}, {}, False, "FAILED"),
        ("BLOCKED", "BLOCKED", {}, {}, False, "BLOCKED"),
        ("IMPORTED", "BLOCKED", {}, {"title": {}}, True, "BLOCKED"),
        ("CANCELLED", "FAILED", {}, {}, False, "BLOCKED"),
    ],
)
def test_processing_and_business_states_do_not_mean_automatic_approval(
    legacy,
    phase,
    inspection,
    fields,
    document,
    expected,
):
    assert (
        _state(
            {"state": legacy, "processing": {"phase": phase}},
            inspection,
            fields,
            document,
        )
        == expected
    )


def report():
    return {
        "job_id": "synthetic-job",
        "revision": 3,
        "fingerprint": "a" * 64,
        "items": [
            {
                "ecomm_id": "900003",
                "sku": "=EXTERNAL_FUNCTION()",
                "barcode": "0012345678905",
                "state": "REVIEW_REQUIRED",
                "url": "https://fabricante-stage3.invalid/producto/900003/",
                "document_sha256": "b" * 64,
                "blockers": ["Revisión humana pendiente"],
                "plan": {"blocked_reasons": ["Ingredientes: sin hecho aprobado."]},
            }
        ],
    }


def test_csv_preserves_leading_zeroes_and_neutralizes_spreadsheet_formulas():
    preview = report()
    before = deepcopy(preview)
    data = export_intake_exceptions(preview, 3, "a" * 64)
    assert data.startswith(b"\xef\xbb\xbf")
    text = data.decode("utf-8-sig")
    assert "'=EXTERNAL_FUNCTION()" in text
    assert "0012345678905" in text
    assert "Revisión humana pendiente" in text
    assert "sin hecho aprobado" in text
    assert preview == before


@pytest.mark.parametrize("revision,fingerprint", [(2, "a" * 64), (3, "b" * 64)])
def test_export_rejects_stale_job_or_evidence_snapshot(revision, fingerprint):
    with pytest.raises(ValueError, match="Cambió el lote"):
        export_intake_exceptions(report(), revision, fingerprint)


def test_ready_with_missing_fields_remains_in_exception_export():
    data = report()
    data["items"][0]["state"] = "READY"
    assert b"900003" in export_intake_exceptions(data, 3, "a" * 64)
    data["items"][0]["plan"]["blocked_reasons"] = []
    assert b"900003" not in export_intake_exceptions(data, 3, "a" * 64)


def test_report_and_csv_are_authenticated_local_reads_and_complete_requires_csrf(
    tmp_path, monkeypatch
):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session
    from app.api.routes import documental_workspace as routes
    from app.core import security
    from app.core.config import Settings
    from app.database.session import get_db
    from test_documental_resumable_source_intake import fixture, prepare_job

    settings = Settings(
        _env_file=None,
        app_session_secret="SYNTHETIC-STAGE3-NOT-A-CREDENTIAL",
        kiki_document_workspace_enabled=True,
        kiki_document_resumable_intake_enabled=True,
        kiki_document_explicit_url_intake_enabled=False,
        kiki_document_parser_kernel_required=False,
        kiki_document_source_fetch_hosts="",
    )
    monkeypatch.setattr(routes, "get_settings", lambda: settings)
    monkeypatch.setattr(security, "get_settings", lambda: settings)
    monkeypatch.setattr(
        routes,
        "reader_available",
        lambda: pytest.fail("Local read must not require downloader"),
    )
    engine = fixture(tmp_path)
    with Session(engine) as db:
        _, job = prepare_job(db)
        token, session = security.create_session(db)
        csrf = security.csrf_token(session.token_hash)
    projected = {**report(), "job_id": job["id"], "total": 1}
    monkeypatch.setattr(
        routes, "build_intake_report", lambda *_args: deepcopy(projected)
    )
    calls = []

    class LocalQueue:
        def __init__(self, *_args):
            pass

        def complete_archived(self, job_id, revision, ecomm_id, **document_cas):
            calls.append((job_id, revision, ecomm_id))
            return {"local_only": True}

    monkeypatch.setattr(routes, "SourceIntakeQueue", LocalQueue)
    app = FastAPI()
    app.include_router(routes.router)

    def isolated_db():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = isolated_db
    path = f"/api/ecomm-app/workspace/sources/intake-jobs/{job['id']}"
    query = "?expected_revision=3&expected_fingerprint=" + "a" * 64
    body = {"expected_revision": 3, "ecomm_id": "900003", "confirm": True}
    with TestClient(app) as client:
        assert client.get(path + "/report").status_code == 401
        assert client.get(path + "/exceptions.csv" + query).status_code == 401
        assert client.post(path + "/complete", json=body).status_code == 401
        client.cookies.set(security.SESSION_COOKIE, token)
        assert client.get(path + "/report").json() == projected
        csv = client.get(path + "/exceptions.csv" + query)
        assert csv.status_code == 200
        assert csv.headers["cache-control"] == "no-store"
        assert "attachment" in csv.headers["content-disposition"]
        assert (
            client.get(
                path + "/exceptions.csv" + query.replace("revision=3", "revision=2")
            ).status_code
            == 409
        )
        assert client.post(path + "/complete", json=body).status_code == 403
        assert calls == []
        assert (
            client.post(
                path + "/complete", json=body, headers={"X-CSRF-Token": csrf}
            ).status_code
            == 200
        )
        assert calls == [(job["id"], 3, "900003")]
        settings.kiki_document_resumable_intake_enabled = False
        assert client.get(path + "/report").status_code == 403
        assert client.get(path + "/exceptions.csv" + query).status_code == 403


def test_smoke_entrypoint_refuses_production_and_accidental_ci_impersonation():
    from integration_sandbox.ci_stage3_pipeline_smoke import checked_mode, LOCAL_URL

    for supplied in (
        {},
        {"DATABASE_URL": "postgresql://production.invalid/kiki"},
        {"GITHUB_ACTIONS": "true"},
        {
            "GITHUB_ACTIONS": "true",
            "KIKI_CI_SYNTHETIC_ONLY": "1",
            "OPENAI_API_KEY": "never-used",
        },
    ):
        with pytest.raises(ValueError):
            checked_mode(supplied)
    with pytest.raises(ValueError):
        checked_mode(
            {
                "GITHUB_ACTIONS": "true",
                "KIKI_INTEGRATION_MODE": "local-synthetic",
                "DATABASE_URL": LOCAL_URL,
            },
            local=True,
        )
    assert checked_mode(
        {"KIKI_INTEGRATION_MODE": "local-synthetic", "DATABASE_URL": LOCAL_URL},
        local=True,
    ) == ("local", LOCAL_URL)


def test_truncated_history_preserves_report_actor_contract(tmp_path):
    """At 512+ events, history remains accepted by the strict frontend report."""
    from sqlalchemy.orm import Session
    from app.services.documental.source_intake_queue import MAX_HISTORY_EVENTS
    from app.services.documental.source_intake_storage import SourceIntakeJob
    from test_documental_resumable_source_intake import fixture, prepare_job

    engine = fixture(tmp_path)
    with Session(engine) as db:
        queue, initial = prepare_job(db)
        job = db.get(SourceIntakeJob, initial["id"])
        job.history = [
            {"action": "SYNTHETIC", "at": "2026-11-24T00:00:00+00:00", "by": "fixture"}
            for _ in range(MAX_HISTORY_EVENTS)
        ]
        db.commit()

        for dropped in (1, 2):
            queue._update(job, job.items, "MANUAL_MAINTENANCE")
            history = job.history
            assert len(history) == MAX_HISTORY_EVENTS
            assert history[0]["action"] == "HISTORY_TRUNCATED"
            assert history[0]["events_dropped"] == dropped
            assert history[-1]["action"] == "MANUAL_MAINTENANCE"
            assert all(
                isinstance(event.get("by"), str) and event["by"] for event in history
            )
