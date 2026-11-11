"""Bounded bulk data access for the existing documental rules; no provider imports."""

from copy import deepcopy
from types import SimpleNamespace
from sqlalchemy import select, cast, func, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import defer
from app.database.models import CatalogSnapshot, EcommApiProductEdit
from app.integrations.ecomm_app.api_catalog_browser import (
    api_variant_row,
    valid_variant_id,
)
from app.integrations.ecomm_app.catalog_stage import STAGE_SOURCE, stage_status
from app.services.ecomm_api_product_workspace_service import EcommApiProductWorkspace
from app.services.documental.research import Research, identity_digest, fact_digest
from app.services.documental.proposals import Proposals
from app.services.documental.storage import Control, Document, Dossier, digest
from app.core.config import get_settings


class AtomicSession:
    """Only a bounded worker owns commit; legacy service commits become flushes."""

    def __init__(self, db):
        self.db = db

    def commit(self):
        self.db.flush()

    def __getattr__(self, key):
        return getattr(self.db, key)


def sources(db, lock=False):
    stmt = select(CatalogSnapshot).where(CatalogSnapshot.source == STAGE_SOURCE)
    if lock:
        stmt = stmt.with_for_update(read=True)
    record = db.scalar(stmt.execution_options(populate_existing=True))
    pages = record.payload if record else []
    quality = stage_status(pages)
    if not quality["complete"] or quality["quality"]["duplicate_variant_ids"]:
        raise ValueError("Captura API incompleta o con identidades duplicadas.")
    result = {}
    for page in pages:
        for parent in page.get("items") or []:
            for variant in parent.get("variants") or []:
                ident = str(variant.get("id"))
                if variant.get("invalid") or not valid_variant_id(ident):
                    continue
                result[ident] = {
                    **api_variant_row(parent, variant, page.get("captured_at")),
                    "ecomm_id": ident,
                    "sku": str(variant.get("sku") or "").strip(),
                    "product_name": str(parent.get("description") or "").strip(),
                    "variant_description": variant.get("variant_description")
                    or variant.get("description"),
                    "is_combo": variant.get("is_combo"),
                    "gtin": variant.get("gtin") or variant.get("barcode"),
                }
    return result


class Context:
    """At most 100 variants and a configured bytes budget per context.

    Document originals and document/fact histories never cross the DB boundary.
    Rules/citations run on the unchanged current document sections and facts.
    """

    def __init__(self, db, ids, source_map, byte_limit, *, lock=False):
        if len(ids) > 100:
            raise ValueError("Contexto demasiado grande.")
        # Budget before ORM materialization, including potentially long histories.
        for model, columns in (
            (
                EcommApiProductEdit,
                [EcommApiProductEdit.fields, EcommApiProductEdit.history],
            ),
            (Dossier, [Dossier.facts]),
        ):
            size = db.scalar(
                select(
                    func.coalesce(
                        func.sum(
                            sum(func.octet_length(cast(c, Text)) for c in columns)
                        ),
                        0,
                    )
                ).where(model.ecomm_id.in_(ids))
            )
            if size > byte_limit:
                raise ValueError(
                    "La ficha o su historial supera el presupuesto del paso; revisar individualmente."
                )
        self.source_map = source_map
        stmt = select(EcommApiProductEdit).where(EcommApiProductEdit.ecomm_id.in_(ids))
        if lock:
            stmt = stmt.order_by(EcommApiProductEdit.ecomm_id).with_for_update()
        self.edits = {
            x.ecomm_id: x
            for x in db.scalars(stmt.execution_options(populate_existing=True))
        }
        self.dossiers = {
            x.ecomm_id: x
            for x in db.scalars(
                select(Dossier)
                .options(defer(Dossier.history))
                .where(Dossier.ecomm_id.in_(ids))
            )
        }
        # JSONB subtraction is performed in PostgreSQL, before reading large PDFs.
        body = cast(Document.body, JSONB).op("-")("original_base64")
        docs = select(
            Document.id, Document.version, Document.digest, body.label("body")
        ).where(Document.body["associated_ecomm_id"].as_string().in_(ids))
        self.documents = {}
        budget = 0
        import json

        for row in db.execute(
            docs.execution_options(stream_results=True, max_row_buffer=1)
        ):
            budget += len(json.dumps(row.body, ensure_ascii=False).encode())
            if budget > byte_limit:
                raise ValueError(
                    "Documentación excede el presupuesto de contexto; revisar individualmente."
                )
            self.documents[row.id] = SimpleNamespace(
                id=row.id, version=row.version, digest=row.digest, body=row.body
            )
        budget += sum(
            len(json.dumps(d.facts, ensure_ascii=False).encode())
            for d in self.dossiers.values()
        )
        budget += sum(
            len(json.dumps(e.fields, ensure_ascii=False).encode())
            for e in self.edits.values()
        )
        if budget > byte_limit:
            raise ValueError(
                "Contexto editorial excede el límite; reducir selección o revisar individualmente."
            )
        # Existing versioned writer remains the only commercial persistence.
        if db.scalar(select(Control).where(Control.id == 1).with_for_update()) is None:
            raise ValueError("Falta el control documental; operación bloqueada.")
        context = self

        class Workspace(EcommApiProductWorkspace):
            def _source(self, ident):
                source = context.source_map.get(ident)
                if not source or not source["sku"]:
                    raise ValueError("Variante ausente o sin SKU en la captura API.")
                return source

            def get(self, ident):
                return self._serialize(context.edits.get(ident), self._source(ident))

        class BulkResearch(Research):
            workspace_type = Workspace

            def __init__(self, db, session):
                self.db = db
                self.actor = (
                    f"{get_settings().kiki_admin_username} · sesión {session.id}"
                )
                self._document_refs = context.documents

            def edit_record(self, ident):
                return context.edits.get(ident)

            def source_record(self, ident):
                return Workspace(self.db)._source(ident)

            def _document(self, ident):
                # A missing document cannot silently become valid evidence.
                if ident not in context.documents:
                    raise ValueError(
                        "Documento original asociado no disponible para esta variante."
                    )
                return context.documents[ident]

        class BulkProposals(Proposals):
            workspace_type = Workspace
            research_type = BulkResearch

            def lock_edit(self, ident):
                # Context already locks all selected commercial rows, then Research.Control.
                pass

        self.Workspace, self.Research, self.Proposals = (
            Workspace,
            BulkResearch,
            BulkProposals,
        )

    def inspect(self, db, session, ident):
        research = self.Research(AtomicSession(db), session)
        edit = self.Workspace(db).get(ident)
        reference = research.reference(ident)
        identity = identity_digest(reference)
        dossier = self.dossiers.get(ident)
        case = SimpleNamespace(
            ecomm_id=ident,
            identity=reference,
            identity_digest=identity,
            facts=deepcopy(dossier.facts) if dossier else [],
        )
        approved, issues = [], []
        revoked = any(f["state"] == "REVOKED" for f in case.facts)
        changed = False
        for fact in case.facts:
            doc = self.documents.get(fact["document_id"])
            changed |= bool(
                not doc
                or doc.version != fact["document_version"]
                or doc.digest != fact["document_hash"]
            )
            if fact["state"] == "APPROVED":
                blockers = research.blockers(case, fact)
                if blockers:
                    issues.extend(blockers)
                else:
                    approved.append({k: v for k, v in fact.items() if k != "history"})
        generated, missing = self.Proposals.generate_fields(approved)
        generated = {k: v for k, v in generated.items() if not edit["fields"].get(k)}
        identity_conflict = edit["source_sku_changed"] or bool(
            edit["source"].get("identity_blockers")
        )
        expected = {
            "workspace_version": edit["version"],
            "dossier_version": dossier.version if dossier else 0,
            "identity_hash": identity,
            "facts": sorted((f["id"], f["version"], fact_digest(f)) for f in approved),
            "documents": sorted(
                (d.id, d.version, d.digest)
                for d in self.documents.values()
                if d.body.get("associated_ecomm_id") == ident
            ),
        }
        return {
            "expected": expected,
            "fingerprint": digest(expected),
            "sufficient_evidence": bool(approved),
            "no_documentation": not any(
                d.body.get("sections") and d.body.get("associated_ecomm_id") == ident
                for d in self.documents.values()
            ),
            "conflicts": bool(identity_conflict or issues),
            "stale": bool(
                changed
                or edit["review_schedule"]["review_due"]
                or (dossier and dossier.identity_digest != identity)
            ),
            "eligible": bool(
                generated
                and approved
                and not identity_conflict
                and not issues
                and not changed
            ),
            "human_required": True,
            "revoked": revoked,
            "documents_changed": changed,
            "fields_without_support": [
                k for k, v in edit["fields"].items() if not v and k not in generated
            ],
            "reasons": list(dict.fromkeys(issues))[:12],
            "review_schedule": edit["review_schedule"],
            "name": reference["name"],
            "presentation": reference["presentation"],
            "is_combo": reference["is_combo"],
            "missing": missing,
        }
