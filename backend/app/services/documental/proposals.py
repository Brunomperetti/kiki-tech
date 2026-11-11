"""2F adapter: existing AI draft + existing commercial save, local deterministic only.

No provider injection/monkeypatch: the real EcommAiEditor.suggest remains disabled.
Rich proposal metadata lives in the existing draft history, not a second editor DB.
"""

from copy import deepcopy
from datetime import datetime
from sqlalchemy import select
from app.database.models import KikiAiEditorialDraft, EcommApiProductEdit
from app.services.ecomm_ai_editor_service import EcommAiEditor
from app.services.ecomm_api_product_workspace_service import (
    TEXT_LIMITS,
)
from app.services.ecomm_api_product_workspace_service import EcommApiProductWorkspace
from .research import Research, now, fact_digest
from .storage import digest
from .fields import LABELS

MODEL = "deterministic-reviewed-evidence-v1"
EVENT = "REVIEWED_EVIDENCE_PROPOSAL"
TEXT = {
    "width": "Ancho documentado",
    "nutrition.carbohydrates": "Hidratos de carbono",
    "nutrition.sugars": "Azúcares",
    "nutrition.total_fat": "Grasas totales",
    "nutrition.saturated_fat": "Grasas saturadas",
    "nutrition.fiber": "Fibra alimentaria",
    "nutrition.sodium": "Sodio",
    "certification": "Certificación declarada",
    "certification_evidence": "Respaldo documental de certificación",
    "ingredients": "Ingredientes",
    "allergens": "Alérgenos",
    "nutrition.energy": "Energía",
    "nutrition.protein": "Proteínas",
    "net_weight": "Contenido neto",
    "commercial_claim": "Declaración comercial",
    "storage_conditions": "Conservación",
    "characteristics": "Características verificables",
    "formulation": "Formulación",
}


class Proposals:
    research_type = Research
    workspace_type = EcommApiProductWorkspace
    model, event = MODEL, EVENT
    product_prefix = "ECOMM_DOCUMENTAL:"

    def before_generate(self, ident, facts):
        if not facts:
            raise ValueError(
                "Faltan hechos documentales aprobados vigentes; no se inventa una ficha."
            )

    def __init__(self, db, session):
        self.db = db
        self.research = self.research_type(
            db, session
        )  # same mutex as evidence/revocations
        self.workspace = self.workspace_type(db)

    def lock_edit(self, ident):
        # Serialize against existing commercial saves before checking their fields.
        self.db.scalar(
            select(EcommApiProductEdit)
            .where(EcommApiProductEdit.ecomm_id == ident)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    def context(self, ident):
        self.lock_edit(ident)
        item = self.research.dossier(ident)
        edit = self.workspace.get(ident)
        if edit["source_sku_changed"]:
            raise ValueError("La identidad de la ficha es incompatible.")
        authorized = [
            deepcopy(f)
            for f in item.facts
            if f["ecomm_id"] == ident
            and f["state"] == "APPROVED"
            and not self.research.blockers(item, f)
        ]
        for fact in authorized:
            fact.pop("history", None)
        fingerprint = digest(
            {
                "identity": item.identity_digest,
                "facts": sorted(
                    [(f["id"], f["version"], fact_digest(f)) for f in authorized]
                ),
            }
        )
        return edit, item, authorized, fingerprint

    @staticmethod
    def generate_fields(facts):
        by_field = {}
        for fact in sorted(facts, key=lambda f: f["id"]):
            by_field.setdefault(fact["field"], fact)
        fields, missing = {}, []

        def add(key, value, keys, clauses=None):
            if isinstance(value, str) and len(value) > TEXT_LIMITS[key]:
                missing.append(
                    f"{key}: el contenido respaldado excede el límite del editor."
                )
                return
            fields[key] = {
                "value": value,
                "evidence_ids": [by_field[k]["id"] for k in keys],
                "clauses": clauses or ([value] if isinstance(value, str) else []),
            }

        for key in ("brand", "manufacturer", "presentation", "category", "subcategory"):
            if key in by_field:
                if key == "subcategory" and "category" not in by_field:
                    missing.append("Subcategoría: falta categoría validada.")
                    continue
                add(key, by_field[key]["value"], [key])
            else:
                missing.append(f"{LABELS[key]}: sin evidencia aprobada; no se propone.")
        name = by_field.get("product_name")
        presentation = by_field.get("presentation")
        if name and presentation:
            title = name["value"] + " · " + presentation["value"]
            for key in ("title", "short_title", "seo_title"):
                add(
                    key,
                    title,
                    ["product_name", "presentation"],
                    [name["value"], presentation["value"]],
                )
        else:
            missing.append(
                "Títulos: falta nombre o presentación con respaldo aprobado."
            )
        rows, keys = [], []
        for key, label in TEXT.items():
            if key not in by_field:
                missing.append(
                    f"{label}: afirmación bloqueada por falta de evidencia aprobada vigente."
                )
                continue
            fact = by_field[key]
            rows.append(
                f"{label}: {fact['value']}"
                + (f" {fact['unit']}" if fact["unit"] else "")
                + "."
            )
            keys.append(key)
        if rows:
            add("details", "\n".join(rows), keys, rows)
            add(
                "attributes",
                [
                    {
                        "name": TEXT[k],
                        "value": by_field[k]["value"]
                        + (f" {by_field[k]['unit']}" if by_field[k]["unit"] else ""),
                    }
                    for k in keys
                ],
                keys,
            )
            # Descriptive copy uses only whole source-backed clauses, no marketing inference.
            if name and presentation:
                lead = name["value"] + " · " + presentation["value"] + "."
                add(
                    "description",
                    "\n".join([lead, *rows]),
                    ["product_name", "presentation", *keys],
                    [lead, *rows],
                )
                short = [
                    lead,
                    *[
                        row
                        for row, k in zip(rows, keys)
                        if k in {"ingredients", "allergens"}
                    ],
                ]
                for key in ("short_description", "seo_description"):
                    add(
                        key,
                        "\n".join(short),
                        [
                            "product_name",
                            "presentation",
                            *[k for k in keys if k in {"ingredients", "allergens"}],
                        ],
                        short,
                    )
        missing.extend(
            [
                "Multimedia y fuentes manuales: se conservan exactamente; no se inventan recursos ni derechos.",
                "EAN, notas y palabras clave: no se generan ni se consideran verificados por la IA.",
            ]
        )
        return fields, missing

    def get_record(self, ident, draft_id):
        record = self.db.get(KikiAiEditorialDraft, draft_id)
        if (
            not record
            or record.product_key != self.product_prefix + ident
            or record.model != self.model
            or not record.history
            or record.history[0].get("event") != self.event
        ):
            raise ValueError("La propuesta no pertenece a esta variante sintética.")
        return record

    @staticmethod
    def meta(record):
        return record.history[0]["proposal"]

    def validity(self, record, edit, item, fingerprint):
        meta = self.meta(record)
        reasons = []
        if (
            edit["version"] != meta["workspace_version"]
            or edit["fields"] != meta["base_fields"]
        ):
            reasons.append(
                "La ficha cambió desde la generación. Generá una propuesta nueva."
            )
        if (
            fingerprint != record.source_hash
            or item.identity_digest != meta["identity_hash"]
        ):
            reasons.append(
                "Las evidencias o la identidad cambiaron. Se requiere nueva generación y revisión."
            )
        if record.review_status == "APPLIED":
            reasons.append("La selección ya fue guardada; no puede aplicarse otra vez.")
        return reasons

    def serialize(self, record, edit, item, authorized, fingerprint):
        reasons = self.validity(record, edit, item, fingerprint)
        if reasons and record.review_status not in {"APPLIED", "STALE"}:
            record.review_status = "STALE"
            record.history = record.history + [
                {
                    "event": "INVALIDATED",
                    "at": now(),
                    "actor": self.research.actor,
                    "reasons": reasons,
                }
            ]
        meta = self.meta(record)
        # Reuse existing draft DTO; source evidence is approved documental input, not API quantities.
        result = EcommAiEditor._serialize(record, current=not reasons)
        result.update(
            {
                "synthetic_only": all(
                    f["provenance"].startswith("fixture://")
                    for f in record.source_facts
                ),
                "isolated_only": self.research.isolated_only,
                "internal_only": True,
                "generator": self.model,
                "ecomm_id": item.ecomm_id,
                "workspace_version": meta["workspace_version"],
                "revision": len(record.history),
                "fields": meta["fields"],
                "base_fields": meta["base_fields"],
                "missing": meta["missing"],
                "decisions": meta.get("decisions", {}),
                "blockers": reasons,
                "state": record.review_status,
                "history": record.history,
                "authorized_facts": authorized,
                "saved_to_product_fields": record.review_status == "APPLIED",
                "review_status": record.review_status,
            }
        )
        self.db.commit()
        return result

    def latest(self, ident):
        edit, item, facts, fingerprint = self.context(ident)
        record = self.db.scalars(
            select(KikiAiEditorialDraft)
            .where(
                KikiAiEditorialDraft.product_key == self.product_prefix + ident,
                KikiAiEditorialDraft.model == self.model,
            )
            .order_by(KikiAiEditorialDraft.id.desc())
        ).first()
        if not record:
            self.db.commit()
            return {
                "available": False,
                "synthetic_only": all(
                    f["provenance"].startswith("fixture://") for f in facts
                ),
                "isolated_only": self.research.isolated_only,
                "internal_only": True,
                "ecomm_id": ident,
                "external_writes_enabled": False,
                "authorized_facts": facts,
            }
        return self.serialize(record, edit, item, facts, fingerprint)

    def generate(
        self, ident, expected_version, *, only_missing=False, batch_reference=None
    ):
        edit, item, facts, fingerprint = self.context(ident)
        self.before_generate(ident, facts)
        if edit["version"] != expected_version:
            raise ValueError(
                "La ficha cambió. Recuperá la versión nueva antes de generar."
            )
        fields, missing = self.generate_fields(facts)
        if only_missing:
            fields = {
                key: value
                for key, value in fields.items()
                if not edit["fields"].get(key)
            }
            if not fields:
                raise ValueError(
                    "No hay campos incompletos que puedan recibir una propuesta respaldada."
                )
        meta = {
            "workspace_version": edit["version"],
            "identity_hash": item.identity_digest,
            "base_fields": edit["fields"],
            "fields": fields,
            "missing": missing,
            "decisions": {},
        }
        record = KikiAiEditorialDraft(
            product_key=self.product_prefix + ident,
            source_hash=fingerprint,
            original_name=item.identity["name"],
            source_facts=facts,
            model=self.model,
            title=fields.get("title", {}).get("value", ""),
            description=fields.get("description", {}).get("value", ""),
            questions=missing[:3],
            review_status="PENDING_REVIEW",
            history=[
                {
                    "event": self.event,
                    "at": now(),
                    "actor": self.research.actor,
                    "proposal": meta,
                    **({"batch_reference": batch_reference} if batch_reference else {}),
                    "quality_warnings": [
                        "Redacción determinista desde hechos de documentos locales revisados; sin IA real. Las decisiones de un operador de prueba no son aprobación efectiva del cliente."
                        if any(
                            not f["provenance"].startswith("fixture://") for f in facts
                        )
                        else "Demostración determinista con documentos sintéticos; no es IA ni investigación oficial."
                    ],
                }
            ],
        )
        self.db.add(record)
        self.db.flush()
        return self.serialize(record, edit, item, facts, fingerprint)

    @staticmethod
    def validate_edit(key, value, proposed):
        original = proposed["value"]
        if value == original:
            return
        if (
            not isinstance(value, str)
            or not isinstance(original, str)
            or not value.strip()
        ):
            raise ValueError(
                "La edición debe conservar un valor explícitamente respaldado."
            )
        if key in {"title", "short_title", "seo_title"}:
            parts = value.split(" · ")
        elif key in {"description", "short_description", "details", "seo_description"}:
            parts = value.splitlines()
        else:
            parts = [value]
        if (
            not parts
            or any(part not in proposed["clauses"] for part in parts)
            or len(set(parts)) != len(parts)
        ):
            raise ValueError(
                "Texto sin respaldo: sólo se permite quitar o reordenar frases completas documentadas. Agregar hechos requiere evidencia nueva."
            )
        if len(value) > TEXT_LIMITS[key]:
            raise ValueError("El texto excede el límite del editor.")

    def review(self, ident, draft_id, revision, decisions):
        edit, item, facts, fingerprint = self.context(ident)
        record = self.get_record(ident, draft_id)
        reasons = self.validity(record, edit, item, fingerprint)
        if (
            reasons
            or record.review_status == "STALE"
            or len(record.history) != revision
        ):
            raise ValueError(
                "Propuesta desactualizada o revisada en otra sesión. "
                + " ".join(reasons)
            )
        meta = deepcopy(self.meta(record))
        if not decisions or set(decisions) - set(meta["fields"]):
            raise ValueError("La selección contiene campos no propuestos.")
        for key, decision in decisions.items():
            if decision["decision"] == "ACCEPTED":
                self.validate_edit(key, decision["value"], meta["fields"][key])
        meta["decisions"] = deepcopy(decisions)
        history = deepcopy(record.history)
        history[0]["proposal"] = meta
        history.append(
            {
                "event": "FIELD_REVIEW",
                "at": now(),
                "actor": self.research.actor,
                "decisions": deepcopy(decisions),
            }
        )
        record.history = history
        record.review_status = "REVIEWED"
        return self.serialize(record, edit, item, facts, fingerprint)

    def apply(self, ident, draft_id, revision, body):
        edit, item, _facts, fingerprint = self.context(ident)
        record = self.get_record(ident, draft_id)
        reasons = self.validity(record, edit, item, fingerprint)
        if (
            reasons
            or record.review_status != "REVIEWED"
            or len(record.history) != revision
        ):
            raise ValueError(
                "Aplicación bloqueada: propuesta desactualizada o sin revisión vigente. "
                + " ".join(reasons)
            )
        meta = self.meta(record)
        merged = deepcopy(edit["fields"])
        selected = {}
        for key, decision in meta["decisions"].items():
            if decision["decision"] == "ACCEPTED":
                self.validate_edit(key, decision["value"], meta["fields"][key])
                merged[key] = decision["value"]
                selected[key] = decision["value"]
        if (
            not selected
            or body.expected_version != meta["workspace_version"]
            or body.status != "DRAFT"
            or body.fields.model_dump() != merged
        ):
            raise ValueError(
                "El guardado debe contener sólo la selección revisada sobre la misma versión, como borrador."
            )
        record.review_status = "APPLIED"
        record.reviewed_at = datetime.fromisoformat(now())
        record.review_note = (
            "Selección individual guardada mediante el editor versionado existente."
        )
        record.history = record.history + [
            {
                "event": "APPLIED_VIA_WORKSPACE",
                "at": now(),
                "actor": self.research.actor,
                "workspace_version_before": edit["version"],
                "selected_fields": list(selected),
            }
        ]
        # Existing service performs validation, CAS, history and the single commercial commit.
        result = self.workspace.save(ident, merged, "DRAFT", body.expected_version)
        self.db.commit()  # also covers existing editor's unchanged-fields no-op
        return result
