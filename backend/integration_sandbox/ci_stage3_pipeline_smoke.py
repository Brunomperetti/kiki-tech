"""Reusable PG18 documentary pipeline acceptance; synthetic database + mock HTTP.

CI: GITHUB_ACTIONS=true and KIKI_CI_SYNTHETIC_ONLY=1, fixed disposable DB.
Local: --local-synthetic, existing Unix-socket role/marker preflight first.
Neither mode accepts a supplied database URL or manufacturer credentials.
Importing this module does not import the application, initialize an engine,
connect, create tables or approve facts. Its HTTP double is reusable by the
private browser harness, never by a production route.
"""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from html import escape
import os
import sys
from threading import Barrier
from types import SimpleNamespace
import unittest
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

HOST = "fabricante-stage3.invalid"
PUBLIC_IP = "93.184.216.34"
LOCAL_URL = (
    "postgresql+psycopg://kiki_integration:kiki-synthetic-only@/kiki_integration"
    "?host=/var/run/postgresql&port=5432"
)
CI_URL = (
    "postgresql+psycopg://kiki_ci:synthetic_ci_only@127.0.0.1:5432/kiki_ci_synthetic"
)


def source_url(ident):
    if not isinstance(ident, str) or not ident.isascii() or not ident.isdigit():
        raise ValueError("Synthetic manufacturer fixture requires a numeric test ID")
    return f"https://{HOST}/producto/{ident}/"


def synthetic_page(name, presentation):
    """Original-shaped HTML whose content is explicitly fabricated for tests."""
    return (
        '<!doctype html><html lang="es"><head><title>Documento sintético PG18</title></head>'
        '<body><main><h1 class="product_title entry-title">' + escape(name) + "</h1>"
        '<div class="woocommerce-tabs"><h2>Descripción</h2>'
        '<table class="woocommerce-product-attributes shop_attributes"><tbody>'
        "<tr><th>Peso</th><td>" + escape(presentation) + "</td></tr>"
        "<tr><th>Marca</th><td>Marca sintética de prueba</td></tr>"
        "<tr><th>Fabricante</th><td>Fabricante sintético PG18</td></tr>"
        "<tr><th>Ingredientes</th><td>Arroz de prueba</td></tr>"
        "<tr><th>Conservación</th><td>Conservar en lugar seco</td></tr>"
        "</tbody></table><p>Archivo ficticio del ensayo aislado; no es documento del cliente.</p>"
        "</div></main></body></html>"
    ).encode("utf-8")


def parser_input(body):
    from document_reader.parser import parse

    return parse(
        body.filename,
        body.content_type,
        body.content_base64,
        web_snapshot=body.web_snapshot,
    )


class MockManufacturer:
    """Actual URL/DNS/robots/content rules, transport and DNS supplied locally."""

    def __init__(self, pages):
        self.pages = dict(pages)
        self.calls = []
        self.addresses = [PUBLIC_IP]
        self.denied_paths = set()
        self.fail_once = set()
        self.oversize_paths = set()

    def resolve(self, hostname):
        if hostname != HOST:
            raise AssertionError("No other manufacturer is configured in this fixture")
        return list(self.addresses)

    def get(self, hostname, ip, path, byte_limit):
        from app.services.documental.source_fetch import Result

        if hostname != HOST or ip != PUBLIC_IP:
            raise AssertionError("Mock HTTP must use the pinned synthetic destination")
        self.calls.append({"path": path, "limit": byte_limit})
        if path == "/robots.txt":
            rules = "User-agent: *\n" + "".join(
                f"Disallow: {value}\n" for value in sorted(self.denied_paths)
            )
            if not self.denied_paths:
                rules += "Allow: /\n"
            return Result(200, "text/plain; charset=UTF-8", rules.encode(), PUBLIC_IP)
        if path in self.fail_once:
            self.fail_once.remove(path)
            return Result(503, "text/html", b"", PUBLIC_IP)
        if path in self.oversize_paths:
            return Result(200, "text/html", b"x" * (byte_limit + 1), PUBLIC_IP)
        return Result(
            200 if path in self.pages else 404,
            "text/html; charset=UTF-8",
            self.pages.get(path, b""),
            PUBLIC_IP,
        )

    def download(self, url, hosts, *, max_bytes):
        from app.services.documental.source_fetch import fetch_html

        return fetch_html(
            url,
            hosts,
            max_bytes=max_bytes,
            resolver=self,
            transport=self,
        )

    def import_exact(self, db, actor, **kwargs):
        from app.services.documental.explicit_url_intake import import_explicit_url

        return import_explicit_url(
            db,
            actor,
            **kwargs,
            downloader=self.download,
            parser=parser_input,
        )


def checked_mode(environ, *, local=False):
    """Pure gate, unit-testable without any PostgreSQL or application import."""
    if local:
        if environ.get("GITHUB_ACTIONS") == "true" or environ.get(
            "KIKI_CI_SYNTHETIC_ONLY"
        ):
            raise ValueError("Local and CI modes cannot be combined")
        if (
            environ.get("KIKI_INTEGRATION_MODE") != "local-synthetic"
            or environ.get("DATABASE_URL") != LOCAL_URL
        ):
            raise ValueError(
                "Local mode requires the exact marked synthetic socket database"
            )
        return "local", LOCAL_URL
    if (
        environ.get("GITHUB_ACTIONS") != "true"
        or environ.get("KIKI_CI_SYNTHETIC_ONLY") != "1"
        or environ.get("DATABASE_URL") not in (None, "", CI_URL)
        or environ.get("KIKI_INTEGRATION_MODE")
    ):
        raise ValueError("Only explicitly opted-in disposable GitHub CI is accepted")
    for key in environ:
        if key.startswith(("ECOMM_", "ML_", "OPENAI_")) or key in {
            "KIKI_AI_API_KEY",
            "KIKI_REFRESH_TOKEN",
            "APP_ENCRYPTION_KEY",
            "APP_SESSION_SECRET",
            "PGSERVICE",
            "PGSERVICEFILE",
            "PGHOST",
            "PGHOSTADDR",
            "PGDATABASE",
            "PGUSER",
            "PGPASSWORD",
            "PGOPTIONS",
        }:
            raise ValueError(
                "Provider/application credentials or alternate DB configuration rejected"
            )
    return "ci", CI_URL


def _network_guard(mode):
    if mode == "local":
        # Includes exact URL/environment validation and role/marker verification
        # before importing any application/SQLAlchemy engine module.
        from integration_sandbox.policy import preflight

        preflight()
        return

    def guard(event, args):
        if event == "socket.connect" and args[1] != ("127.0.0.1", 5432):
            raise RuntimeError("CI stage3 test cannot connect to external services")
        if event in {"socket.getaddrinfo", "socket.gethostbyname", "socket.sendto"}:
            raise RuntimeError("CI stage3 test cannot resolve or contact providers")

    sys.addaudithook(guard)


def _connect(mode):
    import psycopg

    if mode == "local":
        connection = psycopg.connect(
            host="/var/run/postgresql",
            port=5432,
            dbname="kiki_integration",
            user="kiki_integration",
            password="kiki-synthetic-only",
            connect_timeout=5,
            sslmode="disable",
            passfile="/dev/null",
            autocommit=True,
        )
        from integration_sandbox.policy import validate_database_identity

        validate_database_identity(connection)
    else:
        connection = psycopg.connect(
            host="127.0.0.1",
            port=5432,
            dbname="kiki_ci_synthetic",
            user="kiki_ci",
            password="synthetic_ci_only",
            connect_timeout=5,
            sslmode="disable",
            passfile="/dev/null",
            autocommit=True,
        )
        if connection.execute("SELECT current_database(),current_user").fetchone() != (
            "kiki_ci_synthetic",
            "kiki_ci",
        ):
            connection.close()
            raise RuntimeError("Unexpected CI PostgreSQL identity; no DDL executed")
    version = int(connection.execute("SHOW server_version_num").fetchone()[0])
    if not 180000 <= version < 190000:
        connection.close()
        raise RuntimeError("Stage3 acceptance requires disposable PostgreSQL18")
    return connection


MODE = None
TARGET = None


def _gtin(index):
    prefix = "779" + str(index).zfill(9)
    weighted = sum(
        int(n) * (3 if i % 2 == 0 else 1) for i, n in enumerate(reversed(prefix))
    )
    return prefix + str((-weighted) % 10)


def captured_variants(size=20):
    items = []
    for index in range(1, size + 1):
        ident = str(8_800_000 + index)
        items.append(
            {
                "code": "PG18-SYNTHETIC-" + ident,
                "description": f"Arroz sintético {index}",
                "is_combo": False,
                "variants": [
                    {
                        "id": int(ident),
                        "sku": "PG18-SKU-" + ident,
                        "description": "250 g",
                        "variant_description": "250 g",
                        "is_combo": False,
                        "barcode": _gtin(index),
                        "gtin": None,
                        "total_stock": 0,
                        "warehouses": [],
                    }
                ],
            }
        )
    return [
        {
            "version": 1,
            "page": 1,
            "per_page": 50,
            "total": size,
            "total_pages": 1,
            "captured_at": "2026-11-24T12:00:00+00:00",
            "items": items,
        }
    ]


class Stage3Pipeline(unittest.TestCase):
    """Service code is unmodified; only HTTP and DNS are test-local doubles."""

    def test_global_recovery_owner_remains_discoverable_in_bounded_listing(self):
        from datetime import datetime, timedelta, timezone
        from sqlalchemy.orm import Session
        from app.services.documental.source_intake_storage import SourceIntakeJob

        with Session(self.engine) as db:
            original = self.create(db)
            oldest = datetime(2026, 1, 1, tzinfo=timezone.utc)
            job = db.get(SourceIntakeJob, original["id"])
            job.created_at = oldest
            rows = deepcopy(job.items)
            rows[0].update(state="RUNNING", claim_until=oldest.isoformat(), claim_token="SYNTHETIC-LEASE")
            job.items = rows
            db.commit()
            for index in range(22):
                newer = self.create(db)
                db.get(SourceIntakeJob, newer["id"]).created_at = oldest + timedelta(days=index + 1)
                db.commit()
            listing = self.queue(db).listing()
            self.assertEqual(len(listing["items"]), 20)
            self.assertEqual(listing["items"][0]["id"], original["id"])
            self.assertEqual(listing["items"][0]["recoverable_items"], 1)
            self.no_editor_writes(db)

    def setUp(self):
        if MODE not in {"ci", "local"} or not TARGET:
            raise RuntimeError(
                "Use the guarded module entry point, not an arbitrary DB"
            )
        from psycopg import sql
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session
        from app.core import config

        self.schema = "kiki_stage3_" + uuid4().hex[:16]
        with _connect(MODE) as checked:
            checked.execute(
                sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(self.schema))
            )
        self.addCleanup(self._cleanup)
        self.engine = create_engine(
            TARGET,
            connect_args={
                "options": f"-csearch_path={self.schema} -clock_timeout=5000 -cstatement_timeout=15000",
            },
        )
        # No .env, provider key or application secret is loaded by this test.
        settings = config.Settings(
            _env_file=None,
            database_url=TARGET,
            kiki_admin_username="PG18 operador sintético",
            kiki_document_workspace_enabled=True,
            kiki_document_channel_guard_enabled=False,
            kiki_document_ai_generation_enabled=False,
            kiki_ai_enabled=False,
            kiki_ai_api_key="",
            ecomm_app_api_token="",
        )
        config.get_settings = lambda: settings
        from app.database.models import Base, CatalogSnapshot
        from app.services.documental.storage import ResearchBase, Control
        from app.services.documental.source_intake_storage import SourceIntakeBase

        Base.metadata.create_all(self.engine)
        ResearchBase.metadata.create_all(self.engine)
        SourceIntakeBase.metadata.create_all(self.engine)
        self.capture = captured_variants()
        with Session(self.engine) as db:
            db.add(Control(id=1))
            db.add(
                CatalogSnapshot(
                    source="ECOMM_APP_API_STAGE", payload=deepcopy(self.capture)
                )
            )
            db.commit()
        self.actor = SimpleNamespace(id="SYNTHETIC-PG18-HUMAN-TEST")
        self.ids = [str(8_800_000 + i) for i in range(1, 21)]
        self.manufacturer = MockManufacturer(
            {
                f"/producto/{ident}/": synthetic_page(
                    f"Arroz sintético {index}", "250 g"
                )
                for index, ident in enumerate(self.ids, 1)
            }
        )

    def _cleanup(self):
        from psycopg import sql

        if hasattr(self, "engine"):
            self.engine.dispose()
        with _connect(MODE) as checked:
            checked.execute(
                sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(self.schema))
            )

    def queue(self, db, actor=None):
        from app.services.documental.source_intake_queue import SourceIntakeQueue

        return SourceIntakeQueue(db, actor or self.actor, HOST)

    def create(self, db, ids=None, key=None):
        ids = ids or self.ids[:1]
        return self.queue(db).create_explicit(
            key or str(uuid4()),
            [
                {
                    "ecomm_id": ident,
                    "url": source_url(ident),
                    "provenance_note": "URL exacta del fabricante ficticio elegida por el ensayo PG18 aislado.",
                }
                for ident in ids
            ],
        )

    def step(self, db, report):
        return self.queue(db).step(
            report["id"],
            report["revision"],
            explicit_importer=self.manufacturer.import_exact,
        )

    def no_editor_writes(self, db):
        from sqlalchemy import select, func
        from app.database.models import (
            EcommApiProductEdit,
            CatalogSnapshot,
            KikiEcommAiDailySlot,
        )

        self.assertEqual(
            db.scalar(select(func.count()).select_from(EcommApiProductEdit)), 0
        )
        self.assertEqual(
            db.scalar(select(func.count()).select_from(KikiEcommAiDailySlot)), 0
        )
        record = db.scalar(
            select(CatalogSnapshot).where(
                CatalogSnapshot.source == "ECOMM_APP_API_STAGE"
            )
        )
        self.assertEqual(record.payload, self.capture)

    def test_twenty_variants_originals_citations_pending_and_restart(self):
        from sqlalchemy import select
        from sqlalchemy.orm import Session
        from app.services.documental.storage import Document, Dossier

        with Session(self.engine) as db:
            report = self.create(db, self.ids)
            job_id = report["id"]
        for expected, ident in enumerate(self.ids, 1):
            # Reopen the DB/session each step, like a different server process.
            with Session(self.engine) as db:
                report = self.queue(db).detail(job_id)
                report = self.step(db, report)
                row = next(r for r in report["items"] if r["ecomm_id"] == ident)
                self.assertEqual(row["state"], "IMPORTED", row)
                doc = db.get(Document, row["document_id"])
                self.assertEqual(doc.body["source"]["review_state"], "PENDING")
                self.assertEqual(
                    doc.body["original"]["sha256"],
                    sha256(self.manufacturer.pages[f"/producto/{ident}/"]).hexdigest(),
                )
                self.assertTrue(doc.body["original_base64"])
                case = db.get(Dossier, ident)
                self.assertTrue(case.facts, row)
                self.assertTrue(all(f["state"] == "PENDING" for f in case.facts))
                for fact in case.facts:
                    self.assertEqual(fact["ecomm_id"], ident)
                    self.assertIn(fact["quote"], doc.body["sections"][fact["location"]])
                self.assertEqual(report["coverage"]["documents_recorded"], expected)
                self.no_editor_writes(db)
        with Session(self.engine) as db:
            stored = self.queue(db).detail(job_id)
            self.assertEqual(stored["state"], "COMPLETED")
            from app.services.documental.source_intake_report import build_intake_report

            report = build_intake_report(db, self.actor, job_id)
            self.assertEqual(sum(report["summary"].values()), 20)
            self.assertEqual(report["summary"]["READY"], 0)
            self.assertEqual(report["metrics"]["documents_recorded"], 20)
            self.assertGreater(report["metrics"]["pending_facts"], 0)
            self.assertEqual(report["metrics"]["claims_approved_by_operation"], 0)
            self.assertEqual(report["metrics"]["commercial_fields_saved"], 0)
            self.assertEqual(report["metrics"]["ai_requests"], 0)
            self.assertEqual(len(self.manufacturer.calls), 40)
            before_calls = len(self.manufacturer.calls)
            again = self.step(db, stored)
            self.assertEqual(again["state"], "COMPLETED")
            self.assertEqual(len(self.manufacturer.calls), before_calls)
            self.assertEqual(len(db.scalars(select(Document)).all()), 20)

    def test_explicit_synthetic_approval_then_deterministic_fields_no_editor_writes(
        self,
    ):
        from sqlalchemy.orm import Session
        from app.services.documental.contracts import Provenance
        from app.services.documental.local_documents import LocalDocuments
        from app.services.documental.research import Research
        from app.services.documental.proposals import Proposals
        from app.services.documental.commercial_plan import commercial_plan
        from app.services.documental.source_intake_report import (
            build_intake_report,
            export_intake_exceptions,
        )

        ident = self.ids[0]
        with Session(self.engine) as db:
            report = self.step(db, self.create(db))
            doc_id = report["items"][0]["document_id"]
            research = Research(db, self.actor)
            case = research.dossier(ident)
            self.assertTrue(case.facts)
            self.assertTrue(all(f["state"] == "PENDING" for f in case.facts))
            report_before = build_intake_report(db, self.actor, report["id"])
            self.assertEqual(report_before["items"][0]["state"], "REVIEW_REQUIRED")
            before = commercial_plan(db, self.actor, [ident])
            self.assertEqual(before["facts_approved"], 0)
            self.assertEqual(before["items"][0]["approved_facts"], 0)
            document = research._document(doc_id)
            LocalDocuments(db, self.actor).provenance(
                ident,
                doc_id,
                Provenance(
                    expected_document_version=document.version,
                    decision="REVIEWED",
                    reason="APROBACIÓN EXPLÍCITA DEL TEST SINTÉTICO, no aceptación de cliente ni fabricante.",
                ),
            )
            case = research.dossier(ident)
            document = research._document(doc_id)
            research.extract(ident, case.version, doc_id, document.version)
            for fact_id in [f["id"] for f in research.dossier(ident).facts]:
                case = research.dossier(ident)
                fact = next(f for f in case.facts if f["id"] == fact_id)
                self.assertFalse(research.blockers(case, fact), fact)
                research.review(
                    ident,
                    case.version,
                    fact_id,
                    fact["version"],
                    "APPROVED",
                    "APROBACIÓN HUMANA SIMULADA DEL TEST sobre citas del original sintético.",
                )
            plan = commercial_plan(db, self.actor, [ident])
            self.assertGreater(plan["items"][0]["approved_facts"], 0)
            proposal = Proposals(db, self.actor).generate(ident, 0)
            self.assertTrue(
                {
                    "title",
                    "short_title",
                    "description",
                    "short_description",
                    "attributes",
                    "seo_title",
                    "seo_description",
                }.issubset(proposal["fields"])
            )
            self.assertTrue(all(f["evidence_ids"] for f in proposal["fields"].values()))
            self.assertFalse(proposal["saved_to_product_fields"])
            report_after = build_intake_report(db, self.actor, report["id"])
            self.assertEqual(report_after["items"][0]["state"], "READY")
            self.assertEqual(
                build_intake_report(db, self.actor, report["id"])["fingerprint"],
                report_after["fingerprint"],
            )
            # A stale report cannot export old exception classifications.
            with self.assertRaises(ValueError):
                export_intake_exceptions(
                    report_after,
                    report_before["revision"],
                    report_before["fingerprint"],
                )
            approved_facts = deepcopy(research.dossier(ident).facts)
            calls = len(self.manufacturer.calls)
            reused = self.step(db, self.create(db, [ident]))
            self.assertEqual(reused["items"][0]["state"], "IMPORTED")
            self.assertEqual(len(self.manufacturer.calls), calls)
            self.assertEqual(research.dossier(ident).facts, approved_facts)
            self.no_editor_writes(db)

    def test_mock_http_policy_rejections_never_archive_or_approve(self):
        from sqlalchemy import select
        from sqlalchemy.orm import Session
        from app.services.documental.storage import Document

        for policy in ("robots", "private_dns", "oversize"):
            with self.subTest(policy=policy), Session(self.engine) as db:
                ident = self.ids[("robots", "private_dns", "oversize").index(policy)]
                path = f"/producto/{ident}/"
                if policy == "robots":
                    self.manufacturer.denied_paths.add(path)
                elif policy == "private_dns":
                    self.manufacturer.addresses = ["127.0.0.1"]
                else:
                    self.manufacturer.oversize_paths.add(path)
                before_calls = len(self.manufacturer.calls)
                report = self.step(db, self.create(db, [ident]))
                self.assertEqual(report["items"][0]["state"], "BLOCKED", report)
                self.assertFalse(db.scalars(select(Document)).all())
                if policy == "private_dns":
                    self.assertEqual(len(self.manufacturer.calls), before_calls)
                self.manufacturer.addresses = [PUBLIC_IP]
                self.no_editor_writes(db)

    def test_changed_identity_pack_repeated_code_and_repeated_sku_block_before_http(
        self,
    ):
        from sqlalchemy import select
        from sqlalchemy.orm import Session
        from app.database.models import CatalogSnapshot
        from app.services.documental.storage import Document

        for conflict in (
            "identity",
            "pack",
            "shared_gtin",
            "shared_sku",
            "gtin_conflict",
        ):
            with self.subTest(conflict=conflict), Session(self.engine) as db:
                snap = db.scalar(
                    select(CatalogSnapshot).where(
                        CatalogSnapshot.source == "ECOMM_APP_API_STAGE"
                    )
                )
                snap.payload = deepcopy(self.capture)
                db.commit()
                report = self.create(db)
                pages = deepcopy(snap.payload)
                one = pages[0]["items"][0]["variants"][0]
                two = pages[0]["items"][1]["variants"][0]
                if conflict == "identity":
                    one["sku"] = "ALTERED-SYNTHETIC-SKU"
                elif conflict == "pack":
                    one["is_combo"] = True
                elif conflict == "shared_gtin":
                    two["barcode"] = one["barcode"]
                elif conflict == "shared_sku":
                    two["sku"] = one["sku"]
                else:
                    one["gtin"] = _gtin(20)
                snap.payload = pages
                db.commit()
                before_calls = len(self.manufacturer.calls)
                report = self.step(db, report)
                self.assertEqual(report["items"][0]["state"], "BLOCKED", report)
                self.assertEqual(len(self.manufacturer.calls), before_calls)
                self.assertFalse(db.scalars(select(Document)).all())

    def test_document_commit_lost_response_is_recovered_without_repeating_http(self):
        from sqlalchemy import select, func
        from sqlalchemy.orm import Session
        from app.services.documental.storage import Document, Dossier

        calls = []

        def dropped_response(db, actor, **kwargs):
            result = self.manufacturer.import_exact(db, actor, **kwargs)
            calls.append(result["incorporated_document_id"])
            raise ConnectionError("Synthetic server lost reply AFTER original commit")

        with Session(self.engine) as db:
            report = self.create(db)
            report = self.queue(db).step(
                report["id"], report["revision"], explicit_importer=dropped_response
            )
            self.assertEqual(len(calls), 1)
            self.assertEqual(report["items"][0]["state"], "IMPORTED", report)
            self.assertGreater(len(db.get(Dossier, self.ids[0]).facts), 0)
            stored = db.get(Document, report["items"][0]["document_id"])
            checksum, version = stored.digest, stored.version
            facts = deepcopy(db.get(Dossier, self.ids[0]).facts)
            http_count = len(self.manufacturer.calls)
        with Session(self.engine) as db:
            result = self.step(db, self.queue(db).detail(report["id"]))
            self.assertEqual(len(self.manufacturer.calls), http_count)
            self.assertEqual(result["items"][0]["document_id"], calls[0])
            self.assertEqual(db.scalar(select(func.count()).select_from(Document)), 1)
            stored = db.get(Document, calls[0])
            self.assertEqual((stored.digest, stored.version), (checksum, version))
            self.assertEqual(db.get(Dossier, self.ids[0]).facts, facts)
            self.no_editor_writes(db)

    def test_new_job_reuses_exact_identity_original_hash_and_pending_fact_versions(
        self,
    ):
        from sqlalchemy import select, func
        from sqlalchemy.orm import Session
        from app.services.documental.storage import Document, Dossier

        with Session(self.engine) as db:
            first = self.step(db, self.create(db))
            row = first["items"][0]
            expected_document = row["document_id"]
            expected_hash = row["processing"]["document_sha256"]
            expected_facts = deepcopy(db.get(Dossier, self.ids[0]).facts)
            before_calls = len(self.manufacturer.calls)
        with Session(self.engine) as db:
            second = self.step(db, self.create(db))
            self.assertNotEqual(second["id"], first["id"])
            self.assertEqual(second["items"][0]["document_id"], expected_document)
            self.assertEqual(
                db.get(Document, expected_document).body["original"]["sha256"],
                expected_hash,
            )
            self.assertEqual(len(self.manufacturer.calls), before_calls)
            self.assertEqual(db.scalar(select(func.count()).select_from(Document)), 1)
            self.assertEqual(db.get(Dossier, self.ids[0]).facts, expected_facts)
            self.no_editor_writes(db)

    def test_corrupted_or_replaced_original_is_not_reextracted_or_downloaded(self):
        from sqlalchemy.orm import Session
        from app.services.documental.storage import Document, Dossier, digest

        with Session(self.engine) as db:
            report = self.step(db, self.create(db))
            row = report["items"][0]
            facts = deepcopy(db.get(Dossier, self.ids[0]).facts)
            doc = db.get(Document, row["document_id"])
            body = deepcopy(doc.body)
            body["original"]["sha256"] = "0" * 64
            doc.body, doc.digest = body, digest(body)
            db.commit()
            before_calls = len(self.manufacturer.calls)
            recovered = self.queue(db).complete_archived(
                report["id"], report["revision"], self.ids[0]
            )
            self.assertEqual(recovered["items"][0]["processing"]["phase"], "BLOCKED")
            self.assertEqual(len(self.manufacturer.calls), before_calls)
            self.assertEqual(db.get(Document, row["document_id"]).body, body)
            self.assertEqual(db.get(Dossier, self.ids[0]).facts, facts)
            self.no_editor_writes(db)

    def test_manual_retry_is_bounded_and_never_approves_or_executes_another_item(self):
        from sqlalchemy.orm import Session

        def timeout(*_args, **_kwargs):
            raise TimeoutError("SIMULATED request timeout; no HTTP request was made")

        with Session(self.engine) as db:
            report = self.create(db, self.ids[:2])
            for attempt in range(1, 4):
                report = self.queue(db).step(
                    report["id"], report["revision"], explicit_importer=timeout
                )
                row = report["items"][0]
                self.assertEqual(row["state"], "BLOCKED", row)
                self.assertEqual(row["attempts"], attempt)
                self.assertEqual(report["items"][1]["state"], "PENDING")
                self.assertEqual(report["items"][1]["attempts"], 0)
                if attempt < 3:
                    report = self.queue(db).retry(
                        report["id"], report["revision"], self.ids[0]
                    )
            with self.assertRaises(ValueError):
                self.queue(db).retry(report["id"], report["revision"], self.ids[0])
            db.rollback()
            self.assertEqual(self.manufacturer.calls, [])
            self.no_editor_writes(db)

    def test_actual_mock_http503_allows_one_explicit_retry_then_cited_candidates(self):
        from sqlalchemy.orm import Session
        from app.services.documental.storage import Dossier

        self.manufacturer.fail_once.add(f"/producto/{self.ids[0]}/")
        with Session(self.engine) as db:
            report = self.step(db, self.create(db, self.ids[:2]))
            first = report["items"][0]
            self.assertEqual(first["state"], "BLOCKED")
            self.assertTrue(first["processing"]["retryable"], first)
            self.assertEqual(first["attempts"], 1)
            self.assertEqual(report["items"][1]["attempts"], 0)
            report = self.queue(db).retry(report["id"], report["revision"], self.ids[0])
        with Session(self.engine) as db:
            report = self.step(db, self.queue(db).detail(report["id"]))
            self.assertEqual(report["items"][0]["state"], "IMPORTED", report)
            self.assertEqual(report["items"][0]["attempts"], 2)
            self.assertEqual(report["items"][1]["attempts"], 0)
            self.assertTrue(
                all(f["state"] == "PENDING" for f in db.get(Dossier, self.ids[0]).facts)
            )
            self.no_editor_writes(db)

    def test_parallel_expired_recovery_has_one_winner_and_no_duplicate_claims(self):
        from sqlalchemy.orm import Session
        from app.services.documental.source_intake_storage import SourceIntakeJob
        from app.services.documental.storage import Dossier

        with Session(self.engine) as db:
            report = self.step(db, self.create(db, self.ids[:2]))
            job = db.get(SourceIntakeJob, report["id"])
            rows = deepcopy(job.items)
            rows[0].update(
                state="RUNNING",
                claim_token="SYNTHETIC-LOST-WORKER",
                claim_until=(
                    datetime.now(timezone.utc) - timedelta(seconds=1)
                ).isoformat(),
            )
            job.items = rows
            job.revision += 1
            db.commit()
            revision = job.revision
            facts = deepcopy(db.get(Dossier, self.ids[0]).facts)
            calls = len(self.manufacturer.calls)
        ready = Barrier(2)

        def recover(actor_id):
            with Session(self.engine) as db:
                ready.wait(timeout=10)
                try:
                    result = self.queue(db, SimpleNamespace(id=actor_id)).recover(
                        report["id"], revision
                    )
                except ValueError:
                    db.rollback()
                    return "CONFLICT"
                self.assertEqual(result["items"][0]["state"], "IMPORTED")
                return "RECOVERED"

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(recover, ("PG18-TEST-A", "PG18-TEST-B")))
        self.assertEqual(sorted(outcomes), ["CONFLICT", "RECOVERED"])
        with Session(self.engine) as db:
            current = self.queue(db).detail(report["id"])
            self.assertEqual(current["revision"], revision + 1)
            self.assertEqual(len(self.manufacturer.calls), calls)
            self.assertEqual(current["items"][1]["state"], "PENDING")
            self.assertEqual(current["items"][1]["attempts"], 0)
            self.assertEqual(db.get(Dossier, self.ids[0]).facts, facts)
            with self.assertRaises(ValueError):
                self.queue(db)._finish(
                    report["id"],
                    self.ids[0],
                    "SYNTHETIC-LOST-WORKER",
                    current["items"][0]["document_id"],
                    None,
                )
            db.rollback()

    def test_url_mismatch_and_wrong_variant_document_cannot_approve_identity(self):
        from sqlalchemy.orm import Session
        from app.services.documental.storage import Dossier

        with Session(self.engine) as db:
            # Same domain and a plausible page are not proof of exact variant.
            self.manufacturer.pages[f"/producto/{self.ids[0]}/"] = synthetic_page(
                "Otro producto sintético", "1 kg"
            )
            report = self.step(db, self.create(db))
            row = report["items"][0]
            self.assertEqual((row.get("processing") or {}).get("phase"), "BLOCKED", row)
            dossier = db.get(Dossier, self.ids[0])
            self.assertTrue(dossier is None or not dossier.facts)
            self.no_editor_writes(db)

    def test_maximum_twenty_and_explicit_idempotency_key(self):
        from sqlalchemy.orm import Session

        with Session(self.engine) as db:
            key = str(uuid4())
            first = self.create(db, self.ids, key)
            second = self.create(db, self.ids, key)
            self.assertEqual(first["id"], second["id"])
            self.assertEqual(first["revision"], second["revision"])
            with self.assertRaises(ValueError):
                self.create(db, [*self.ids, "8800021"])
            db.rollback()
            with self.assertRaises(ValueError):
                self.create(db, self.ids[:1], key)
            db.rollback()
            self.assertEqual(self.manufacturer.calls, [])


def main(argv=None):
    global MODE, TARGET
    args = list(sys.argv[1:] if argv is None else argv)
    if args not in ([], ["--local-synthetic"]):
        raise SystemExit("Only --local-synthetic is supported; no arbitrary DB target")
    MODE, TARGET = checked_mode(os.environ, local=bool(args))
    _network_guard(MODE)
    with _connect(MODE) as checked:
        print(
            "PG18 stage3 synthetic database verified:",
            checked.execute("SHOW server_version").fetchone()[0],
            flush=True,
        )
    outcome = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(Stage3Pipeline)
    )
    if not outcome.wasSuccessful():
        raise SystemExit(1)
    print(
        "Stage3 pipeline PASS: mock HTTP only; 0 provider calls, 0 AI, 0 automatic approvals/publications; isolated schemas removed.",
        flush=True,
    )


if __name__ == "__main__":
    main()
