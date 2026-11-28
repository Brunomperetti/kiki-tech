"""Human, atomic review of up to twenty existing evidence-backed proposals.

No generator, new jobs, approvals of facts, channel writes or new persistence.
The original proposal reviewer and versioned editor own validation and history.
"""

from copy import deepcopy
from types import SimpleNamespace

from sqlalchemy import select, func, cast, Text

from app.core.config import get_settings
from app.database.models import KikiAiEditorialDraft
from app.integrations.ecomm_app.api_catalog_browser import valid_variant_id
from app.services.editorial_batches.context import Context, AtomicSession, sources
from .proposals import Proposals, MODEL, AI_MODEL
from .storage import digest

MAX_ITEMS = 20


def selection(ids):
    if (
        not isinstance(ids, list)
        or not 1 <= len(ids) <= MAX_ITEMS
        or any(not isinstance(ident, str) or not valid_variant_id(ident) for ident in ids)
        or len(set(ids)) != len(ids)
    ):
        raise ValueError("Seleccioná entre 1 y 20 variantes API diferentes.")
    return sorted(ids)


class CommercialReview:
    context_type = Context
    source_loader = staticmethod(sources)

    def __init__(self, db, session):
        self.db, self.session = db, session

    def _context(self, ids, *, lock):
        ids = selection(ids)
        catalog = self.source_loader(self.db, lock=lock)
        if any(ident not in catalog for ident in ids):
            raise ValueError("Una variante ya no está en la captura API completa.")
        context = self.context_type(
            self.db, ids, catalog, get_settings().kiki_editorial_context_bytes,
            lock=lock,
        )
        return ids, context

    def _drafts(self, ids):
        # Only the latest proposal of the established generators, never historical
        # Excel identities or a prior draft substituted for an applied latest one.
        keys = [Proposals.product_prefix + ident for ident in ids]
        latest = select(func.max(KikiAiEditorialDraft.id)).where(
            KikiAiEditorialDraft.product_key.in_(keys),
            KikiAiEditorialDraft.model.in_((MODEL, AI_MODEL)),
        ).group_by(KikiAiEditorialDraft.product_key)
        lengths = func.octet_length(cast(KikiAiEditorialDraft.history, Text))
        if self.db.bind.dialect.name == "sqlite":
            lengths = func.length(cast(KikiAiEditorialDraft.history, Text)) * 4
        size = self.db.scalar(select(func.coalesce(func.sum(lengths), 0)).where(
            KikiAiEditorialDraft.id.in_(latest)
        ))
        if size > get_settings().kiki_editorial_context_bytes:
            raise ValueError("Las propuestas exceden el límite; reducí la selección.")
        return {
            row.product_key.removeprefix(Proposals.product_prefix): row
            for row in self.db.scalars(select(KikiAiEditorialDraft).where(
                KikiAiEditorialDraft.id.in_(latest)
            ).execution_options(populate_existing=True))
        }

    def _preview(self, ids, context):
        service = context.Proposals(AtomicSession(self.db), self.session)
        drafts = self._drafts(ids)
        rows, pins = [], []
        for ident in ids:
            edit, dossier, facts, fingerprint = service.context(ident)
            record = drafts.get(ident)
            reasons, fields = [], {}
            meta = service.meta(record) if record else {}
            if record:
                reasons = service.validity(record, edit, dossier, fingerprint)
                if record.review_status not in {"PENDING_REVIEW", "REVIEWED"}:
                    reasons.append("La propuesta requiere una nueva generación o ya fue guardada.")
                authorized = {f["id"] for f in facts}
                for key, proposal in meta["fields"].items():
                    cited = proposal.get("evidence_ids") or []
                    if not cited or not set(cited).issubset(authorized):
                        reasons.append("Hay campos sin citas aprobadas vigentes.")
                    fields[key] = {
                        **deepcopy(proposal),
                        "current": deepcopy(edit["fields"].get(key)),
                        "prior_decision": deepcopy((meta.get("decisions") or {}).get(key)),
                    }
            else:
                reasons.append("No hay propuesta: preparala desde el plan comercial con hechos aprobados.")
            pin = {
                "ecomm_id": ident,
                "identity": dossier.identity_digest,
                "workspace_version": edit["version"],
                "workspace_fields": edit["fields"],
                "evidence": fingerprint,
                "draft_id": record.id if record else None,
                "draft_revision": len(record.history) if record else None,
                "draft_state": record.review_status if record else None,
                "draft_meta": meta,
            }
            pins.append(pin)
            rows.append({
                "ecomm_id": ident,
                "sku": dossier.identity.get("sku"),
                "name": dossier.identity.get("name"),
                "presentation": dossier.identity.get("presentation"),
                "workspace_version": edit["version"],
                "status": edit["status"],
                "draft_id": pin["draft_id"],
                "revision": pin["draft_revision"],
                "state": "BLOCKED" if reasons else "REVIEW_REQUIRED",
                "reasons": list(dict.fromkeys(reasons)),
                "fields": fields,
                "evidence": [{
                    k: deepcopy(f.get(k)) for k in (
                        "id", "field", "value", "document_id", "document_version",
                        "location", "quote", "provenance", "state",
                    )
                } for f in facts],
            })
        return {
            "schema_version": "kiki-commercial-review-v1",
            "total": len(rows),
            "fingerprint": digest(pins),
            "items": rows,
            "internal_only": True,
            "external_writes_enabled": False,
            "facts_approved": 0,
            "provider_calls": 0,
            "publications": 0,
        }

    def preview(self, ids):
        ids, context = self._context(ids, lock=True)
        try:
            return self._preview(ids, context)
        finally:
            context.release()

    def apply(self, expected_fingerprint, items, scope_ids):
        item_ids = selection([row["ecomm_id"] for row in items])
        if not set(item_ids).issubset(selection(scope_ids)):
            raise ValueError("La revisión contiene variantes fuera de la previsualización.")
        ids, context = self._context(scope_ids, lock=True)
        try:
            preview = self._preview(ids, context)
            if expected_fingerprint != preview["fingerprint"]:
                raise ValueError("La ficha, evidencia o propuesta cambió. Volvé a comparar antes de guardar.")
            expected = {row["ecomm_id"]: row for row in preview["items"]}
            service = context.Proposals(AtomicSession(self.db), self.session)
            results = []
            # Validate every row before the first human review/write. A second
            # failure still rolls back the complete transaction in the route.
            for request in items:
                row = expected[request["ecomm_id"]]
                if row["state"] == "BLOCKED" or (
                    request["draft_id"] != row["draft_id"]
                    or request["expected_revision"] != row["revision"]
                    or request["expected_workspace_version"] != row["workspace_version"]
                ):
                    raise ValueError("Una propuesta dejó de ser revisable. No se guardó el lote.")
                decisions = request["decisions"]
                if not decisions or set(decisions) - set(row["fields"]):
                    raise ValueError("Seleccioná solo campos propuestos para esta variante.")
                for key, decision in decisions.items():
                    if decision["decision"] == "ACCEPTED":
                        service.validate_edit(key, decision["value"], row["fields"][key])
            for request in items:
                ident = request["ecomm_id"]
                row = expected[ident]
                decisions = request["decisions"]
                reviewed = service.review(ident, row["draft_id"], row["revision"], decisions)
                accepted = {
                    k: d["value"] for k, d in decisions.items()
                    if d["decision"] == "ACCEPTED"
                }
                if accepted:
                    fields = deepcopy(context.Workspace(self.db).get(ident)["fields"])
                    fields.update(accepted)
                    edit = service.apply(
                        ident, row["draft_id"], reviewed["revision"],
                        SimpleNamespace(
                            expected_version=row["workspace_version"], status="DRAFT",
                            fields=SimpleNamespace(model_dump=lambda value=fields: value),
                        ),
                    )
                    version, state = edit["version"], "SAVED_DRAFT"
                else:
                    version, state = row["workspace_version"], "REJECTED"
                results.append({
                    "ecomm_id": ident, "workspace_version": version,
                    "state": state, "fields_saved": sorted(accepted),
                })
            return {
                "schema_version": "kiki-commercial-review-result-v1",
                "items": results, "total": len(results),
                "internal_only": True, "external_writes_enabled": False,
                "facts_approved": 0, "provider_calls": 0, "publications": 0,
            }
        finally:
            context.release()
