"""Actual PostgreSQL 18 commercial acceptance, only disposable synthetic data.

CI uses the fixed ephemeral service and both opt-ins. Local execution requires
--local-synthetic and the existing non-superuser socket/marker preflight before
application imports or DDL. No production URL, provider, credentials, paid AI,
manufacturer authorization or genuine human acceptance is used by this test.
Importing this module has no application, engine or database side effects.
"""

import base64
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import os
import sys
from threading import Barrier, Event
from types import SimpleNamespace
import unittest
from uuid import uuid4

LOCAL_URL = (
    "postgresql+psycopg://kiki_integration:kiki-synthetic-only@/kiki_integration"
    "?host=/var/run/postgresql&port=5432"
)
CI_URL = (
    "postgresql+psycopg://kiki_ci:synthetic_ci_only@127.0.0.1:5432/kiki_ci_synthetic"
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
            raise RuntimeError("CI stage4 test cannot connect to external services")
        if event in {"socket.getaddrinfo", "socket.gethostbyname", "socket.sendto"}:
            raise RuntimeError("CI stage4 test cannot resolve or contact providers")

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
        raise RuntimeError("Stage4 acceptance requires disposable PostgreSQL18")
    return connection


MODE = None
TARGET = None


def captured_variants(size=20):
    """Fabricated API shape; IDs are local fixtures, never customer references."""
    return [
        {
            "page": 1,
            "total": size,
            "total_pages": 1,
            "per_page": 50,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "items": [
                {
                    "code": f"PG18-E4-{i}",
                    "description": f"Lentejas prueba {i} 250 g",
                    "is_combo": False,
                    "variants": [
                        {
                            "id": 8_900_000 + i,
                            "sku": f"PG18-E4-SKU-{i}",
                            "variant_description": "250 g",
                            "description": "250 g",
                            "is_combo": False,
                            "gtin": None,
                            "barcode": None,
                            "total_stock": 0,
                            "warehouses": [],
                        }
                    ],
                }
                for i in range(1, size + 1)
            ],
        }
    ]


def seed_document(db, actor, ident):
    """Explicit TEST source review and facts; never auto-approval in app code.

    Original bytes are fabricated UTF-8 text, clearly labelled as such. The
    document follows the reader's persisted shape. PDF parsing and sandbox
    boundary remain separately tested by the existing reader/browser suites.
    """
    from app.services.documental.research import Research
    from app.services.documental.storage import Document, digest

    index = int(ident) - 8_900_000
    name = f"Lentejas prueba {index} 250 g"
    claims = []
    for field, value in (
        ("product_name", name),
        ("presentation", "250 g"),
        ("brand", "Marca sintética PG18"),
        ("manufacturer", "Fabricante ficticio PG18"),
        ("characteristics", "Lentejas secas de prueba"),
        ("category", "Dietética de prueba"),
        ("subcategory", "Legumbres de prueba"),
    ):
        claims.append(
            {
                "field": field,
                "value": value,
                "unit": None,
                "location": f"texto/linea/{len(claims)+1}",
                "quote": f"{field}: {value}",
                "presentation": "250 g",
                "commercial_field": "attributes",
            }
        )
    sections = {row["location"]: row["quote"] for row in claims}
    sections["texto/linea/8"] = (
        "ENSAYO FICTICIO. No es documentación ni permiso del cliente."
    )
    for kind, extension in (("IMAGE", "png"), ("VIDEO", "mp4")):
        sections[f"permiso/{kind}"] = (
            f"Licencia sintética: el titular de prueba autoriza el uso comercial de "
            f"https://fabricante-e4.invalid/{ident}.{extension} en catálogo de ensayo."
        )
    original = "\n".join(sections.values()).encode()
    checksum = sha256(original).hexdigest()
    body = {
        "id": "local-" + f"{int(ident):032x}",
        "version": 1,
        "synthetic": False,
        "origin_kind": "FILE",
        "associated_ecomm_id": ident,
        "identity": {
            "name": name,
            "presentation": "250 g",
            "ean": None,
            "brand": "Marca sintética PG18",
            "manufacturer": "Fabricante ficticio PG18",
            "is_combo": False,
        },
        "identity_evidence": {
            "name": {
                "value": name,
                "location": claims[0]["location"],
                "quote": claims[0]["quote"],
            },
            "presentation": {
                "value": "250 g",
                "location": claims[1]["location"],
                "quote": claims[1]["quote"],
            },
        },
        "source": {
            "reference_url": f"https://fabricante-e4.invalid/{ident}/",
            "review_state": "REVIEWED",
            "reviewer": "SYNTHETIC TEST OPERATOR",
            "review_reason": "Revisión ficticia explícita para comprobar reglas SQL, no aceptación comercial.",
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
        },
        "provenance": "local://sha256/" + checksum,
        "parse_status": "TEXT_EXTRACTED",
        "parser_blockers": [],
        "parser_warnings": [],
        "original": {
            "sha256": checksum,
            "size": len(original),
            "content_type": "text/plain",
            "filename": "fabricado-solo-ensayo.txt",
        },
        "original_base64": base64.b64encode(original).decode(),
        "sections": sections,
        "claims": claims,
        "kind": "Documento local",
        "title": "FICTICIO PG18.txt",
    }
    doc = Document(id=body["id"], version=1, body=body, digest=digest(body), history=[])
    db.add(doc)
    db.commit()
    research = Research(db, actor)
    item = research.dossier(ident)
    extracted = research.extract(ident, item.version, doc.id, doc.version)
    for candidate in extracted["facts"]:
        item = research.dossier(ident)
        fact = next(f for f in item.facts if f["id"] == candidate["id"])
        research.review(
            ident,
            item.version,
            fact["id"],
            fact["version"],
            "APPROVED",
            "Aprobación explícita SINTÉTICA del test SQL; no revisión auténtica del cliente.",
        )
    db.commit()
    return doc.id


class Stage4Commercial(unittest.TestCase):
    def setUp(self):
        if MODE not in {"ci", "local"} or not TARGET:
            raise RuntimeError("Use guarded module entry point; no arbitrary database")
        from psycopg import sql
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session
        from app.core import config

        self.schema = "kiki_stage4_" + uuid4().hex[:16]
        with _connect(MODE) as checked:
            checked.execute(
                sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(self.schema))
            )
        self.addCleanup(self._cleanup)
        self.engine = create_engine(
            TARGET,
            connect_args={
                "options": f"-csearch_path={self.schema} -clock_timeout=5000 -cstatement_timeout=15000"
            },
        )
        self.settings = config.Settings(
            _env_file=None,
            database_url=TARGET,
            kiki_admin_username="SYNTHETIC PG18 OPERATOR",
            kiki_document_workspace_enabled=True,
            kiki_document_channel_guard_enabled=True,
            kiki_document_channel_guard_pilot_id="8900001",
            kiki_ai_enabled=False,
            kiki_document_ai_generation_enabled=False,
            kiki_ai_api_key="",
            ecomm_app_api_token="",
        )
        # Per-process test DI; no .env or production settings imported.
        config.get_settings = lambda: self.settings
        from app.database.models import Base, CatalogSnapshot
        from app.services.documental.storage import ResearchBase, Control
        from app.services.editorial_batches.storage import EditorialBase

        Base.metadata.create_all(self.engine)
        ResearchBase.metadata.create_all(self.engine)
        EditorialBase.metadata.create_all(self.engine)
        from app.services.documental.source_intake_storage import SourceIntakeBase

        SourceIntakeBase.metadata.create_all(self.engine)
        self.capture = captured_variants()
        self.ids = [str(8_900_000 + i) for i in range(1, 21)]
        self.actor = SimpleNamespace(id="SYNTHETIC-E4-PG18-OPERATOR")
        with Session(self.engine) as db:
            db.add(Control(id=1))
            db.add(
                CatalogSnapshot(
                    source="ECOMM_APP_API_STAGE", payload=deepcopy(self.capture)
                )
            )
            db.commit()

    def _cleanup(self):
        from psycopg import sql

        if hasattr(self, "engine"):
            self.engine.dispose()
        with _connect(MODE) as checked:
            checked.execute(
                sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(self.schema))
            )

    def seed(self, db, count=1):
        return [seed_document(db, self.actor, ident) for ident in self.ids[:count]]

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
        self.assertEqual(
            db.scalar(
                select(CatalogSnapshot).where(
                    CatalogSnapshot.source == "ECOMM_APP_API_STAGE"
                )
            ).payload,
            self.capture,
        )

    def catalog(self, db, version=0, retired=False):
        from app.services.documental.taxonomy_catalog import TaxonomyCatalog

        return TaxonomyCatalog(db, self.actor).save(
            expected_version=version,
            revision=f"SYNTHETIC-E4-v{version+1}",
            entries=[
                {
                    "id": "legumbres",
                    "category": "Dietética de prueba",
                    "subcategory": "Legumbres de prueba",
                    "state": "RETIRED" if retired else "ACTIVE",
                }
            ],
            mappings=[]
            if retired
            else [
                {
                    "id": "ml-legumbres",
                    "pair_id": "legumbres",
                    "channel": "ML",
                    "category": "Categoría ML interna de prueba",
                    "subcategory": "Subcategoría ML interna de prueba",
                    "state": "ACTIVE",
                }
            ],
            reason="Revisión explícita del vocabulario SINTÉTICO de ensayo PostgreSQL.",
        )

    def approve_taxonomy(self, service, state, catalog, **changes):
        return service.review(
            self.ids[0],
            expected_version=state["expected_version"],
            expected_workspace_version=state["expected_workspace_version"],
            expected_fingerprint=state["evidence_fingerprint"],
            channel=state["channel"],
            decision="APPROVED",
            taxonomy_revision=catalog["revision"],
            target_category=state["source_pair"]["category"],
            target_subcategory=state["source_pair"]["subcategory"],
            reason="Clasificación explícita SINTÉTICA de prueba, no aceptación del cliente.",
            catalog_version=catalog["version"],
            catalog_pair_id="legumbres",
            **changes,
        )

    def test_taxonomy_catalog_persistence_retirement_and_mapping_invalidation(self):
        from sqlalchemy.orm import Session
        from app.services.documental.taxonomy_catalog import TaxonomyCatalog
        from app.services.documental.taxonomy_review import TaxonomyReview

        with Session(self.engine) as db:
            self.seed(db)
            catalog = self.catalog(db)
            service = TaxonomyReview(db, self.actor)
            approved = self.approve_taxonomy(service, service.get(self.ids[0]), catalog)
            self.assertEqual(approved["state"], "APPROVED")
            self.assertTrue(approved["catalog_bound"])
            self.no_editor_writes(db)
        with Session(self.engine) as db:
            self.assertEqual(TaxonomyCatalog(db, self.actor).get()["version"], 1)
            self.assertEqual(
                TaxonomyReview(db, self.actor).get(self.ids[0])["state"], "APPROVED"
            )
            self.catalog(db, 1, retired=True)
            state = TaxonomyReview(db, self.actor).get(self.ids[0])
            self.assertEqual(state["state"], "STALE")
            self.assertEqual(state["record"]["catalog_version"], 1)
            self.no_editor_writes(db)

    def test_two_parallel_catalog_writers_have_only_one_cas_winner(self):
        from sqlalchemy.orm import Session

        with Session(self.engine) as db:
            self.catalog(db)
        barrier = Barrier(2)

        def attempt():
            with Session(self.engine) as db:
                barrier.wait(timeout=10)
                try:
                    self.catalog(db, 1)
                    return "saved"
                except ValueError:
                    db.rollback()
                    return "conflict"

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: attempt(), range(2)))
        self.assertEqual(sorted(results), ["conflict", "saved"])

    def media(self, ident=None, kind="IMAGE"):
        ident = ident or self.ids[0]
        return {
            "kind": kind,
            "url": f"https://fabricante-e4.invalid/{ident}.{'png' if kind == 'IMAGE' else 'mp4'}",
            "alt": "Recurso FICTICIO del ensayo",
            "source_url": f"https://fabricante-e4.invalid/{ident}/",
        }

    def rights(self, research, doc, media, decision="APPROVED", *, bound=False):
        from app.services.documental.media_rights import review_media_rights

        item = research.dossier(self.ids[0])
        return review_media_rights(
            research,
            item.ecomm_id,
            item.version,
            doc.id,
            doc.version,
            media["url"],
            media["kind"],
            media["source_url"],
            decision,
            "OWNER_AUTHORIZATION",
            "permiso/" + media["kind"],
            doc.body["sections"]["permiso/" + media["kind"]],
            "Autorización explícita SINTÉTICA del test; no implica permiso real del fabricante.",
            **(
                {
                    "alt_text": media["alt"],
                    "presentation": "250 g",
                    "expected_workspace_version": 1,
                }
                if bound
                else {}
            ),
        )

    def test_exact_image_and_video_rights_persist_revoke_and_source_drift(self):
        from sqlalchemy.orm import Session
        from app.services.documental.storage import Document, digest
        from app.services.documental.research import Research
        from app.services.documental.media_rights import media_permission_report

        from app.services.ecomm_api_product_workspace_service import (
            EcommApiProductWorkspace,
            blank_fields,
        )

        with Session(self.engine) as db:
            docid = self.seed(db)[0]
            resources = [self.media(), self.media(kind="VIDEO")]
            fields = blank_fields()
            fields.update(presentation="250 g", media=resources)
            EcommApiProductWorkspace(db).save(self.ids[0], fields, "DRAFT", 0)
            research = Research(db, self.actor)
            report = media_permission_report(
                research, research.dossier(self.ids[0]), resources
            )
            self.assertEqual(
                [row["state"] for row in report], ["NO_PERMISSION", "NO_PERMISSION"]
            )
            for media in resources:
                self.rights(research, db.get(Document, docid), media, bound=True)
            db.commit()
        with Session(self.engine) as db:
            research = Research(db, self.actor)
            report = media_permission_report(
                research, research.dossier(self.ids[0]), resources
            )
            self.assertTrue(
                all(row["current"] and row["stage4_ready"] for row in report)
            )
            self.rights(research, db.get(Document, docid), resources[0], "REVOKED")
            db.commit()
            report = media_permission_report(
                research, research.dossier(self.ids[0]), resources
            )
            self.assertEqual(report[0]["state"], "REVOKED")
            doc = db.get(Document, docid)
            doc.version += 1
            doc.body = {**doc.body, "version": doc.version}
            doc.digest = digest(doc.body)
            db.commit()
            report = media_permission_report(
                Research(db, self.actor), research.dossier(self.ids[0]), resources
            )
            self.assertEqual(report[1]["state"], "STALE")
            self.assertEqual(
                EcommApiProductWorkspace(db).get(self.ids[0])["version"], 1
            )

    def test_same_gtin_and_pack_cannot_inherit_unit_evidence_or_media(self):
        from sqlalchemy import select
        from sqlalchemy.orm import Session
        from app.database.models import CatalogSnapshot
        from app.services.documental.research import Research
        from app.services.documental.storage import Document
        from app.services.documental.media_rights import media_grant_current

        with Session(self.engine) as db:
            docid = self.seed(db)[0]
            research = Research(db, self.actor)
            self.rights(research, db.get(Document, docid), self.media())
            db.commit()
            stage = db.scalar(
                select(CatalogSnapshot).where(
                    CatalogSnapshot.source == "ECOMM_APP_API_STAGE"
                )
            )
            payload = deepcopy(stage.payload)
            for index in (0, 1, 2):
                payload[0]["items"][index]["variants"][0]["barcode"] = "7794940000796"
            payload[0]["items"][1]["is_combo"] = True
            payload[0]["items"][1]["variants"][0].update(
                is_combo=True, variant_description="Pack x2 de 250 g"
            )
            stage.payload = payload
            db.commit()
            research = Research(db, self.actor)
            for ident in self.ids[1:3]:
                item = research.dossier(ident)
                self.assertFalse(media_grant_current(research, item, self.media()))
                with self.assertRaises(ValueError):
                    research.extract(ident, item.version, docid, 1)
                db.rollback()
            self.assertFalse(
                media_grant_current(
                    research, research.dossier(self.ids[0]), self.media()
                )
            )
            # Source identity changed: even the original ID must revalidate.

    def test_saved_18_field_coverage_does_not_certify_unbacked_seo_or_media(self):
        from sqlalchemy.orm import Session
        from app.services.documental.research import Research
        from app.services.documental.completion import saved_field_coverage
        from app.services.ecomm_api_product_workspace_service import (
            blank_fields,
            EcommApiProductWorkspace,
        )

        with Session(self.engine) as db:
            self.seed(db)
            fields = blank_fields()
            fields.update(
                title="Lentejas prueba 1 250 g · 250 g",
                presentation="250 g",
                seo_title="Milagroso producto sin gluten",
                media=[self.media()],
            )
            result = EcommApiProductWorkspace(db).save(self.ids[0], fields, "DRAFT", 0)
            self.assertEqual(result["version"], 1)
            research = Research(db, self.actor)
            item = research.dossier(self.ids[0])
            report = saved_field_coverage(research, item, fields)
            self.assertEqual(report["total_fields"], 18)
            rows = {r["field"]: r for r in report["fields"]}
            self.assertEqual(rows["seo_title"]["state"], "FILLED_UNBACKED")
            self.assertEqual(rows["media"]["state"], "BLOCKED")
            self.assertFalse(report["publication_allowed"])
            db.commit()
        with Session(self.engine) as db:
            saved = EcommApiProductWorkspace(db).get(self.ids[0])
            self.assertEqual(saved["version"], 1)
            self.assertEqual(saved["fields"], fields)

    def proposal(self, db, ident):
        from app.services.documental.proposals import Proposals

        return Proposals(db, self.actor).generate(ident, 0)

    @staticmethod
    def decisions(preview):
        return [
            {
                "ecomm_id": row["ecomm_id"],
                "draft_id": row["draft_id"],
                "expected_revision": row["revision"],
                "expected_workspace_version": row["workspace_version"],
                "decisions": {
                    "title": {
                        "decision": "ACCEPTED",
                        "value": row["fields"]["title"]["value"],
                    }
                },
            }
            for row in preview["items"]
        ]

    def test_twenty_existing_proposals_review_save_draft_and_reopen_with_history(self):
        from sqlalchemy.orm import Session
        from app.services.documental.commercial_review import CommercialReview
        from app.services.ecomm_api_product_workspace_service import (
            EcommApiProductWorkspace,
        )

        with Session(self.engine) as db:
            self.seed(db, 20)
            for ident in self.ids:
                self.proposal(db, ident)
            service = CommercialReview(db, self.actor)
            preview = service.preview(self.ids)
            self.assertEqual(preview["total"], 20)
            self.assertTrue(
                all(row["state"] == "REVIEW_REQUIRED" for row in preview["items"])
            )
            self.no_editor_writes(db)
            result = service.apply(
                preview["fingerprint"], self.decisions(preview), self.ids
            )
            db.commit()
            self.assertEqual(result["total"], 20)
            self.assertTrue(
                all(row["state"] == "SAVED_DRAFT" for row in result["items"])
            )
            self.assertFalse(result["external_writes_enabled"])
        with Session(self.engine) as db:
            for ident in self.ids:
                edit = EcommApiProductWorkspace(db).get(ident)
                self.assertEqual(edit["status"], "DRAFT")
                self.assertEqual(edit["version"], 1)
                self.assertEqual(len(edit["history"]), 1)
                self.assertTrue(edit["fields"]["title"])
                self.assertFalse(edit["readiness"]["ready"])

    def test_stale_editor_or_revoked_evidence_never_overwritten_by_batch(self):
        from sqlalchemy.orm import Session
        from app.services.documental.commercial_review import CommercialReview
        from app.services.documental.research import Research
        from app.services.ecomm_api_product_workspace_service import (
            EcommApiProductWorkspace,
            blank_fields,
        )

        with Session(self.engine) as db:
            self.seed(db, 2)
            for ident in self.ids[:2]:
                self.proposal(db, ident)
            preview = CommercialReview(db, self.actor).preview(self.ids[:2])
            fields = blank_fields()
            fields["note"] = "Cambio concurrente del operador de prueba; preservar."
            EcommApiProductWorkspace(db).save(self.ids[1], fields, "DRAFT", 0)
            with self.assertRaises(ValueError):
                CommercialReview(db, self.actor).apply(
                    preview["fingerprint"], self.decisions(preview), self.ids[:2]
                )
            db.rollback()
            self.assertEqual(
                EcommApiProductWorkspace(db).get(self.ids[0])["version"], 0
            )
            self.assertEqual(
                EcommApiProductWorkspace(db).get(self.ids[1])["fields"]["note"],
                fields["note"],
            )
            research = Research(db, self.actor)
            dossier = research.dossier(self.ids[0])
            fact = dossier.facts[0]
            research.review(
                self.ids[0],
                dossier.version,
                fact["id"],
                fact["version"],
                "REJECTED",
                "Revocación explícita SINTÉTICA para demostrar bloqueo de la propuesta anterior.",
            )
            db.commit()
            fresh = CommercialReview(db, self.actor).preview(self.ids[:2])
            self.assertTrue(all(row["state"] == "BLOCKED" for row in fresh["items"]))

    def test_twenty_taxonomy_decisions_are_persisted_atomically_without_editor_writes(
        self,
    ):
        from sqlalchemy.orm import Session
        from app.services.documental.taxonomy_review import TaxonomyReview

        with Session(self.engine) as db:
            self.seed(db, 20)
            catalog = self.catalog(db)
            service = TaxonomyReview(db, self.actor)
            preview = service.preview_batch(self.ids)
            decisions = []
            for row in preview["items"]:
                decisions.append(
                    {
                        "ecomm_id": row["ecomm_id"],
                        "expected_version": row["expected_version"],
                        "expected_workspace_version": row["expected_workspace_version"],
                        "expected_fingerprint": row["evidence_fingerprint"],
                        "decision": "APPROVED",
                        "taxonomy_revision": catalog["revision"],
                        "target_category": "Dietética de prueba",
                        "target_subcategory": "Legumbres de prueba",
                        "reason": "Revisión explícita SINTÉTICA de taxonomía por variante, no aprobación auténtica.",
                        "catalog_version": catalog["version"],
                        "catalog_pair_id": "legumbres",
                    }
                )
            result = service.review_batch(
                ids=self.ids,
                channel="KIKI",
                expected_selection_fingerprint=preview["selection_fingerprint"],
                decisions=decisions,
            )
            self.assertEqual(result["total"], 20)
            self.assertTrue(all(row["state"] == "APPROVED" for row in result["items"]))
            self.no_editor_writes(db)
        with Session(self.engine) as db:
            service = TaxonomyReview(db, self.actor)
            for ident in self.ids:
                state = service.get(ident)
                self.assertEqual(state["mapping_version"], 1)
                self.assertEqual(state["state"], "APPROVED")
                self.assertEqual(len(state["history"]), 1)

    def test_bulk_review_replay_and_simultaneous_operators_save_only_once(self):
        from sqlalchemy.orm import Session
        from app.services.documental.commercial_review import CommercialReview
        from app.services.ecomm_api_product_workspace_service import (
            EcommApiProductWorkspace,
        )

        with Session(self.engine) as db:
            self.seed(db, 2)
            for ident in self.ids[:2]:
                self.proposal(db, ident)
            preview = CommercialReview(db, self.actor).preview(self.ids[:2])
            decisions = self.decisions(preview)
            db.rollback()  # release preview locks before real separate operators
        barrier = Barrier(2)

        def apply():
            with Session(self.engine) as db:
                barrier.wait(timeout=10)
                try:
                    CommercialReview(db, self.actor).apply(
                        preview["fingerprint"], decisions, self.ids[:2]
                    )
                    db.commit()
                    return "saved"
                except ValueError:
                    db.rollback()
                    return "conflict"

        with ThreadPoolExecutor(max_workers=2) as pool:
            result = list(pool.map(lambda _: apply(), range(2)))
        self.assertEqual(sorted(result), ["conflict", "saved"])
        with Session(self.engine) as db:
            with self.assertRaises(ValueError):
                CommercialReview(db, self.actor).apply(
                    preview["fingerprint"], decisions, self.ids[:2]
                )
            db.rollback()  # lost-response replay cannot duplicate the original save
            for ident in self.ids[:2]:
                edit = EcommApiProductWorkspace(db).get(ident)
                self.assertEqual(edit["version"], 1)
                self.assertEqual(len(edit["history"]), 1)

    def test_late_batch_failure_rolls_back_prior_field_reviews_and_editor_saves(self):
        from unittest.mock import patch
        from sqlalchemy import select
        from sqlalchemy.orm import Session
        from app.database.models import KikiAiEditorialDraft
        from app.services.documental.proposals import Proposals
        from app.services.documental.commercial_review import CommercialReview
        from app.services.ecomm_api_product_workspace_service import (
            EcommApiProductWorkspace,
        )

        with Session(self.engine) as db:
            self.seed(db, 2)
            for ident in self.ids[:2]:
                self.proposal(db, ident)
            preview = CommercialReview(db, self.actor).preview(self.ids[:2])
            initial = {
                row.id: deepcopy(row.history)
                for row in db.scalars(select(KikiAiEditorialDraft))
            }
            original = Proposals.apply

            def fail_second(service, ident, *args, **kwargs):
                if ident == self.ids[1]:
                    raise ValueError(
                        "Injected fixture-only failure after first draft save"
                    )
                return original(service, ident, *args, **kwargs)

            with patch.object(Proposals, "apply", fail_second):
                with self.assertRaises(ValueError):
                    CommercialReview(db, self.actor).apply(
                        preview["fingerprint"], self.decisions(preview), self.ids[:2]
                    )
                db.rollback()  # same atomic boundary as the authenticated API route
            for ident in self.ids[:2]:
                self.assertEqual(EcommApiProductWorkspace(db).get(ident)["version"], 0)
            for row in db.scalars(select(KikiAiEditorialDraft)):
                self.assertEqual(row.history, initial[row.id])
                self.assertEqual(row.review_status, "PENDING_REVIEW")
            self.no_editor_writes(db)

    def test_channel_packages_remain_blocked_without_rights_or_taxonomy_and_reject_source_drift(
        self,
    ):
        from sqlalchemy.orm import Session
        from app.services.documental.storage import Document, digest
        from app.services.commercial_channel_export_service import (
            preview_commercial_export,
            download_commercial_export,
        )
        from app.services.ecomm_api_product_workspace_service import (
            blank_fields,
            EcommApiProductWorkspace,
        )

        with Session(self.engine) as db:
            docid = self.seed(db)[0]
            proposal = self.proposal(db, self.ids[0])
            fields = blank_fields()
            fields.update(
                {key: row["value"] for key, row in proposal["fields"].items()}
            )
            fields["media"] = [self.media()]
            EcommApiProductWorkspace(db).save(self.ids[0], fields, "DRAFT", 0)
            for channel in ("ml", "tn"):
                preview = preview_commercial_export(
                    db, self.actor, channel, self.ids[:1]
                )
                self.assertEqual(preview["blocked"], 1)
                self.assertEqual(preview["prepared_internal"], 0)
                row = preview["items"][0]
                self.assertEqual(row["state"], "BLOCKED")
                self.assertFalse(row["publication_enabled"])
                self.assertNotEqual(row["internal_taxonomy"]["state"], "APPROVED")
                self.assertFalse(preview["external_writes_enabled"])
            old = preview["preview_fingerprint"]
            doc = db.get(Document, docid)
            doc.version += 1
            doc.body = {**doc.body, "version": doc.version}
            doc.digest = digest(doc.body)
            db.commit()
            with self.assertRaises(ValueError):
                download_commercial_export(db, self.actor, "tn", self.ids[:1], old)
            db.rollback()
            self.assertEqual(
                EcommApiProductWorkspace(db).get(self.ids[0])["version"], 1
            )

    def test_periodic_policy_persists_cas_and_tasks_do_not_change_facts_or_editor(self):
        from sqlalchemy.orm import Session
        from app.services.monthly_catalog_reports import (
            review_policy,
            save_review_policy,
            preview_periodic_review,
        )
        from app.services.documental.storage import Dossier

        with Session(self.engine) as db:
            self.seed(db)
            original = deepcopy(db.get(Dossier, self.ids[0]).facts)
            policy = review_policy(db)
            save_review_policy(
                db,
                self.actor,
                expected_version=0,
                settings={
                    **policy["settings"],
                    "interval_days": 14,
                    "evidence_max_age_days": 7,
                },
                reason="Configuración explícita SINTÉTICA de revisión, sin aprobación comercial.",
            )
            with self.assertRaises(ValueError):
                save_review_policy(
                    db,
                    self.actor,
                    expected_version=0,
                    settings=policy["settings"],
                    reason="Solicitud antigua que no debe reemplazar otra decisión.",
                )
            db.rollback()
            preview = preview_periodic_review(db)
            self.assertEqual(preview["total_variants"], 20)
            self.assertEqual(preview["reason_counts"]["INCOMPLETE_FICHE"], 20)
            self.assertEqual(preview["reason_counts"]["UNREVIEWED_PRODUCT"], 20)
            self.assertEqual(preview["commercial_changes"], 0)
            self.assertEqual(db.get(Dossier, self.ids[0]).facts, original)
            self.no_editor_writes(db)
        with Session(self.engine) as db:
            self.assertEqual(review_policy(db)["settings"]["interval_days"], 14)
            self.assertEqual(review_policy(db)["editorial_signoff_max_days"], 30)

    def test_integral_twenty_api_variants_mock_search_actual_import_and_pending_citations(
        self,
    ):
        from sqlalchemy.orm import Session
        from app.services.documental.catalog_automation import CatalogAutomation
        from app.services.documental.storage import Document, Dossier
        from integration_sandbox.ci_stage3_pipeline_smoke import (
            HOST,
            MockManufacturer,
            source_url,
            synthetic_page,
        )

        ids = self.ids
        calls = []

        class Search:
            def search(self, identity):
                calls.append(identity["ecomm_id"])
                return {
                    "provider": "SYNTHETIC-PG18-SEARCH",
                    "queried_at": datetime.now(timezone.utc).isoformat(),
                    "results": [
                        {
                            "url": source_url(identity["ecomm_id"]),
                            "title": "Referencia FICTICIA PG18",
                            "snippet": "No es evidencia aprobada",
                            "source_kind": "OFFICIAL_CANDIDATE",
                            "official_verified": False,
                        }
                    ],
                }

        http = MockManufacturer(
            {
                f"/producto/{ident}/": synthetic_page(
                    f"Lentejas prueba {index} 250 g", "250 g"
                )
                for index, ident in enumerate(ids, 1)
            }
        )
        with Session(self.engine) as db:
            created = CatalogAutomation(
                db, self.actor, Search(), HOST, network_enabled=True
            ).create(str(uuid4()), ids)
            jobid = created["id"]
        for index, ident in enumerate(ids, 1):
            with Session(self.engine) as db:
                service = CatalogAutomation(
                    db, self.actor, Search(), HOST, network_enabled=True
                )
                before = service.detail(jobid)
                result = service.step(
                    jobid, before["revision"], explicit_importer=http.import_exact
                )
                self.assertEqual(result["counts"]["IMPORTED"], index)
                row = next(row for row in result["items"] if row["ecomm_id"] == ident)
                self.assertEqual(row["public_state"], "EVIDENCE_REVIEW_REQUIRED", row)
                doc = db.get(Document, row["document_id"])
                self.assertEqual(doc.body["source"]["review_state"], "PENDING")
                self.assertEqual(
                    doc.body["retrieval"]["selection_mode"],
                    "AUTOMATED_SEARCH_CANDIDATE",
                )
                facts = db.get(Dossier, ident).facts
                self.assertTrue(facts)
                self.assertTrue(
                    all(
                        f["state"] == "PENDING" and f["reviewer"] is None for f in facts
                    )
                )
                self.assertTrue(
                    all(
                        f["quote"] in doc.body["sections"][f["location"]] for f in facts
                    )
                )
                self.no_editor_writes(db)
        self.assertEqual(sorted(calls), ids)
        self.assertEqual(len(http.calls), 40)
        self.assertEqual(result["search_requests"], 20)
        with Session(self.engine) as db:
            service = CatalogAutomation(
                db, self.actor, Search(), HOST, network_enabled=True
            )
            with self.assertRaises(ValueError):
                service.step(
                    jobid, created["revision"], explicit_importer=http.import_exact
                )
            db.rollback()
            self.assertEqual(len(calls), 20)
            self.assertEqual(len(http.calls), 40)
            listing = service.listing()
            self.assertEqual(len(listing["items"]), 1)
            self.assertEqual(listing["items"][0]["id"], jobid)

    def test_integral_approved_existing_original_reuses_deterministic_proposal_and_never_writes_fiche(
        self,
    ):
        from sqlalchemy.orm import Session
        from app.services.documental.catalog_automation import CatalogAutomation
        from app.database.models import KikiAiEditorialDraft
        from sqlalchemy import select, func

        class NoSearch:
            def search(self, _identity):
                raise AssertionError(
                    "Fresh archived original must not be researched again"
                )

        with Session(self.engine) as db:
            self.seed(db)
            service = CatalogAutomation(
                db, self.actor, NoSearch(), "fabricante-e4.invalid"
            )
            job = service.create(str(uuid4()), self.ids[:1])
            self.assertTrue(job["items"][0]["automation"]["reused_original"])
            result = service.step(job["id"], job["revision"])
            row = result["items"][0]
            self.assertEqual(row["public_state"], "PROPOSAL_REVIEW_REQUIRED", row)
            draftid = row["automation"]["proposal"]["draft_id"]
            self.assertEqual(
                db.get(KikiAiEditorialDraft, draftid).review_status, "PENDING_REVIEW"
            )
            again = service.prepare_proposals(job["id"], result["revision"])
            self.assertEqual(
                again["items"][0]["automation"]["proposal"]["draft_id"], draftid
            )
            self.assertEqual(
                db.scalar(select(func.count()).select_from(KikiAiEditorialDraft)), 1
            )
            self.no_editor_writes(db)

    def test_global_daily_search_reservation_cas_for_two_preclaimed_postgresql_jobs(
        self,
    ):
        from sqlalchemy.orm import Session
        from app.services.documental.catalog_automation import CatalogAutomation
        from app.services.documental.source_intake_storage import SourceIntakeJob
        from app.services.documental.source_intake_pipeline import PipelineError

        calls = []

        class Search:
            def search(self, identity):
                calls.append(identity["ecomm_id"])
                return {
                    "provider": "SYNTHETIC",
                    "results": [],
                    "queried_at": "2026-11-28T12:00:00+00:00",
                }

        claims = []
        with Session(self.engine) as db:
            for ident in self.ids[:2]:
                service = CatalogAutomation(
                    db,
                    self.actor,
                    Search(),
                    "fabricante-e4.invalid",
                    network_enabled=True,
                    daily_search_limit=1,
                )
                job = service.create(str(uuid4()), [ident])
                record = db.get(SourceIntakeJob, job["id"])
                rows = deepcopy(record.items)
                token = str(uuid4())
                # Adversarial two-preclaimed recovery fixture: the ordinary
                # queue already permits only one active provider step. Test
                # the quota mutex independently in case leases preexist.
                rows[0].update(state="RUNNING", claim_token=token, attempts=1)
                record.items = rows
                db.commit()
                claims.append((record.id, ident, token))
        barrier = Barrier(2)

        def reserve(claim):
            with Session(self.engine) as db:
                service = CatalogAutomation(
                    db,
                    self.actor,
                    Search(),
                    "fabricante-e4.invalid",
                    network_enabled=True,
                    daily_search_limit=1,
                )
                barrier.wait(timeout=10)
                try:
                    service._resolve(*claim)
                except PipelineError as error:
                    db.rollback()
                    return error.code

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(reserve, claims))
        self.assertEqual(
            sorted(outcomes), ["GLOBAL_SEARCH_DAILY_BUDGET", "NO_AUTHORIZED_SOURCE"]
        )
        self.assertEqual(len(calls), 1)
        with Session(self.engine) as db:
            self.no_editor_writes(db)

    def test_periodic_runner_two_process_ticks_and_restart_do_not_duplicate_or_sign_off(
        self,
    ):
        from sqlalchemy import select, func
        from sqlalchemy.orm import sessionmaker
        from app.database.models import CatalogSnapshot
        from app.services.periodic_review_runner import PeriodicReviewRunner, SOURCE
        from app.services.documental.storage import Dossier

        config = SimpleNamespace(
            kiki_monthly_review_enabled=True,
            kiki_v2_enabled=True,
            kiki_editorial_executor_enabled=True,
        )
        factory = sessionmaker(bind=self.engine, expire_on_commit=False)
        with factory() as db:
            self.seed(db)
            facts = deepcopy(db.get(Dossier, self.ids[0]).facts)
        barrier = Barrier(2)

        def tick(_):
            runner = PeriodicReviewRunner(factory, config=config)
            barrier.wait(timeout=10)
            return runner.tick()["state"]

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(tick, range(2)))
        self.assertEqual(results.count("COMPLETED_DIAGNOSTIC"), 1)
        self.assertTrue(
            all(
                state in {"COMPLETED_DIAGNOSTIC", "BUSY", "THROTTLED", "NOT_DUE"}
                for state in results
            ),
            results,
        )
        restarted = PeriodicReviewRunner(factory, config=config).tick()
        self.assertIn(restarted["state"], {"THROTTLED", "NOT_DUE"})
        with factory() as db:
            self.assertEqual(
                db.scalar(
                    select(func.count())
                    .select_from(CatalogSnapshot)
                    .where(CatalogSnapshot.source.startswith("KIKI_MONTHLY:"))
                ),
                1,
            )
            archived = db.scalar(
                select(CatalogSnapshot).where(
                    CatalogSnapshot.source.startswith("KIKI_MONTHLY:")
                )
            ).payload[0]
            self.assertIsNone(archived["human_acknowledgement"])
            self.assertTrue(archived["created_by"].startswith("SYSTEM_AUTOMATION"))
            ledger = db.scalar(
                select(CatalogSnapshot).where(CatalogSnapshot.source == SOURCE)
            ).payload[0]
            self.assertEqual(len(ledger["tasks"]), 20)
            self.assertEqual(len(ledger["history"]), 1)
            self.assertEqual(ledger["human_acknowledgements_created"], 0)
            self.assertEqual(db.get(Dossier, self.ids[0]).facts, facts)
            self.no_editor_writes(db)

    def test_periodic_original_reconfirmation_matches_exact_pg_json_receipt(self):
        from sqlalchemy.orm import Session
        from app.services.documental.storage import Document, Dossier, digest
        from app.services.monthly_catalog_reports import preview_periodic_review

        with Session(self.engine) as db:
            docid = self.seed(db)[0]
            document = db.get(Document, docid)
            old = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
            document.body = {
                **document.body,
                "source": {**document.body["source"], "reviewed_at": old},
            }
            document.digest = digest(document.body)
            db.commit()
            before = preview_periodic_review(db)
            self.assertEqual(before["reason_counts"]["EVIDENCE_EXPIRED"], 1)
            item = db.get(Dossier, self.ids[0])
            facts = deepcopy(item.facts)
            event = {
                "action": "PROVENANCE_RECONFIRMED",
                "at": datetime.now(timezone.utc).isoformat(),
                "actor": "SYNTHETIC-PG18-TEST-REVIEWER",
                "detail": {
                    "document_id": docid,
                    "document_version": document.version,
                    "document_hash": document.digest,
                    "decision": "REVIEWED",
                },
            }
            item.history = [*item.history, event]
            item.version += 1
            db.commit()
            after = preview_periodic_review(db)
            self.assertEqual(after["reason_counts"]["EVIDENCE_EXPIRED"], 0)
            self.assertEqual(db.get(Dossier, self.ids[0]).facts, facts)
            self.assertEqual(document.body["source"]["reviewed_at"], old)
            self.no_editor_writes(db)

    def test_integral_periodic_same_and_changed_html_refresh_exact_original_pg(self):
        from sqlalchemy.orm import Session
        from app.services.documental.catalog_automation import CatalogAutomation
        from app.services.documental.storage import Document, Dossier, digest
        from app.services.documental.research import Research
        from integration_sandbox.ci_stage3_pipeline_smoke import (
            HOST,
            MockManufacturer,
            source_url,
            synthetic_page,
        )

        class Search:
            def search(self, identity):
                return {
                    "provider": "SYNTHETIC",
                    "results": [
                        {
                            "url": source_url(identity["ecomm_id"]),
                            "source_kind": "OFFICIAL_CANDIDATE",
                        }
                    ],
                }

        for index, changed in enumerate((False, True), 1):
            ident = self.ids[index - 1]
            content = synthetic_page(f"Lentejas prueba {index} 250 g", "250 g")
            http = MockManufacturer({f"/producto/{ident}/": content})
            with Session(self.engine) as db:
                service = CatalogAutomation(
                    db, self.actor, Search(), HOST, network_enabled=True
                )
                initial = service.create(str(uuid4()), [ident])
                acquired = service.step(
                    initial["id"],
                    initial["revision"],
                    explicit_importer=http.import_exact,
                )
                doc = db.get(Document, acquired["items"][0]["document_id"])
                body = deepcopy(doc.body)
                old = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
                body["source"].update(registered_at=old, declared_consulted_at=old)
                body["retrieval"]["acquired_at"] = old
                doc.body = body
                doc.digest = digest(body)
                db.commit()
                # Artificially aging metadata changes its digest in this
                # fixture; refresh stale facts before the next CAS capture.
                Research(db, self.actor).dossier(ident)
                db.commit()
                previous = doc.version
                pending = service.create(str(uuid4()), [ident])
                self.assertEqual(
                    pending["items"][0]["automation"]["phase"], "REFRESH_REQUIRED"
                )
                if changed:
                    http.pages[f"/producto/{ident}/"] += (
                        b"<!-- FICTITIOUS changed original -->"
                    )
                result = service.step(
                    pending["id"],
                    pending["revision"],
                    explicit_importer=http.import_exact,
                )
                row = result["items"][0]
                self.assertEqual(row["processing"]["phase"], "EXTRACTED", row)
                current = db.get(Document, row["document_id"])
                self.assertEqual(current.version, previous + int(changed))
                self.assertEqual(len(http.calls), 4)
                self.assertTrue(
                    all(f["state"] != "APPROVED" for f in db.get(Dossier, ident).facts)
                )
                reused = service.create(str(uuid4()), [ident])
                self.assertTrue(reused["items"][0]["automation"]["reused_original"])
                self.no_editor_writes(db)

    def test_workspace_strong_orm_reference_cannot_overwrite_a_concurrent_version(self):
        from sqlalchemy import select
        from sqlalchemy.orm import Session
        from app.database.models import EcommApiProductEdit
        from app.services.ecomm_api_product_workspace_service import (
            EcommApiProductWorkspace,
            blank_fields,
        )

        fields = blank_fields()
        fields["note"] = "Primer borrador sintético"
        with Session(self.engine) as db:
            EcommApiProductWorkspace(db).save(self.ids[0], fields, "DRAFT", 0)
        with Session(self.engine, expire_on_commit=False) as stale:
            held = stale.scalar(
                select(EcommApiProductEdit).where(
                    EcommApiProductEdit.ecomm_id == self.ids[0]
                )
            )
            self.assertEqual(held.version, 1)
            with Session(self.engine) as newer:
                updated = {**fields, "note": "Cambio concurrente que debe preservarse"}
                EcommApiProductWorkspace(newer).save(self.ids[0], updated, "DRAFT", 1)
            with self.assertRaises(ValueError):
                EcommApiProductWorkspace(stale).save(self.ids[0], fields, "DRAFT", 1)
            stale.rollback()
            restored = EcommApiProductWorkspace(stale).get(self.ids[0])
            self.assertEqual(restored["version"], 2)
            self.assertEqual(restored["fields"]["note"], updated["note"])

    def test_ready_documentary_guard_and_bulk_editor_share_lock_order_without_deadlock(
        self,
    ):
        from concurrent.futures import ThreadPoolExecutor
        from unittest.mock import patch
        from sqlalchemy import select
        from sqlalchemy.orm import Session
        from app.database.models import EcommApiProductEdit
        from app.services.ecomm_api_product_workspace_service import (
            EcommApiProductWorkspace,
            blank_fields,
        )
        from app.services.documental.storage import Document
        from app.services.documental.research import Research
        from app.services.documental.proposals import Proposals
        from app.services.documental.commercial_review import CommercialReview
        import app.services.documental.channel_readiness_guard as gate

        ident = self.ids[0]
        with Session(self.engine) as db:
            docid = self.seed(db)[0]
            Proposals(db, self.actor).generate(ident, 0)
            fields = blank_fields()
            generated, _ = Proposals.generate_fields(
                Research(db, self.actor).dossier(ident).facts
            )
            fields.update({key: row["value"] for key, row in generated.items()})
            fields["media"] = [self.media()]
            fields["sources"] = [
                {
                    "kind": "FABRICANTE",
                    "name": "Fuente FICTICIA PG18",
                    "url": self.media()["source_url"],
                    "verified": True,
                    "note": "Comprobación sintética explícita para probar mutex; no aceptación comercial real.",
                }
            ]
            EcommApiProductWorkspace(db).save(ident, fields, "DRAFT", 0)
            research = Research(db, self.actor)
            item = research.dossier(ident)
            document = db.get(Document, docid)
            extracted = research.extract(ident, item.version, docid, document.version)
            for candidate in extracted["facts"]:
                item = research.dossier(ident)
                fact = next(row for row in item.facts if row["id"] == candidate["id"])
                if fact["state"] != "APPROVED":
                    research.review(
                        ident,
                        item.version,
                        fact["id"],
                        fact["version"],
                        "APPROVED",
                        "Revisión SINTÉTICA de nueva identidad editorial para comprobar el orden transaccional.",
                    )
            self.rights(research, document, self.media())
            db.commit()
            Proposals(db, self.actor).generate(ident, 1)
            preview = CommercialReview(db, self.actor).preview([ident])
            choices = self.decisions(preview)
            db.rollback()
        editor_held, guard_obtained_control = Event(), Event()
        original = gate.require_primary_evidence

        def guarded(*args, **kwargs):
            result = original(*args, **kwargs)
            guard_obtained_control.set()
            return result

        def bulk():
            with Session(self.engine) as db:
                db.scalar(
                    select(EcommApiProductEdit)
                    .where(EcommApiProductEdit.ecomm_id == ident)
                    .with_for_update()
                )
                editor_held.set()
                # With the correct order the READY request waits for this row
                # before Control, so this bounded wait expires, then both finish.
                # Reversed Control→editor order creates a genuine PG deadlock.
                guard_obtained_control.wait(timeout=0.5)
                CommercialReview(db, self.actor).apply(
                    preview["fingerprint"], choices, [ident]
                )
                db.commit()
                return "bulk"

        def ready():
            if not editor_held.wait(timeout=5):
                raise AssertionError("Fixture editor lock was not obtained")
            with Session(self.engine) as db:
                saved = EcommApiProductWorkspace(db).save(
                    ident, fields, "READY_FOR_CHANNELS", 1, session=self.actor
                )
                self.assertEqual(saved["version"], 2)
                return "ready"

        with patch.object(gate, "require_primary_evidence", guarded):
            with ThreadPoolExecutor(max_workers=2) as pool:
                first, second = pool.submit(bulk), pool.submit(ready)
                self.assertEqual(
                    {first.result(timeout=15), second.result(timeout=15)},
                    {"bulk", "ready"},
                )
        with Session(self.engine) as db:
            saved = EcommApiProductWorkspace(db).get(ident)
            self.assertEqual(saved["status"], "READY_FOR_CHANNELS")
            self.assertEqual(saved["version"], 2)
            self.assertEqual(saved["fields"], fields)

    def test_twenty_cached_variants_preflight_sql_cost_with_3200_api_variants(self):
        from time import perf_counter
        from sqlalchemy import event, select
        from sqlalchemy.orm import Session
        from app.database.models import CatalogSnapshot
        from app.services.documental.catalog_automation import CatalogAutomation

        class NoSearch:
            def search(self, _identity):
                raise AssertionError(
                    "Performance acceptance is offline; no search authorized"
                )

        measured = []
        with Session(self.engine) as db:
            self.seed(db, 20)

            def measure(label):
                statements = []

                def sql_seen(_connection, _cursor, statement, _params, _context, _many):
                    if statement.lstrip().upper().startswith("SELECT"):
                        statements.append(statement)

                event.listen(self.engine, "before_cursor_execute", sql_seen)
                started = perf_counter()
                try:
                    result = CatalogAutomation(
                        db, self.actor, NoSearch(), "fabricante-e4.invalid"
                    ).create(str(uuid4()), self.ids)
                finally:
                    elapsed = perf_counter() - started
                    event.remove(self.engine, "before_cursor_execute", sql_seen)
                self.assertEqual(result["total"], 20)
                self.assertEqual(
                    {row["ecomm_id"] for row in result["items"]}, set(self.ids)
                )
                self.assertTrue(
                    all(row["automation"]["reused_original"] for row in result["items"])
                )
                self.assertEqual(result["search_requests"], 0)
                measured.append((len(statements), elapsed))
                print(
                    f"PG18 PERF {label}: selected=20 SELECTs={len(statements)} seconds={elapsed:.3f} provider_calls=0",
                    flush=True,
                )

            measure("catalogue=20")
            stage = db.scalar(
                select(CatalogSnapshot).where(
                    CatalogSnapshot.source == "ECOMM_APP_API_STAGE"
                )
            )
            template = captured_variants(3200)[0]
            self.capture = [
                {
                    **template,
                    "page": index + 1,
                    "total_pages": 64,
                    "items": template["items"][index * 50 : (index + 1) * 50],
                }
                for index in range(64)
            ]
            stage.payload = deepcopy(self.capture)
            db.commit()
            measure("catalogue=3200")
            self.assertEqual(measured[0][0], measured[1][0])
            self.no_editor_writes(db)

    def test_ml_official_validation_positive_204_pg_ledger_replay_without_editor_or_token_change(
        self,
    ):
        """Real PG ledger/client, fake official HTTP and reviewed preview DTO.

        This isolates validation execution/CAS, not the strict documentary
        export gate already exercised by the other PostgreSQL cases. No real
        account, price, stock, licence, publication or vendor call is asserted.
        """
        from unittest.mock import patch
        from sqlalchemy import select, func
        from sqlalchemy.orm import Session
        from app.database.models import ImportJobRecord, MercadoLibreConnection
        from app.integrations.mercadolibre.client import MercadoLibreClient
        from app.integrations.mercadolibre.transport import Response
        from app.services import mercadolibre_official_validation as official
        from app.services.ecomm_api_product_workspace_service import (
            EcommApiProductWorkspace,
            blank_fields,
        )

        ident = self.ids[0]
        actor = SimpleNamespace(id=1)  # Synthetic authenticated-session shape.
        settings = SimpleNamespace(
            kiki_ml_official_validation_enabled=True,
            kiki_v2_writes_enabled=True,
            ml_api_url="https://api.mercadolibre.com",
        )
        review = {
            "preview_fingerprint": "a" * 64,
            "items": [
                {
                    "blockers": [],
                    "channel_taxonomy": {
                        "target_pair": {"category": "Alimentos", "subcategory": "Arroz"}
                    },
                    "field_evidence": {},
                    "commercial_fields": {
                        "title": "Arroz FICTICIO 250 g",
                        "media": [
                            {
                                "kind": "IMAGE",
                                "url": "https://fabricante-e4.invalid/fixture.png",
                            }
                        ],
                    },
                }
            ],
        }

        class FakeHTTP:
            def __init__(self):
                self.calls = []

            def request(self, method, url, *, headers=None, data=None):
                self.calls.append((method, url))
                if method == "GET" and url.endswith("/users/me"):
                    return Response(200, {"id": 123})
                if method == "GET" and url.endswith("/categories/MLA1400/attributes"):
                    return Response(200, [])
                if method == "GET" and url.endswith("/categories/MLA1400"):
                    return Response(
                        200,
                        {
                            "id": "MLA1400",
                            "path_from_root": [
                                {"name": "Alimentos"},
                                {"name": "Arroz"},
                            ],
                        },
                    )
                if (
                    method == "POST"
                    and url == "https://api.mercadolibre.com/items/validate"
                ):
                    return Response(204, {})
                raise AssertionError(
                    "OAuth, writes and unrelated URLs are forbidden in this fixture"
                )

        class Factory:
            def __call__(self, _db):
                return self

            def _client(self, _connection):
                return MercadoLibreClient(
                    settings, "SYNTHETIC-NOT-A-REAL-ML-TOKEN", transport=FakeHTTP()
                )

            def _run(self, *_args, **_kwargs):
                raise AssertionError("No automatic OAuth refresh")

            def _refresh(self, *_args, **_kwargs):
                raise AssertionError("No token refresh")

        http = FakeHTTP()
        with patch.object(
            official, "preview_commercial_export", lambda *_a, **_k: deepcopy(review)
        ):
            with Session(self.engine) as db:
                fields = blank_fields()
                fields["note"] = (
                    "Borrador SINTÉTICO preservado durante validación ML del test"
                )
                before = EcommApiProductWorkspace(db).save(ident, fields, "DRAFT", 0)
                db.add(
                    MercadoLibreConnection(
                        id=1,
                        user_id="123",
                        access_token="SYNTHETIC-ENCRYPTED-FIXTURE-ONLY",
                        refresh_token="SYNTHETIC-REFRESH-NEVER-USED",
                        expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
                        connected_at=datetime.now(timezone.utc),
                        updated_at=datetime.now(timezone.utc),
                    )
                )
                db.commit()
                connection = db.get(MercadoLibreConnection, 1)
                credentials = (
                    connection.access_token,
                    connection.refresh_token,
                    connection.expires_at,
                )
                prepared = official.prepare(
                    db,
                    actor,
                    settings,
                    request_key=str(uuid4()),
                    ecomm_id=ident,
                    parameters={
                        "seller_id": "123",
                        "category_id": "MLA1400",
                        "price": 1234.5,
                        "currency_id": "ARS",
                        "available_quantity": 1,
                        "condition": "new",
                        "buying_mode": "buy_it_now",
                        "listing_type_id": "gold_special",
                        "attributes": [],
                    },
                    reason="Parámetros FICTICIOS de ensayo; sólo validar con transporte local, nunca publicar.",
                )
                self.assertEqual(prepared["state"], "PREVIEW")
                receipt = official.validate(
                    db,
                    actor,
                    settings,
                    prepared["id"],
                    expected_revision=prepared["revision"],
                    expected_preview_fingerprint=prepared["preview_fingerprint"],
                    confirm=True,
                    service_factory=Factory(),
                    transport=http,
                )
                self.assertEqual(receipt["state"], "VALIDATED")
                self.assertTrue(receipt["official_payload_validated"])
                self.assertFalse(receipt["publication_created"])
                self.assertEqual(receipt["provider_calls"], 4)
            with Session(self.engine) as db:
                # A fresh session/restart replays the persisted result without
                # another validation POST or OAuth work.
                replay = official.validate(
                    db,
                    actor,
                    settings,
                    prepared["id"],
                    expected_revision=prepared["revision"],
                    expected_preview_fingerprint=prepared["preview_fingerprint"],
                    confirm=True,
                    service_factory=Factory(),
                    transport=http,
                )
                self.assertEqual(replay["state"], "VALIDATED")
                self.assertEqual(len(http.calls), 4)
                self.assertEqual(
                    [method for method, _url in http.calls],
                    ["GET", "GET", "GET", "POST"],
                )
                self.assertTrue(http.calls[-1][1].endswith("/items/validate"))
                self.assertEqual(
                    db.scalar(
                        select(func.count())
                        .select_from(ImportJobRecord)
                        .where(ImportJobRecord.source == official.SOURCE)
                    ),
                    1,
                )
                ledger = db.get(ImportJobRecord, prepared["id"])
                self.assertNotIn(
                    "SYNTHETIC-NOT-A-REAL-ML-TOKEN", str(ledger.diagnostics)
                )
                self.assertEqual(ledger.status, "VALIDATED")
                after = EcommApiProductWorkspace(db).get(ident)
                self.assertEqual(
                    (after["version"], after["fields"], after["history"]),
                    (before["version"], before["fields"], before["history"]),
                )
                current = db.get(MercadoLibreConnection, 1)
                self.assertEqual(
                    (current.access_token, current.refresh_token, current.expires_at),
                    credentials,
                )


def main(argv=None):
    global MODE, TARGET
    args = list(sys.argv[1:] if argv is None else argv)
    if args not in ([], ["--local-synthetic"]):
        raise SystemExit("Only --local-synthetic is supported; no arbitrary DB target")
    MODE, TARGET = checked_mode(os.environ, local=bool(args))
    _network_guard(MODE)
    with _connect(MODE) as checked:
        print(
            "PG18 stage4 synthetic database verified:",
            checked.execute("SHOW server_version").fetchone()[0],
            flush=True,
        )
    outcome = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(Stage4Commercial)
    )
    if not outcome.wasSuccessful():
        raise SystemExit(1)
    print(
        "Stage4 PG18 PASS: isolated schemas removed; fabricated originals and explicit TEST decisions only; 0 provider calls, 0 paid AI, 0 publications.",
        flush=True,
    )


if __name__ == "__main__":
    main()
