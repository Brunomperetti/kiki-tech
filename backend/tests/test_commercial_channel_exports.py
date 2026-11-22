"""Disposable synthetic originals and SQL only; no external provider calls."""

from copy import deepcopy
import csv
from io import StringIO
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.database.models import CatalogSnapshot, EcommApiProductEdit
from app.services.documental.storage import Dossier, Document
from app.services.commercial_channel_export_service import (
    preview_commercial_export,
    download_commercial_export,
    download_monthly_report,
    _cell,
)
from app.services.contractual_delivery_audit_service import build_delivery_audit
from app.services.monthly_catalog_reports import (
    save_monthly_report,
    monthly_report,
    acknowledge_monthly_report,
    list_monthly_reports,
)
from app.services.ecomm_api_product_workspace_service import EcommApiProductWorkspace
from test_documental_channel_readiness_guard import (
    IDENT,
    prepare,
    install_fake_source,
    complete_fields,
    setting,
)


@pytest.fixture
def dbcase(tmp_path, monkeypatch):
    import app.services.documental.research as research

    monkeypatch.setattr(research, "get_settings", lambda: setting())
    engine, _ = prepare(tmp_path)
    with Session(engine) as db:
        _, user = install_fake_source(db)
        EcommApiProductWorkspace(db).save(
            IDENT, complete_fields(), "READY_FOR_CHANNELS", 0, session=user
        )
    yield engine
    engine.dispose()


def edit_for(db):
    return db.scalar(
        select(EcommApiProductEdit).where(EcommApiProductEdit.ecomm_id == IDENT)
    )


def test_source_backed_channel_preview_download_is_read_only(dbcase, monkeypatch):
    from app.services.documental.research import Research

    def no_writes(*args, **kwargs):
        raise AssertionError("Export must not reconcile or persist evidence")

    monkeypatch.setattr(Research, "commit_change", no_writes)
    writes = []

    def collect(conn, cursor, statement, params, context, many):
        if statement.lstrip().split()[0].upper() in {"INSERT", "UPDATE", "DELETE"}:
            writes.append(statement)

    event.listen(dbcase, "before_cursor_execute", collect)
    with Session(dbcase) as db:
        before = deepcopy(edit_for(db).history)
        preview = preview_commercial_export(db, SimpleNamespace(id=1), "ml", [IDENT])
        assert preview["total"] == preview["prepared_internal"] == 1
        assert preview["blocked"] == 0
        assert preview["provider_calls"] == preview["ai_requests"] == 0
        assert preview["external_writes_enabled"] is False
        assert preview["native_provider_import_file"] is False
        item = preview["items"][0]
        assert item["evidence_verified"] is True
        assert item["channel_requirements_pending"]
        data, latest = download_commercial_export(
            db, SimpleNamespace(id=1), "ml", [IDENT], preview["preview_fingerprint"]
        )
        assert latest["preview_fingerprint"] == preview["preview_fingerprint"]
        rows = list(csv.DictReader(StringIO(data.decode("utf-8-sig")), delimiter=";"))
        assert rows[0]["ecomm_id"] == IDENT
        assert rows[0]["title"] == complete_fields()["title"]
        assert (
            rows[0]["publicacion_habilitada"]
            == rows[0]["formato_nativo_proveedor"]
            == "NO"
        )
        assert "note" not in rows[0]
        assert edit_for(db).history == before
        assert not db.new and not db.dirty
    assert writes == []


def test_same_preview_cannot_switch_channels(dbcase):
    with Session(dbcase) as db:
        preview = preview_commercial_export(db, SimpleNamespace(id=1), "ml", [IDENT])
        with pytest.raises(ValueError, match="previsualización"):
            download_commercial_export(
                db, SimpleNamespace(id=1), "tn", [IDENT], preview["preview_fingerprint"]
            )


@pytest.mark.parametrize(
    "change", ["editor", "document", "revocation", "capture", "rights"]
)
def test_changed_data_rejects_download_without_overwriting(dbcase, change):
    with Session(dbcase) as db:
        preview = preview_commercial_export(db, SimpleNamespace(id=1), "tn", [IDENT])
    with Session(dbcase) as other:
        if change == "editor":
            edit = edit_for(other)
            edit.fields = {
                **edit.fields,
                "seo_title": "Edited by another synthetic operator",
            }
            edit.version += 1
        elif change == "document":
            doc = other.scalars(select(Document)).first()
            doc.version += 1
        elif change in {"revocation", "rights"}:
            dossier = other.get(Dossier, IDENT)
            if change == "revocation":
                facts = deepcopy(dossier.facts)
                facts[0]["state"] = "REVOKED"
                dossier.facts = facts
            else:
                history = deepcopy(dossier.history)
                history.append(
                    {
                        "action": "MEDIA_RIGHTS_REVIEW",
                        "detail": {
                            "kind": "IMAGE",
                            "media_url": complete_fields()["media"][0]["url"],
                            "decision": "REVOKED",
                        },
                    }
                )
                dossier.history = history
            dossier.version += 1
        else:
            snap = other.scalar(
                select(CatalogSnapshot).where(
                    CatalogSnapshot.source == "ECOMM_APP_API_STAGE"
                )
            )
            pages = deepcopy(snap.payload)
            pages[0]["captured_at"] = "2026-11-21T12:00:00+00:00"
            snap.payload = pages
        other.commit()
    with Session(dbcase) as db:
        with pytest.raises(ValueError, match="previsualización"):
            download_commercial_export(
                db, SimpleNamespace(id=1), "tn", [IDENT], preview["preview_fingerprint"]
            )


def test_original_and_pack_are_not_substituted_and_missing_source_is_explained(dbcase):
    with Session(dbcase) as db:
        snap = db.scalar(
            select(CatalogSnapshot).where(
                CatalogSnapshot.source == "ECOMM_APP_API_STAGE"
            )
        )
        pages = deepcopy(snap.payload)
        pages[0]["items"][0]["variants"].append(
            {
                "id": "7518950",
                "sku": "9995-X2",
                "variant_description": "Pack x2 de 250 g",
                "is_combo": True,
                "total_stock": 0,
            }
        )
        snap.payload = pages
        db.commit()
        result = preview_commercial_export(
            db, SimpleNamespace(id=1), "ml", [IDENT, "7518950"]
        )
        assert result["total"] == 2
        pack = result["items"][1]
        assert pack["source_is_combo"] is True
        assert pack["evidence_verified"] is False
        assert pack["state"] == "BLOCKED"
        assert any("expediente" in reason for reason in pack["blockers"])
        assert db.get(Dossier, "7518950") is None


@pytest.mark.parametrize(
    "ids",
    [[], [IDENT, IDENT], ["None"], ["invalid id"], [str(i + 1) for i in range(21)]],
)
def test_invalid_selection_rejected(dbcase, ids):
    with Session(dbcase) as db, pytest.raises(ValueError):
        preview_commercial_export(db, SimpleNamespace(id=1), "ml", ids)


@pytest.mark.parametrize(
    "value", ["=HYPERLINK(1)", "\t=1", " +1", "\ufeff@a", "-2", "\n1"]
)
def test_csv_formulas_are_neutralized_without_truncation(value):
    assert _cell(value).startswith("'")
    assert _cell("0" * 5000) == "0" * 5000
    with pytest.raises(ValueError, match="límite"):
        _cell("x" * (128 * 1024 + 1))


def test_budget_checked_before_original_materialization(dbcase, monkeypatch):
    import app.services.commercial_channel_export_service as module

    monkeypatch.setattr(module, "CONTEXT_BYTES", 1)
    with Session(dbcase) as db, pytest.raises(ValueError, match="presupuesto"):
        preview_commercial_export(db, SimpleNamespace(id=1), "ml", [IDENT])


def test_monthly_report_is_recoverable_idempotent_and_ack_is_separate(dbcase):
    with Session(dbcase) as db:
        before_edit = deepcopy(edit_for(db).history)
        summary, _ = build_delivery_audit(db)
        data, _ = download_monthly_report(db, summary["preview_fingerprint"])
        assert data.startswith(b"\xef\xbb\xbf")
        report = save_monthly_report(
            db,
            SimpleNamespace(id=1),
            summary["preview_fingerprint"],
            "Operador de prueba",
        )
        assert report["human_acknowledgement"] is None
        assert report["review_status"] == "AWAITING_HUMAN_REVIEW"
        assert report["individual_fiches_approved"] == report["facts_approved"] == 0
        assert len("KIKI_MONTHLY:" + report["report_id"]) <= 30
        repeated = save_monthly_report(
            db,
            SimpleNamespace(id=1),
            summary["preview_fingerprint"],
            "Otro responsable",
        )
        assert repeated["report_id"] == report["report_id"]
        assert repeated["responsible"] == "Operador de prueba"
    with Session(dbcase) as db:
        restored = monthly_report(db, report["report_id"])
        assert len(restored["rows"]) == restored["summary"]["total"]
        acknowledged = acknowledge_monthly_report(
            db,
            SimpleNamespace(id=2),
            report["report_id"],
            1,
            report["fingerprint"],
            "Revisé el informe general y asigné las excepciones documentales de prueba.",
        )
        assert acknowledged["revision"] == 2
        assert acknowledged["review_status"] == "GENERAL_REVIEW_WITHIN_30_DAYS"
        assert acknowledged["catalog_state_currently_revalidated"] is False
        assert acknowledged["human_acknowledgement"]["scope"].endswith(
            "NOT_INDIVIDUAL_SOURCE_OR_FICHE_APPROVAL"
        )
        assert edit_for(db).history == before_edit
        assert list_monthly_reports(db)["items"][0]["report_id"] == report["report_id"]
        with pytest.raises(ValueError, match="Otro operador"):
            acknowledge_monthly_report(
                db,
                SimpleNamespace(id=3),
                report["report_id"],
                1,
                report["fingerprint"],
                "Una segunda revisión no debe sobrescribir la confirmación anterior.",
            )


def test_monthly_changed_capture_rejects_old_preview_and_confirmation(dbcase):
    with Session(dbcase) as db:
        summary, _ = build_delivery_audit(db)
        report = save_monthly_report(
            db,
            SimpleNamespace(id=1),
            summary["preview_fingerprint"],
            "Operador sintético",
        )
        snap = db.scalar(
            select(CatalogSnapshot).where(
                CatalogSnapshot.source == "ECOMM_APP_API_STAGE"
            )
        )
        pages = deepcopy(snap.payload)
        pages[0]["items"][0]["variants"][0]["sku"] = "MODIFICADO"
        snap.payload = pages
        db.commit()
    with Session(dbcase) as db:
        with pytest.raises(ValueError, match="previsualización"):
            download_monthly_report(db, report["fingerprint"])
        with pytest.raises(ValueError, match="previsualización"):
            acknowledge_monthly_report(
                db,
                SimpleNamespace(id=1),
                report["report_id"],
                1,
                report["fingerprint"],
                "Revisión basada en una captura que ya cambió; debe bloquearse.",
            )
        assert monthly_report(db, report["report_id"])["human_acknowledgement"] is None


def test_routes_require_authentication_and_csrf(dbcase, monkeypatch):
    import app.api.routes.commercial_exports as routes
    from app.core.security import require_session
    from app.database.session import get_db
    import app.core.security as security

    monkeypatch.setattr(
        routes,
        "get_settings",
        lambda: SimpleNamespace(kiki_document_workspace_enabled=True),
    )
    monkeypatch.setattr(
        security,
        "get_settings",
        lambda: SimpleNamespace(
            app_session_secret="synthetic_session_secret_for_offline_test_only"
        ),
    )
    app = FastAPI()
    app.include_router(routes.router)

    def database():
        with Session(dbcase) as db:
            yield db

    app.dependency_overrides[get_db] = database
    with TestClient(app) as client:
        assert client.get("/api/ecomm-app/workspace/reports/monthly").status_code == 401
        assert (
            client.post(
                "/api/ecomm-app/workspace/exports/commercial/preview",
                json={"channel": "ml", "ecomm_ids": [IDENT]},
            ).status_code
            == 401
        )
        app.dependency_overrides[require_session] = lambda: SimpleNamespace(
            id=1, token_hash="synthetic_session_hash"
        )
        assert (
            client.post(
                "/api/ecomm-app/workspace/exports/commercial/preview",
                json={"channel": "ml", "ecomm_ids": [IDENT]},
            ).status_code
            == 403
        )
        from app.core.security import csrf_token

        headers = {"X-CSRF-Token": csrf_token("synthetic_session_hash")}
        response = client.post(
            "/api/ecomm-app/workspace/exports/commercial/preview",
            json={"channel": "ml", "ecomm_ids": [IDENT]},
            headers=headers,
        )
        assert response.status_code == 200
        fp = response.json()["preview_fingerprint"]
        assert (
            client.post(
                "/api/ecomm-app/workspace/exports/commercial/download",
                json={
                    "channel": "ml",
                    "ecomm_ids": [IDENT],
                    "expected_fingerprint": fp,
                    "confirm": False,
                },
                headers=headers,
            ).status_code
            == 422
        )
        csv_response = client.post(
            "/api/ecomm-app/workspace/exports/commercial/download",
            json={
                "channel": "ml",
                "ecomm_ids": [IDENT],
                "expected_fingerprint": fp,
                "confirm": True,
            },
            headers=headers,
        )
        assert csv_response.status_code == 200
        assert csv_response.headers["cache-control"] == "no-store"
        assert csv_response.headers["content-type"].startswith("text/csv")
        assert (
            "kiki-comercial-ml-revision.csv"
            in csv_response.headers["content-disposition"]
        )


def test_large_but_valid_editor_arrays_export_without_truncation(dbcase):
    with Session(dbcase) as db:
        edit = edit_for(db)
        fields = deepcopy(edit.fields)
        fields["attributes"] = [
            {"name": "A" * 90, "value": "B" * 450} for _ in range(40)
        ]
        fields["media"] = [
            {
                "kind": "IMAGE",
                "url": "https://fabricante-prueba.invalid/" + "x" * 900,
                "source_url": "https://fabricante-prueba.invalid/" + "y" * 900,
                "alt": "Z" * 180,
            }
            for _ in range(30)
        ]
        edit.fields = fields
        edit.version += 1
        db.commit()
        preview = preview_commercial_export(db, SimpleNamespace(id=1), "ml", [IDENT])
        assert preview["items"][0]["evidence_verified"] is False
        data, _ = download_commercial_export(
            db, SimpleNamespace(id=1), "ml", [IDENT], preview["preview_fingerprint"]
        )
        rows = list(csv.DictReader(StringIO(data.decode("utf-8-sig")), delimiter=";"))
        import json

        assert json.loads(rows[0]["attributes"]) == fields["attributes"]
        assert json.loads(rows[0]["media"]) == fields["media"]


def test_monthly_audit_detects_concurrent_change_without_table_locks(
    dbcase, monkeypatch
):
    import app.services.contractual_delivery_audit_service as module

    calls = []
    original = module._audit_state

    def changing(db):
        calls.append(None)
        return original(db) if len(calls) == 1 else "changed-concurrently"

    monkeypatch.setattr(module, "_audit_state", changing)
    with Session(dbcase) as db, pytest.raises(ValueError, match="durante la auditoría"):
        build_delivery_audit(db)


def test_versioned_channel_taxonomy_is_separate_and_bound_to_preview(
    dbcase, monkeypatch
):
    import sys
    import app.services.commercial_channel_export_service as module

    inspections = []

    def current_review(inspection, history, channel):
        inspections.append(inspection)
        return {
            "state": "APPROVED",
            "mapping_version": 3,
            "source_pair": {
                "category": "Fabricante",
                "subcategory": "Subcategoría fuente",
            },
            "record": {
                "taxonomy_revision": "2026-11-human-v3",
                "target_pair": {
                    "category": "Canal " + channel,
                    "subcategory": "Revisada",
                },
                "evidence_ids": ["f-categoria", "f-subcategoria"],
                "reviewer": "Operador sintético",
            },
        }

    monkeypatch.setitem(
        sys.modules,
        "app.services.documental.taxonomy_review",
        SimpleNamespace(current_review=current_review),
    )
    with Session(dbcase) as db:
        ml = preview_commercial_export(db, SimpleNamespace(id=1), "ml", [IDENT])
        tn = preview_commercial_export(db, SimpleNamespace(id=1), "tn", [IDENT])
        assert (
            ml["items"][0]["channel_taxonomy"]["target_pair"]["category"] == "Canal ML"
        )
        assert (
            tn["items"][0]["channel_taxonomy"]["target_pair"]["category"] == "Canal TN"
        )
        assert ml["preview_fingerprint"] != tn["preview_fingerprint"]
        assert inspections[0]["ecomm_id"] == IDENT
        assert inspections[0]["expected"]["workspace_version"] == edit_for(db).version
        data, _ = download_commercial_export(
            db, SimpleNamespace(id=1), "ml", [IDENT], ml["preview_fingerprint"]
        )
        assert "Canal ML" in data.decode("utf-8-sig")
        assert ml["items"][0]["channel_taxonomy"]["external_category_ids"] is None
        assert module._taxonomy_review is not None


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/reports/monthly/preview"),
        ("GET", "/reports/monthly"),
        ("POST", "/reports/monthly"),
        ("POST", "/reports/monthly/download"),
        ("GET", "/reports/monthly/202611:abcdef0123"),
        ("POST", "/reports/monthly/202611:abcdef0123/acknowledge"),
        ("POST", "/reports/monthly/202611:abcdef0123/download"),
        ("POST", "/exports/commercial/preview"),
        ("POST", "/exports/commercial/download"),
    ],
)
def test_only_production_compat_harness_allows_exact_delivery_routes(method, path):
    from integration_sandbox.policy import route_allowed

    full = "/api/ecomm-app/workspace" + path
    assert route_allowed(method, full, production_compat=True)
    assert not route_allowed(method, full)


@pytest.mark.parametrize(
    "method,path",
    [
        ("DELETE", "/api/ecomm-app/workspace/reports/monthly"),
        ("GET", "/api/ecomm-app/workspace/reports/monthly/bogus"),
        ("POST", "/api/ecomm-app/workspace/reports/monthly/202611:abcdef0123/publish"),
        ("POST", "/api/ecomm-app/workspace/exports/commercial/sync"),
        ("POST", "/api/mercadolibre/sync"),
        ("POST", "/api/tiendanube/import-csv"),
    ],
)
def test_delivery_harness_does_not_open_methods_or_provider_operations(method, path):
    from integration_sandbox.policy import route_allowed

    assert not route_allowed(method, path, production_compat=True)
