"""Human taxonomy decisions in the existing, versioned documentary history.

These are operator-reviewed classification mappings, not manufacturer claims
or remotely verified category IDs. No new catalog, schema or provider writes.
"""

from copy import deepcopy

from sqlalchemy import select, func, cast, Text

from app.database.models import EcommApiProductEdit
from app.services.ecomm_api_product_workspace_service import EcommApiProductWorkspace
from .research import Research, fact_digest
from .storage import Dossier, digest
from .taxonomy_alignment import _key

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


def evidence_fingerprint(inspection):
    expected = inspection.get("expected") or {}
    return digest(
        {
            "identity": expected.get("identity_hash"),
            "workspace_version": expected.get("workspace_version"),
            "facts": expected.get("facts") or [],
            "documents": expected.get("documents") or [],
            "source_pair": _source_pair(inspection),
        }
    )


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
        or inspection.get("stale")
        or not _source_pair(inspection)
    )
    state = "NONE"
    if record:
        state = record["decision"]
        if record.get("ecomm_id") != inspection.get("ecomm_id"):
            state = "STALE"
        elif record.get("evidence_fingerprint") != evidence_fingerprint(inspection):
            state = "STALE"
        elif blocked and state == "APPROVED":
            state = "BLOCKED"
    return {
        "state": state,
        "channel": channel,
        "mapping_version": len(decisions),
        "record": deepcopy(record),
        "source_pair": _source_pair(inspection),
        "can_approve": not blocked,
        "evidence_fingerprint": evidence_fingerprint(inspection),
        "official_external_category_verified": False,
        "external_category_ids": None,
        "editorial_fields_applied": False,
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
        research, item, edit, inspected = self._context(ident)
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
        if decision == "REVOKED" and (
            not current["record"] or current["record"]["decision"] != "APPROVED"
        ):
            raise ValueError("No existe clasificación aprobada para revocar.")
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
                fact["evidence_id"] for fact in inspected["approved_taxonomy"]
            ),
            "evidence_fingerprint": current["evidence_fingerprint"],
            "identity_hash": item.identity_digest,
            "workspace_version": edit["version"],
            "reviewer": research.actor,
            "review_kind": "HUMAN_EXPLICIT",
            "reason": reason.strip(),
            "official_external_category_verified": False,
            "external_category_ids": None,
        }
        if decision == "REVOKED":
            for key in (
                "taxonomy_revision",
                "source_pair",
                "target_pair",
                "evidence_ids",
            ):
                record[key] = deepcopy(current["record"][key])
        research.commit_change(item, deepcopy(item.facts), EVENT, record)
        result = self._serialize(item, edit, inspected, channel)
        self.db.commit()
        return result
