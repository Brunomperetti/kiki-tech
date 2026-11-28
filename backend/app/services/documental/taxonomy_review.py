"""Human taxonomy decisions in the existing, versioned documentary history.

These are operator-reviewed classification mappings, not manufacturer claims
or remotely verified category IDs. No new catalog, schema or provider writes.
"""

from copy import deepcopy

from sqlalchemy import select, func, cast, Text

from app.database.models import EcommApiProductEdit
from app.core.config import get_settings
from app.services.ecomm_api_product_workspace_service import EcommApiProductWorkspace
from .research import Research, fact_digest
from .storage import Dossier, digest
from .taxonomy_alignment import _key, catalog_proposal
from .taxonomy_catalog import catalog_state, selected_pair

EVENT = "TAXONOMY_REVIEW"
CHANNELS = {"KIKI", "ECOMM", "ML", "TN"}


def _source_pair(inspection):
    grouped = {"category": {}, "subcategory": {}}
    for fact in inspection.get("approved_taxonomy") or []:
        field = fact.get("field")
        value = fact.get("value")
        if field in grouped and _key(value) and fact.get("evidence_id"):
            grouped[field][_key(value)] = value
    if not all(len(values) == 1 for values in grouped.values()):
        return None
    return {field: next(iter(values.values())) for field, values in grouped.items()}


def evidence_fingerprint(inspection, *, classification=False):
    expected = inspection.get("expected") or {}
    return digest(
        {
            "identity": expected.get("identity_hash"),
            "workspace_version": None
            if classification
            else expected.get("workspace_version"),
            "facts": expected.get("facts") or [],
            "documents": expected.get("documents") or [],
            "source_pair": _source_pair(inspection),
        }
    )


def classification_supported(inspection):
    """Human classification can cite name/size; it is not maker taxonomy."""
    if _source_pair(inspection):
        return True
    if inspection.get("approved_taxonomy"):
        return False
    grouped = {"product_name": set(), "presentation": set()}
    for fact in inspection.get("classification_evidence") or []:
        if (
            fact.get("field") in grouped
            and fact.get("evidence_id")
            and _key(fact.get("value"))
        ):
            grouped[fact["field"]].add(_key(fact["value"]))
    return all(len(values) == 1 for values in grouped.values())


def current_review(inspection, history, channel="KIKI"):
    if channel not in CHANNELS:
        raise ValueError("Canal de clasificación inválido.")
    decisions = [
        event.get("detail")
        for event in history or []
        if event.get("action") == EVENT
        and isinstance(event.get("detail"), dict)
        and event["detail"].get("channel") == channel
    ]
    record = decisions[-1] if decisions else None
    blocked = bool(
        inspection.get("conflicts")
        or inspection.get("classification_stale", inspection.get("stale"))
        or not classification_supported(inspection)
    )
    state = "NONE"
    if record:
        state = record["decision"]
        if state == "REVOKED":
            pass
        elif record.get("ecomm_id") != inspection.get("ecomm_id"):
            state = "STALE"
        elif record.get("evidence_fingerprint") != evidence_fingerprint(
            inspection, classification=bool(record.get("catalog_fingerprint"))
        ):
            state = "STALE"
        elif blocked and state == "APPROVED":
            state = "BLOCKED"
        if (
            state != "REVOKED"
            and record.get("catalog_fingerprint")
            and record["catalog_fingerprint"]
            != (inspection.get("taxonomy_catalog") or {}).get("fingerprint")
        ):
            state = "STALE"
    return {
        "state": state,
        "channel": channel,
        "mapping_version": len(decisions),
        "record": deepcopy(record),
        "source_pair": _source_pair(inspection),
        "can_approve": not blocked,
        "evidence_fingerprint": evidence_fingerprint(
            inspection,
            classification=bool(record and record.get("catalog_fingerprint")),
        ),
        "official_external_category_verified": False,
        "external_category_ids": None,
        "editorial_fields_applied": False,
        "catalog_bound": bool(record and record.get("catalog_fingerprint")),
        "review_required": state != "APPROVED",
        "classification_evidence": deepcopy(
            inspection.get("classification_evidence") or []
        ),
    }


def inspection_from_context(ident, item, edit, authorized, documents, catalog):
    """Reuse already checked source facts; never turn editor labels into facts."""
    return {
        "ecomm_id": ident,
        "conflicts": bool(
            edit.get("source_sku_changed")
            or edit.get("source", {}).get("identity_blockers")
        ),
        "stale": bool(edit.get("review_schedule", {}).get("review_due")),
        # Editing copy does not revoke a classification. Existing Research
        # authorization still rejects expired/revoked documents and facts.
        "classification_stale": False,
        "approved_taxonomy": [
            {"field": f["field"], "value": f["value"], "evidence_id": f["id"]}
            for f in authorized
            if f["field"] in {"category", "subcategory"}
        ],
        "classification_evidence": [
            {"field": f["field"], "value": f["value"], "evidence_id": f["id"]}
            for f in authorized
            if f["field"] in {"product_name", "presentation"}
        ],
        "taxonomy_catalog": catalog,
        "expected": {
            "identity_hash": item.identity_digest,
            "workspace_version": edit["version"],
            "facts": sorted(
                (f["id"], f["version"], fact_digest(f)) for f in authorized
            ),
            "documents": sorted((d.id, d.version, d.digest) for d in documents),
        },
    }


def histories_for(db, ids, *, byte_limit):
    """One bounded bulk read; history never creates a new taxonomy catalog."""
    import json

    lengths = func.octet_length(cast(Dossier.history, Text))
    if db.bind.dialect.name == "sqlite":
        lengths = func.length(cast(Dossier.history, Text)) * 4
    size = db.scalar(
        select(func.coalesce(func.sum(lengths), 0)).where(Dossier.ecomm_id.in_(ids))
    )
    if size > byte_limit:
        raise ValueError(
            "El historial de clasificación supera el límite; reducí la selección."
        )
    result, used = {}, 0
    for ident, history in db.execute(
        select(Dossier.ecomm_id, Dossier.history)
        .where(Dossier.ecomm_id.in_(ids))
        .execution_options(stream_results=True, max_row_buffer=1)
    ):
        used += len(json.dumps(history, ensure_ascii=False).encode())
        if used > byte_limit:
            raise ValueError(
                "El historial de clasificación supera el límite; reducí la selección."
            )
        result[ident] = history
    return result


class TaxonomyReview:
    research_type = Research
    workspace_type = EcommApiProductWorkspace

    def __init__(self, db, session):
        self.db, self.session = db, session

    def _context(self, ident):
        # Follow the editor/proposal lock ordering: editorial row, then Control.
        self.db.scalar(
            select(EcommApiProductEdit)
            .where(EcommApiProductEdit.ecomm_id == ident)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        research = self.research_type(self.db, self.session)
        item = research.dossier(ident)
        edit = self.workspace_type(self.db).get(ident)
        approved, blocked = [], False
        for fact in item.facts:
            if fact.get("state") == "APPROVED":
                issues = research.blockers(item, fact)
                blocked |= bool(issues)
                if not issues:
                    approved.append(fact)
        documents = research.documents(ident)
        inspection = {
            "ecomm_id": ident,
            "conflicts": blocked or edit["source_sku_changed"],
            "stale": bool(edit["review_schedule"]["review_due"]),
            "approved_taxonomy": [
                {
                    "field": fact["field"],
                    "value": fact["value"],
                    "evidence_id": fact["id"],
                }
                for fact in approved
                if fact["field"] in {"category", "subcategory"}
            ],
            "classification_evidence": [
                {
                    "field": fact["field"],
                    "value": fact["value"],
                    "evidence_id": fact["id"],
                }
                for fact in approved
                if fact["field"] in {"product_name", "presentation"}
            ],
            "expected": {
                "identity_hash": item.identity_digest,
                "workspace_version": edit["version"],
                "facts": sorted(
                    (fact["id"], fact["version"], fact_digest(fact))
                    for fact in approved
                ),
                "documents": sorted(
                    (doc.id, doc.version, doc.digest) for doc in documents
                ),
            },
            "taxonomy_catalog": catalog_state(self.db),
            "classification_stale": False,
        }
        return research, item, edit, inspection

    def get(self, ident, channel="KIKI"):
        _research, item, edit, inspected = self._context(ident)
        state = self._serialize(item, edit, inspected, channel)
        self.db.commit()
        return state

    @staticmethod
    def _serialize(item, edit, inspection, channel):
        return {
            "ecomm_id": item.ecomm_id,
            "expected_version": item.version,
            "expected_workspace_version": edit["version"],
            **current_review(inspection, item.history, channel),
            "history": [
                deepcopy(event)
                for event in item.history
                if event.get("action") == EVENT
                and (event.get("detail") or {}).get("channel") == channel
            ],
            "external_writes_enabled": False,
            "human_review_required": True,
        }

    def review(
        self,
        ident,
        *,
        expected_version,
        expected_workspace_version,
        expected_fingerprint,
        channel,
        decision,
        taxonomy_revision,
        target_category,
        target_subcategory,
        reason,
        catalog_version=None,
        catalog_pair_id=None,
        channel_mapping_id=None,
        _prepared=None,
        _commit=True,
    ):
        if channel not in CHANNELS or decision not in {"APPROVED", "REVOKED"}:
            raise ValueError("Decisión o canal de clasificación inválido.")
        for value, limit in (
            (taxonomy_revision, 100),
            (target_category, 160),
            (target_subcategory, 160),
            (reason, 600),
        ):
            if (
                not isinstance(value, str)
                or not value.strip()
                or len(value) > limit
                or any(ord(char) < 32 or ord(char) == 127 for char in value)
            ):
                raise ValueError(
                    "Revisión de clasificación incompleta o fuera de límites."
                )
        if len(reason.strip()) < 20:
            raise ValueError("Explicá la decisión con al menos 20 caracteres.")
        research, item, edit, inspected = _prepared or self._context(ident)
        research.expect(item, expected_version)
        if edit["version"] != expected_workspace_version:
            raise ValueError(
                "La ficha cambió; revisá la clasificación contra la versión actual."
            )
        current = current_review(inspected, item.history, channel)
        if expected_fingerprint != current["evidence_fingerprint"]:
            raise ValueError(
                "Cambió la evidencia o identidad; recuperá la revisión actual."
            )
        if decision == "APPROVED" and not current["can_approve"]:
            raise ValueError(
                "Faltan categorías documentales aprobadas y vigentes o hay conflictos."
            )
        if (
            decision == "APPROVED"
            and not current["source_pair"]
            and catalog_version is None
        ):
            raise ValueError(
                "La clasificación humana sin categoría de fabricante requiere un par del vocabulario interno versionado."
            )
        if (
            decision == "APPROVED"
            and current["catalog_bound"]
            and catalog_version is None
        ):
            raise ValueError(
                "La revisión está ligada al vocabulario; seleccioná su versión y par actuales."
            )
        if decision == "REVOKED" and (
            not current["record"] or current["record"]["decision"] != "APPROVED"
        ):
            raise ValueError("No existe clasificación aprobada para revocar.")
        catalog_binding = {}
        if catalog_version is not None or catalog_pair_id is not None:
            catalog = inspected.get("taxonomy_catalog") or {}
            if (
                type(catalog_version) is not int
                or catalog_version < 1
                or catalog_version != catalog.get("version")
            ):
                raise ValueError(
                    "El vocabulario cambió; recuperá la versión antes de revisar."
                )
            if decision == "APPROVED" and taxonomy_revision.strip() != catalog.get(
                "revision"
            ):
                raise ValueError(
                    "La revisión declarada no corresponde al vocabulario vigente."
                )
            internal, target = selected_pair(
                catalog, catalog_pair_id, channel, channel_mapping_id
            )
            if decision == "APPROVED" and target != {
                "category": target_category.strip(),
                "subcategory": target_subcategory.strip(),
            }:
                raise ValueError(
                    "La jerarquía no corresponde al par o equivalencia seleccionada."
                )
            if decision == "APPROVED" and channel != "KIKI":
                internal_review = current_review(inspected, item.history, "KIKI")
                if (
                    internal_review["state"] != "APPROVED"
                    or not internal_review["catalog_bound"]
                    or internal_review["record"].get("internal_pair_id")
                    != catalog_pair_id
                ):
                    raise ValueError(
                        "Revisá primero el par interno KIKI de esta variante; no se hereda de otra ficha."
                    )
            catalog_binding = {
                "catalog_version": catalog["version"],
                "catalog_fingerprint": catalog["fingerprint"],
                "internal_pair_id": catalog_pair_id,
                "internal_pair": internal,
                "channel_mapping_id": channel_mapping_id if channel != "KIKI" else None,
            }
        record = {
            "ecomm_id": ident,
            "channel": channel,
            "mapping_version": current["mapping_version"] + 1,
            "decision": decision,
            "taxonomy_revision": taxonomy_revision.strip(),
            "source_pair": current["source_pair"],
            "target_pair": {
                "category": target_category.strip(),
                "subcategory": target_subcategory.strip(),
            },
            "evidence_ids": sorted(
                {
                    fact["evidence_id"]
                    for fact in (
                        inspected["approved_taxonomy"]
                        + (
                            inspected.get("classification_evidence", [])
                            if catalog_binding
                            else []
                        )
                    )
                }
            ),
            "evidence_fingerprint": evidence_fingerprint(
                inspected,
                classification=bool(catalog_binding or current["catalog_bound"]),
            ),
            "identity_hash": item.identity_digest,
            "workspace_version": edit["version"],
            "reviewer": research.actor,
            "review_kind": "HUMAN_EXPLICIT",
            "reason": reason.strip(),
            "official_external_category_verified": False,
            "external_category_ids": None,
            **catalog_binding,
        }
        if decision == "REVOKED":
            for key in (
                "taxonomy_revision",
                "source_pair",
                "target_pair",
                "evidence_ids",
            ):
                record[key] = deepcopy(current["record"][key])
            for key in (
                "catalog_version",
                "catalog_fingerprint",
                "internal_pair_id",
                "internal_pair",
                "channel_mapping_id",
            ):
                if key in current["record"]:
                    record[key] = deepcopy(current["record"][key])
        research.commit_change(item, deepcopy(item.facts), EVENT, record)
        result = self._serialize(item, edit, inspected, channel)
        if _commit:
            self.db.commit()
        return result

    def preview_batch(
        self, ids, channel="KIKI", *, context_type=None, source_loader=None
    ):
        context, inspections, histories, catalog = self._batch_context(
            ids, channel, context_type, source_loader
        )
        try:
            rows = []
            for ident in ids:
                inspected = inspections[ident]
                item = context.dossiers.get(ident)
                current = current_review(inspected, histories.get(ident, []), channel)
                reason = None
                if not catalog["version"] or not any(
                    p["state"] == "ACTIVE" for p in catalog["entries"]
                ):
                    current["can_approve"] = False
                    reason = "Falta vocabulario interno activo revisado."
                if channel != "KIKI":
                    internal = current_review(
                        inspected, histories.get(ident, []), "KIKI"
                    )
                    if internal["state"] != "APPROVED" or not internal["catalog_bound"]:
                        current["can_approve"] = False
                        reason = "Falta clasificación KIKI vigente para esta variante."
                rows.append(
                    {
                        "ecomm_id": ident,
                        "expected_version": item.version if item else 0,
                        "expected_workspace_version": inspected["expected"][
                            "workspace_version"
                        ],
                        "name": inspected.get("name") or "",
                        **current,
                        "exception": None
                        if current["can_approve"]
                        else "REVIEW_REQUIRED",
                        "proposal": catalog_proposal(inspected, catalog, current),
                        "reason": reason
                        or (
                            "Falta evidencia aprobada de nombre y presentación o de categorías."
                            if not current["can_approve"]
                            else "Revisión humana individual requerida."
                        ),
                    }
                )
            result = {
                "mode": "TAXONOMY_BATCH_REVIEW",
                "channel": channel,
                "total": len(rows),
                "items": rows,
                "catalog": catalog,
                "external_writes_enabled": False,
                "automatic_approvals": 0,
            }
            result["selection_fingerprint"] = digest(
                {"channel": channel, "catalog": catalog["fingerprint"], "items": rows}
            )
            return result
        finally:
            context.release()

    def _batch_context(self, ids, channel, context_type=None, source_loader=None):
        from app.integrations.ecomm_app.api_catalog_browser import valid_variant_id
        from app.services.editorial_batches.context import Context, sources

        if (
            channel not in CHANNELS
            or not isinstance(ids, list)
            or not 1 <= len(ids) <= 20
            or len(set(ids)) != len(ids)
            or not all(isinstance(i, str) and valid_variant_id(i) for i in ids)
        ):
            raise ValueError("Revisá entre 1 y 20 Ecomm ID únicos y un canal válido.")
        source_loader, context_type = source_loader or sources, context_type or Context
        source = source_loader(self.db, lock=True)
        if any(ident not in source for ident in ids):
            raise ValueError("Una variante no está en la captura API completa actual.")
        context = context_type(
            self.db,
            sorted(ids),
            source,
            get_settings().kiki_editorial_context_bytes,
            lock=True,
        )
        try:
            history = histories_for(
                self.db, ids, byte_limit=get_settings().kiki_editorial_context_bytes
            )
            catalog = catalog_state(self.db)
            inspected = {}
            for ident in ids:
                row = context.inspect(self.db, self.session, ident)
                row.update(ecomm_id=ident, taxonomy_catalog=catalog)
                row["classification_stale"] = bool(
                    row.get("documents_changed")
                    or (
                        context.dossiers.get(ident)
                        and context.dossiers[ident].identity_digest
                        != row["expected"]["identity_hash"]
                    )
                )
                authorized_ids = {f[0] for f in row["expected"].get("facts", [])}
                dossier = context.dossiers.get(ident)
                row["classification_evidence"] = [
                    {"field": f["field"], "value": f["value"], "evidence_id": f["id"]}
                    for f in (dossier.facts if dossier else [])
                    if f["id"] in authorized_ids
                    and f["field"] in {"product_name", "presentation"}
                ]
                inspected[ident] = row
            return context, inspected, history, catalog
        except Exception:
            context.release()
            raise

    def review_batch(
        self,
        *,
        ids,
        channel,
        expected_selection_fingerprint,
        decisions,
        context_type=None,
        source_loader=None,
    ):
        if (
            not isinstance(ids, list)
            or not isinstance(decisions, list)
            or not decisions
            or not all(isinstance(d, dict) for d in decisions)
            or len(decisions) != len(ids)
            or {d.get("ecomm_id") for d in decisions} != set(ids)
            or len({d.get("ecomm_id") for d in decisions}) != len(decisions)
        ):
            raise ValueError(
                "El lote necesita una decisión explícita por cada variante, incluidas las excepciones."
            )
        required = {
            "ecomm_id",
            "decision",
            "expected_version",
            "expected_workspace_version",
            "expected_fingerprint",
            "taxonomy_revision",
            "target_category",
            "target_subcategory",
            "reason",
        }
        allowed = required | {
            "catalog_version",
            "catalog_pair_id",
            "channel_mapping_id",
        }
        for choice in decisions:
            if set(choice) - allowed or choice.get("decision") not in {
                "SKIP",
                "APPROVED",
                "REVOKED",
            }:
                raise ValueError(
                    "Decisión de lote inválida; no se admiten controles internos desde el cliente."
                )
            if choice["decision"] != "SKIP" and not required.issubset(choice):
                raise ValueError(
                    "Faltan controles de versión o respaldo para una decisión del lote."
                )
            if choice["decision"] == "APPROVED" and (
                type(choice.get("catalog_version")) is not int
                or not choice.get("catalog_pair_id")
            ):
                raise ValueError(
                    "Cada aprobación del lote requiere un par y versión del vocabulario interno."
                )
        preview = self.preview_batch(
            ids, channel, context_type=context_type, source_loader=source_loader
        )
        if preview["selection_fingerprint"] != expected_selection_fingerprint:
            raise ValueError(
                "Cambió la selección, evidencia o vocabulario; recuperá la previsualización."
            )
        context, inspections, histories, catalog = self._batch_context(
            ids, channel, context_type, source_loader
        )
        try:
            # Recheck under the same locks. Existing Control is held through commit.
            from sqlalchemy.orm.attributes import set_committed_value
            from app.services.editorial_batches.context import AtomicSession

            research = context.Research(AtomicSession(self.db), self.session)
            results = []
            for choice in decisions:
                ident = choice["ecomm_id"]
                if choice.get("decision") == "SKIP":
                    results.append(
                        {
                            "ecomm_id": ident,
                            "state": "SKIPPED",
                            "reason": choice.get("reason")
                            or "Excepción pendiente de revisión humana.",
                        }
                    )
                    continue
                item = context.dossiers.get(ident)
                if item is None:
                    raise ValueError(
                        "La variante requiere documentación antes de clasificar."
                    )
                set_committed_value(item, "history", histories.get(ident, []))
                inspection = inspections[ident]
                edit = context.Workspace(self.db).get(ident)
                results.append(
                    self.review(
                        ident,
                        **{k: v for k, v in choice.items() if k != "ecomm_id"},
                        channel=channel,
                        _prepared=(research, item, edit, inspection),
                        _commit=False,
                    )
                )
            self.db.commit()
            return {
                "mode": "TAXONOMY_BATCH_REVIEW",
                "total": len(results),
                "items": results,
                "external_writes_enabled": False,
                "automatic_approvals": 0,
            }
        except Exception:
            self.db.rollback()
            raise
        finally:
            context.release()
