from copy import deepcopy
from datetime import datetime, timezone
import re
from sqlalchemy import select
from app.core.config import get_settings
from app.database.models import EcommApiProductEdit
from app.services.ecomm_api_product_workspace_service import EcommApiProductWorkspace
from .documents import BRAND, MANUFACTURER, FIXTURES, REQUIRED, LABELS
from .storage import Control, Document, Dossier, digest


def now():
    return datetime.now(timezone.utc).isoformat()


def fact_digest(fact):
    return digest(
        {
            key: fact.get(key)
            for key in (
                "field",
                "commercial_field",
                "value",
                "unit",
                "presentation",
                "document_id",
                "document_version",
                "document_hash",
                "identity_hash",
                "location",
                "quote",
            )
        }
    )


class Research:
    def __init__(self, db, session):
        self.db = db
        self.actor = (
            f"{get_settings().kiki_admin_username} · sesión de prueba {session.id}"
        )
        # One transaction mutex for this small test schema. All reads/revisions use it.
        if db.scalar(select(Control).where(Control.id == 1).with_for_update()) is None:
            raise RuntimeError(
                "Falta el control transaccional de investigación; operación bloqueada."
            )

    def reference(self, ident):
        source = EcommApiProductWorkspace(self.db)._source(ident)
        edit = self.db.scalar(
            select(EcommApiProductEdit).where(EcommApiProductEdit.ecomm_id == ident)
        )
        fields = edit.fields if edit else {}
        return {
            "ecomm_id": ident,
            "name": source["product_name"],
            "sku": source["sku"],
            "presentation": source["variant_description"],
            "is_combo": source["is_combo"],
            "ean": source["gtin"]
            or fields.get("proposed_gtin")
            or {"900001": "12345670", "900002": "12345685"}.get(ident),
            "brand": fields.get("brand") or BRAND,
            "manufacturer": fields.get("manufacturer") or MANUFACTURER,
            "editorial_presentation": fields.get("presentation") or None,
            "provenance": {
                "name": "Captura Ecomm-App sintética",
                "presentation": "Captura Ecomm-App sintética",
                "ean": "Captura Ecomm-App sintética"
                if source["gtin"]
                else "Propuesta KIKI no verificada"
                if fields.get("proposed_gtin")
                else "Referencia sintética del fixture (no dato de Ecomm-App)",
                "brand": "Campo KIKI no verificado"
                if fields.get("brand")
                else "Referencia sintética del fixture",
                "manufacturer": "Campo KIKI no verificado"
                if fields.get("manufacturer")
                else "Referencia sintética del fixture",
            },
        }

    @staticmethod
    def identity_issues(reference, body):
        issues = []
        for key, label in [
            ("name", "Nombre"),
            ("presentation", "Presentación"),
            ("ean", "EAN"),
            ("brand", "Marca"),
            ("manufacturer", "Fabricante"),
        ]:
            expected, actual = reference.get(key), body["identity"].get(key)
            if expected and (
                not actual
                or str(expected).strip().casefold() != str(actual).strip().casefold()
            ):
                issues.append(
                    f"{label} incompatible o ausente: referencia «{expected}» / documento «{actual or 'sin datos'}»."
                )
        if (
            reference.get("editorial_presentation")
            and reference["editorial_presentation"] != reference["presentation"]
        ):
            issues.append(
                "La presentación editorial KIKI difiere de la captura Ecomm-App."
            )
        return issues

    def documents(self):
        return self.db.scalars(select(Document).order_by(Document.id)).all()

    def dossier(self, ident):
        item = self.db.get(Dossier, ident)
        try:
            reference = self.reference(ident)
        except ValueError:
            if item and any(f["state"] != "STALE" for f in item.facts):
                facts = deepcopy(item.facts)
                for fact in facts:
                    self.event(
                        fact,
                        "STALE",
                        "La variante no tiene identidad única disponible en la captura.",
                        "Sistema",
                        action="INVALIDATE_IDENTITY",
                    )
                self.commit_change(item, facts, "IDENTITY_UNAVAILABLE")
            raise
        if item is None:
            item = Dossier(
                ecomm_id=ident,
                version=0,
                identity=reference,
                identity_digest=digest(reference),
                facts=[],
                history=[],
            )
            self.db.add(item)
            self.db.flush()
        if item.identity_digest != digest(reference):
            facts = deepcopy(item.facts)
            for fact in facts:
                self.event(
                    fact,
                    "STALE",
                    "Cambió la identidad o referencia comercial de la variante.",
                    "Sistema",
                    action="INVALIDATE_IDENTITY",
                )
            previous = item.identity
            item.identity = reference
            item.identity_digest = digest(reference)
            self.commit_change(
                item,
                facts,
                "IDENTITY_CHANGED",
                {"before": previous, "after": reference},
            )
        self.refresh(item)
        return item

    def event(self, fact, state, reason, actor=None, *, action="REVIEW"):
        before = {
            key: deepcopy(value) for key, value in fact.items() if key != "history"
        }
        fact["version"] += 1
        fact["verification_digest"] = fact_digest(fact) if state == "APPROVED" else None
        fact.update(
            state=state,
            reviewer=self.actor
            if state in {"APPROVED", "REJECTED", "REVOKED"}
            else None,
            reviewed_at=now() if state in {"APPROVED", "REJECTED", "REVOKED"} else None,
        )
        fact["history"] = fact.get("history", []) + [
            {
                "at": now(),
                "actor": actor or self.actor,
                "triggered_by": self.actor,
                "action": action,
                "reason": reason,
                "version": fact["version"],
                "before": before,
                "after": {
                    key: deepcopy(value)
                    for key, value in fact.items()
                    if key != "history"
                },
            }
        ]

    def commit_change(self, item, facts, action, detail=None):
        item.version += 1
        item.facts = facts
        item.history = item.history + [
            {
                "at": now(),
                "actor": self.actor,
                "version": item.version,
                "action": action,
                "detail": detail,
            }
        ]
        self.db.flush()

    def blockers(self, item, fact, *, include_conflicts=True):
        doc = self.db.get(Document, fact["document_id"])
        issues = self.identity_issues(item.identity, doc.body)
        if (
            doc.version != fact["document_version"]
            or doc.digest != fact["document_hash"]
        ):
            issues.append(
                "El documento cambió. Extraé nuevamente los hechos de la versión actual."
            )
        if fact["identity_hash"] != item.identity_digest:
            issues.append(
                "La identidad cambió desde la extracción. Reextraé los hechos."
            )
        section = doc.body["sections"].get(fact["location"], "")
        claim = next(
            (
                claim
                for claim in doc.body["claims"]
                if claim["field"] == fact["field"]
                and claim["location"] == fact["location"]
            ),
            None,
        )
        if not claim or any(
            fact.get(key) != claim.get(key) for key in ("value", "unit", "presentation")
        ):
            issues.append(
                "La transcripción no coincide con el dato explícito del documento."
            )
        if fact["state"] == "APPROVED" and fact.get(
            "verification_digest"
        ) != fact_digest(fact):
            issues.append("Cambió el contenido de un hecho previamente verificado.")
        if not fact["quote"] or fact["quote"] not in section:
            issues.append(
                "El fragmento no está respaldado por esa ubicación del documento."
            )
        if not fact["value"] or not re.search(
            r"(?<!\w)" + re.escape(fact["value"]) + r"(?!\w)",
            fact["quote"],
            re.IGNORECASE,
        ):
            issues.append("El valor no aparece explícitamente en el fragmento.")
        if fact["field"].startswith("nutrition.") or fact["field"] == "net_weight":
            if (
                not fact["unit"]
                or fact["unit"].casefold() not in fact["quote"].casefold()
            ):
                issues.append(
                    "Falta una unidad explícita y respaldada por el documento."
                )
        if fact["presentation"] != item.identity["presentation"]:
            issues.append("La presentación del hecho no corresponde a la variante.")
        if include_conflicts:
            for other in item.facts:
                if (
                    other["id"] == fact["id"]
                    or other["field"] != fact["field"]
                    or other["state"] in {"REJECTED", "REVOKED"}
                ):
                    continue
                if not self.blockers(item, other, include_conflicts=False) and (
                    other["value"],
                    other["unit"],
                ) != (fact["value"], fact["unit"]):
                    issues.append(
                        f"Dato contradictorio en {other['document_id']}. Rechazá o resolvé el respaldo incompatible antes de aprobar."
                    )
        return issues

    def refresh(self, item):
        facts = deepcopy(item.facts)
        changed = False
        for fact in facts:
            doc = self.db.get(Document, fact["document_id"])
            reason = (
                "El documento cambió."
                if doc.version != fact["document_version"]
                or doc.digest != fact["document_hash"]
                else None
            )
            if fact["state"] == "APPROVED" and self.blockers(item, fact):
                reason = (
                    reason
                    or "El dato ahora tiene un respaldo incompatible o contradictorio."
                )
            if reason and fact["state"] != "STALE":
                self.event(fact, "STALE", reason, "Sistema", action="INVALIDATE")
                changed = True
        if changed:
            self.commit_change(item, facts, "EVIDENCE_INVALIDATED")

    @staticmethod
    def expect(item, version):
        if item.version != version:
            raise ValueError(
                "La investigación cambió en otra sesión o se invalidó evidencia. Recuperá la versión nueva antes de decidir."
            )

    def serialize(self, item):
        facts = []
        for original in item.facts:
            fact = deepcopy(original)
            fact["blockers"] = self.blockers(item, fact)
            if fact["state"] == "STALE":
                fact["blockers"].append(
                    "Verificación invalidada: reextraé y revisá el hecho."
                )
            fact["verified"] = fact["state"] == "APPROVED" and not fact["blockers"]
            fact["label"] = LABELS[fact["field"]]
            facts.append(fact)
        result = {
            "ecomm_id": item.ecomm_id,
            "version": item.version,
            "identity": item.identity,
            "facts": facts,
            "history": item.history,
            "missing": [
                LABELS[key]
                for key in REQUIRED
                if not any(f["field"] == key and f["verified"] for f in facts)
            ],
            "documents": [
                {
                    "id": doc.id,
                    "version": doc.version,
                    "hash": doc.digest,
                    "body": doc.body,
                    "issues": self.identity_issues(item.identity, doc.body),
                    "versions": [v["version"] for v in FIXTURES[doc.id]],
                    "history": doc.history,
                }
                for doc in self.documents()
            ],
            "synthetic_only": True,
            "external_writes_enabled": False,
            "commercial_fields_applied": False,
        }
        self.db.commit()
        return result

    def extract(self, ident, expected_version, document_id, document_version):
        item = self.dossier(ident)
        self.expect(item, expected_version)
        doc = self.db.get(Document, document_id)
        if not doc or doc.version != document_version:
            raise ValueError("La versión del documento cambió o no existe.")
        facts = deepcopy(item.facts)
        changed = False
        for claim in doc.body["claims"]:
            key = digest(
                {"ecomm_id": ident, "document_id": document_id, "field": claim["field"]}
            )[:24]
            candidate = {
                **claim,
                "id": key,
                "ecomm_id": ident,
                "document_id": document_id,
                "document_version": doc.version,
                "document_hash": doc.digest,
                "identity_hash": item.identity_digest,
                "consulted_at": now(),
                "provenance": doc.body["provenance"],
            }
            existing = next((fact for fact in facts if fact["id"] == key), None)
            same = existing and all(
                existing.get(k) == v
                for k, v in candidate.items()
                if k != "consulted_at"
            )
            if same and existing["state"] != "STALE":
                continue
            if existing:
                before = {
                    key: deepcopy(value)
                    for key, value in existing.items()
                    if key != "history"
                }
                existing.update(candidate)
                self.event(
                    existing,
                    "PENDING",
                    "Nueva extracción documental, sin aprobación automática.",
                    action="EXTRACT",
                )
                existing["history"][-1]["before"] = before
            else:
                existing = {
                    **candidate,
                    "version": 0,
                    "history": [],
                    "state": "PENDING",
                    "reviewer": None,
                    "created_by": self.actor,
                }
                self.event(
                    existing,
                    "PENDING",
                    "Extracción determinista de un documento sintético.",
                    action="EXTRACT",
                )
                facts.append(existing)
            changed = True
        if changed:
            self.commit_change(
                item,
                facts,
                "EXTRACT",
                {"document_id": doc.id, "document_version": doc.version},
            )
            self.refresh(item)
        return self.serialize(item)

    def review(
        self, ident, expected_version, fact_id, expected_fact_version, decision, reason
    ):
        if len(reason.strip()) < 10:
            raise ValueError(
                "Registrá un motivo de revisión de al menos 10 caracteres reales."
            )
        item = self.dossier(ident)
        self.expect(item, expected_version)
        facts = deepcopy(item.facts)
        fact = next((f for f in facts if f["id"] == fact_id), None)
        if not fact or fact["version"] != expected_fact_version:
            raise ValueError(
                "La versión de la evidencia cambió. No se sobrescribió la decisión."
            )
        if decision == "APPROVED" and (
            fact["state"] == "STALE" or self.blockers(item, fact)
        ):
            raise ValueError(
                "No se puede aprobar evidencia insuficiente, contradictoria o invalidada."
            )
        self.event(fact, decision, reason)
        self.commit_change(
            item,
            facts,
            "REVIEW",
            {"fact_id": fact_id, "decision": decision, "reason": reason},
        )
        self.refresh(item)
        return self.serialize(item)

    def revise_document(self, document_id, expected_version, new_version):
        doc = self.db.get(Document, document_id)
        body = next(
            (v for v in FIXTURES.get(document_id, []) if v["version"] == new_version),
            None,
        )
        if (
            not doc
            or doc.version != expected_version
            or not body
            or new_version != doc.version + 1
        ):
            raise ValueError(
                "Revisión documental inexistente o versión desactualizada."
            )
        doc.history = doc.history + [
            {
                "at": now(),
                "actor": self.actor,
                "version": doc.version,
                "body": doc.body,
                "hash": doc.digest,
            }
        ]
        doc.version, doc.body, doc.digest = new_version, deepcopy(body), digest(body)
        self.db.flush()
        for item in self.db.scalars(select(Dossier).order_by(Dossier.ecomm_id)):
            self.refresh(item)
        self.db.commit()
        return {"document_id": doc.id, "version": doc.version, "synthetic_only": True}
