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
from datetime import datetime, timezone
from hashlib import sha256
import os
import sys
from threading import Barrier
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
