from copy import deepcopy
from datetime import datetime, timezone
import re
from sqlalchemy import select
from app.core.config import get_settings
from app.database.models import EcommApiProductEdit
from app.services.ecomm_api_product_workspace_service import EcommApiProductWorkspace
from .fields import REQUIRED, LABELS
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


def identity_digest(reference):
    # Provenance display and copying the exact canonical presentation to the editor
    # do not change the variant. Genuine contradictory editorial values still do.
    # Display-only research hints cannot invalidate approved identity or facts.
    values = {k: v for k, v in reference.items() if k not in {"provenance", "presentation_lookup_hint"}}
    if values.get("editorial_presentation") == values.get("presentation"):
        values["editorial_presentation"] = None
    return digest(values)


class Research:
    Control, Document, Dossier = Control, Document, Dossier
    workspace_type = EcommApiProductWorkspace
    fixtures = {}
    isolated_only = False

    def edit_record(self, ident):
        return self.db.scalar(
            select(EcommApiProductEdit).where(EcommApiProductEdit.ecomm_id == ident)
        )

    def source_record(self, ident):
        return self.workspace_type(self.db)._source(ident)

    def additional_blockers(self, item, doc):
        issues = []
        if (
            not item.identity.get("presentation")
            or item.identity.get("is_combo") is None
        ):
            issues.append(
                "Falta identidad de presentación o tipo de venta en la captura."
            )
        edit = self.edit_record(item.ecomm_id)
        fields = edit.fields if edit else {}
        for key in ("brand", "manufacturer"):
            if (
                fields.get(key)
                and fields[key].strip().casefold()
                != str(doc.body.get("identity", {}).get(key) or "").strip().casefold()
            ):
                issues.append(
                    f"{key}: el valor editorial difiere del documento; requiere revisión."
                )
        return issues

    def assisted(self, item):
        return None

    def validate_document(self, ident, doc):
        if doc and doc.body.get("associated_ecomm_id") != ident:
            raise ValueError(
                "Documento no asociado al Ecomm ID exacto; no se comparte por SKU o EAN."
            )

    def documents(self, ident=None):
        return list(
            self.db.scalars(
                select(self.Document)
                .where(self.Document.body["associated_ecomm_id"].as_string() == ident)
                .order_by(self.Document.id)
            )
        )

    def reference(self, ident):
        source = self.source_record(ident)
        if source.get("identity_blockers"):
            raise ValueError("Identidad bloqueada: barcode y gtin discrepan.")
        edit = self.edit_record(ident)
        fields = edit.fields if edit else {}
        # The API barcode and a lookup-only Excel hint MUST remain separate.
        # Manufacturer documents may not print the EAN even when name, brand
        # and presentation match. A lookup hint must not become an approved
        # fact or an obligatory barcode claim in every source document.
        lookup_gtin = None
        lookup_provenance = "Sin código externo apto para búsqueda"
        if not source["gtin"]:
            # Only *unique, non-combo* barcodes with exact Ecomm ID+SKU and a
            # complete, unchanged API capture can be considered. This merely
            # supplies a reference for source matching. It is NOT a verified
            # manufacturer assertion and never approves documentary facts.
            from app.services.ecomm_gtin_export_service import (
                safe_gtin_candidates_for_pages,
            )

            # A Research instance is scoped to one guarded request/transaction.
            # Build the validated export index once when several references are
            # checked together; never reuse it across HTTP requests.
            export_candidates = getattr(self, "_export_gtin_candidates", None)
            if export_candidates is None:
                export_candidates = safe_gtin_candidates_for_pages(
                    self.db, self.workspace_type(self.db)._source_pages()
                )
                self._export_gtin_candidates = export_candidates
            candidate = export_candidates.get(ident)
            if candidate:
                lookup_gtin = candidate
                lookup_provenance = (
                    "Excel de inventario Ecomm-App: ID y SKU exactos, GTIN único "
                    "y válido, variante no combo. Solo pista de búsqueda, "
                    "no GTIN certificado por API ni por fabricante."
                )
        from .presentation_hint import candidate as size_candidate

        return {
            "ecomm_id": ident,
            "name": source["product_name"],
            "sku": source["sku"],
            "presentation": source["variant_description"],
            "presentation_lookup_hint": size_candidate(source),
            "is_combo": source["is_combo"],
            "parent_is_combo": source.get("parent_is_combo"),
            "ean": source["gtin"],
            "lookup_gtin": lookup_gtin,
            "barcode": source.get("barcode"),
            "gtin_raw": source.get("gtin_raw"),
            "brand": source.get("brand"),
            "manufacturer": source.get("manufacturer"),
            "editorial_presentation": fields.get("presentation") or None,
            "provenance": {
                "name": "Captura API; no equivale a verificación del fabricante",
                "presentation": "Captura API; no equivale a verificación del fabricante",
                "presentation_lookup_hint": "Medida encontrada en el texto original de Ecomm; solo pista para contrastar con etiqueta y fabricante, nunca presentación certificada.",
                "ean": "Captura API; no equivale a verificación del fabricante",
                "lookup_gtin": lookup_provenance,
                "brand": "Campo KIKI de contraste; no aprobado por defecto",
                "manufacturer": "Campo KIKI de contraste; no aprobado por defecto",
            },
        }

    def __init__(self, db, session):
        self.db = db
        self.actor = f"{get_settings().kiki_admin_username} · sesión {session.id}"
        # Hold ORM references for this operation under the existing mutex.
        # The weak identity map otherwise reloads documents for each pair of
        # facts. Values and verification rules are never memoized.
        self._document_refs = {}
        # One transaction mutex for the initial documentary workspace. All reads/revisions use it.
        if (
            db.scalar(
                select(self.Control).where(self.Control.id == 1).with_for_update()
            )
            is None
        ):
            raise RuntimeError(
                "Falta el control transaccional de investigación; operación bloqueada."
            )

    def _document(self, document_id):
        if document_id not in self._document_refs:
            self._document_refs[document_id] = self.db.get(self.Document, document_id)
        return self._document_refs[document_id]

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
        # A validated Excel GTIN is a lookup hint. Do not demand that every
        # manufacturer's document print it, but reject an explicit conflicting
        # EAN on a document before any fact can be approved.
        hint = reference.get("lookup_gtin")
        claimed = body["identity"].get("ean")
        if hint and claimed and str(hint).strip() != str(claimed).strip():
            issues.append(
                "EAN declarado en documento incompatible con la pista GTIN "
                "del Excel Ecomm-App; revisar variante y presentación."
            )
        if (
            reference.get("editorial_presentation")
            and reference["editorial_presentation"] != reference["presentation"]
        ):
            issues.append(
                "La presentación editorial KIKI difiere de la captura Ecomm-App."
            )
        if body.get("associated_ecomm_id"):
            if body["associated_ecomm_id"] != reference["ecomm_id"]:
                issues.append(
                    "Documento asociado a otro Ecomm ID; no se reutiliza por SKU/EAN."
                )
            document_sale_type = body["identity"].get("is_combo")
            # Manufacturers commonly identify an individual retail product by
            # its *exact name and presentation* without an explicit "unidad"
            # field. Absence must not block all ordinary, non-combo evidence.
            # Pack/kit identities remain strict: no inherited unit EAN, no
            # assumption about contents or the actual pack presentation.
            if document_sale_type is not None and (
                document_sale_type != reference["is_combo"]
            ):
                issues.append("Tipo de venta (unidad/pack) incompatible.")
            elif reference["is_combo"] is True and document_sale_type is not True:
                issues.append(
                    "Pack/kit sin tipo de venta explícito en el documento; "
                    "no se puede acreditar la presentación del pack."
                )
        return issues

    @staticmethod
    def _equivalence_record(item, doc):
        """Latest explicit decision for this exact document, never shared by EAN/SKU."""
        for event in reversed(item.history or []):
            if event.get("action") != "DOCUMENT_IDENTITY_REVIEW":
                continue
            detail = event.get("detail") or {}
            if detail.get("document_id") == doc.id:
                return detail
        return None

    def identity_blockers(self, item, doc):
        issues = self.identity_issues(item.identity, doc.body)
        record = self._equivalence_record(item, doc)
        if not record or record.get("decision") != "APPROVED":
            return issues
        if (
            record.get("ecomm_id") != item.ecomm_id
            or record.get("identity_digest") != item.identity_digest
            or record.get("document_version") != doc.version
            or record.get("document_hash") != doc.digest
            or record.get("source_name") != item.identity.get("name")
            or record.get("source_presentation") != item.identity.get("presentation")
            or record.get("document_name") != doc.body.get("identity", {}).get("name")
            or record.get("document_presentation") != doc.body.get("identity", {}).get("presentation")
            or item.identity.get("is_combo") is not False
            or doc.body.get("source", {}).get("review_state") != "REVIEWED"
            or doc.body.get("parse_status") != "TEXT_EXTRACTED"
        ):
            return issues
        # Human decision waives only the stated nomenclature and package-size
        # differences; not EAN, SKU, brand, manufacturer or sale type.
        issues = [
            issue for issue in issues
            if not issue.startswith(("Nombre incompatible", "Presentación incompatible"))
        ]
        editorial = item.identity.get("editorial_presentation")
        if editorial == doc.body["identity"]["presentation"]:
            issues = [issue for issue in issues if not issue.startswith("La presentación editorial")]
        return issues

    def review_document_identity(
        self, ident, expected_version, document_id, document_version, decision, reason
    ):
        if decision not in {"APPROVED", "REVOKED"}:
            raise ValueError("Decisión de identidad no permitida.")
        if len(reason.strip()) < 20:
            raise ValueError("Indicá cómo contrastaste el producto con la fuente (20 caracteres).")
        item = self.dossier(ident)
        self.expect(item, expected_version)
        doc = self._document(document_id)
        self.validate_document(ident, doc)
        if not doc or doc.version != document_version:
            raise ValueError("Documento inexistente o cambió de versión.")
        if doc.body.get("associated_ecomm_id") != ident:
            raise ValueError("La equivalencia solo puede vincular el documento de esta variante.")
        if decision == "APPROVED":
            if (
                item.identity.get("is_combo") is not False
                or doc.body.get("source", {}).get("review_state") != "REVIEWED"
                or doc.body.get("parse_status") != "TEXT_EXTRACTED"
            ):
                raise ValueError("Requiere unidad individual y procedencia documental revisada.")
            identity = doc.body.get("identity", {})
            if not all(str(identity.get(k) or "").strip() for k in ("name", "presentation")):
                raise ValueError("La fuente debe identificar explícitamente nombre y presentación.")
            original = self.identity_issues(item.identity, doc.body)
            if not any(x.startswith(("Nombre incompatible", "Presentación incompatible")) for x in original):
                raise ValueError("Sin diferencias de identidad nominal que requieran conciliación.")
            disallowed = [
                x for x in original if not x.startswith((
                    "Nombre incompatible", "Presentación incompatible",
                    "La presentación editorial",
                ))
            ]
            if disallowed or self.additional_blockers(item, doc) or doc.body.get("parser_blockers"):
                raise ValueError("Existen discrepancias de EAN, tipo de venta u otros bloqueos.")
        else:
            current = self._equivalence_record(item, doc)
            if not current or current.get("decision") != "APPROVED":
                raise ValueError("No hay una conciliación aprobada vigente para revocar.")
        record = {
            "ecomm_id": ident,
            "document_id": doc.id,
            "document_version": doc.version,
            "document_hash": doc.digest,
            "identity_digest": item.identity_digest,
            "source_name": item.identity.get("name"),
            "source_presentation": item.identity.get("presentation"),
            "document_name": doc.body.get("identity", {}).get("name"),
            "document_presentation": doc.body.get("identity", {}).get("presentation"),
            "decision": decision,
            "reason": reason.strip(),
            "reviewer": self.actor,
        }
        self.commit_change(item, deepcopy(item.facts), "DOCUMENT_IDENTITY_REVIEW", record)
        self.refresh(item)
        return self.serialize(item)

    def dossier(self, ident):
        item = self.db.get(self.Dossier, ident)
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
            item = self.Dossier(
                ecomm_id=ident,
                version=0,
                identity=reference,
                identity_digest=identity_digest(reference),
                facts=[],
                history=[],
            )
            self.db.add(item)
            self.db.flush()
        if item.identity_digest != identity_digest(reference):
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
            item.identity_digest = identity_digest(reference)
            self.commit_change(
                item,
                facts,
                "IDENTITY_CHANGED",
                {"before": previous, "after": reference},
            )
        elif item.identity != reference:
            item.identity = reference  # same identity, updated visible provenance only
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
        doc = self._document(fact["document_id"])
        issues = self.identity_blockers(item, doc)
        issues.extend(self.additional_blockers(item, doc))
        if fact["ecomm_id"] != item.ecomm_id:
            issues.append("El hecho no pertenece a esta variante Ecomm-App.")
        if doc.body.get("associated_ecomm_id"):
            if doc.body["source"]["review_state"] != "REVIEWED":
                issues.append(
                    "Procedencia sin revisión vigente. Declarar oficial una fuente no la autentica."
                )
            issues.extend(doc.body.get("parser_blockers", []))
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
        doc_presentation = doc.body.get("identity", {}).get("presentation")
        record = self._equivalence_record(item, doc)
        matched_alias = bool(
            record and record.get("decision") == "APPROVED"
            and not self.identity_blockers(item, doc)
            and fact["presentation"] == doc_presentation
        )
        if fact["presentation"] != item.identity["presentation"] and not matched_alias:
            issues.append("La presentación del hecho no corresponde a la variante.")
        if fact["field"] == "certification_evidence" and not re.search(
            r"\d", fact["value"]
        ):
            issues.append(
                "El respaldo de certificación requiere una referencia específica identificable; no basta una declaración genérica."
            )
        property_claim = fact["field"] in {
            "commercial_claim",
            "characteristics",
        } and bool(
            re.search(r"sin\s+gluten|org[aá]nic[oa]", fact["value"], re.IGNORECASE)
        )
        if fact["field"] == "certification" or property_claim:
            support = next(
                (
                    f
                    for f in item.facts
                    if f["document_id"] == fact["document_id"]
                    and f["field"] == "certification_evidence"
                    and f["state"] == "APPROVED"
                    and not self.blockers(item, f, include_conflicts=False)
                ),
                None,
            )
            if not support:
                issues.append(
                    "Certificación sin respaldo documental específico aprobado vigente; no se puede afirmar la propiedad."
                )
            if property_claim:
                certificate = next(
                    (
                        f
                        for f in item.facts
                        if f["document_id"] == fact["document_id"]
                        and f["field"] == "certification"
                        and f["state"] == "APPROVED"
                        and not self.blockers(item, f, include_conflicts=False)
                    ),
                    None,
                )
                if (
                    not certificate
                    or fact["value"].strip().casefold()
                    != certificate["value"].strip().casefold()
                ):
                    issues.append(
                        "La propiedad requiere su certificación específica aprobada; no se infiere desde otra característica."
                    )
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
            doc = self._document(fact["document_id"])
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
        from .local_documents import public_body

        assisted = self.assisted(item)

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
                    "body": public_body(doc.body),
                    "issues": self.identity_blockers(item, doc),
                    "versions": [v["version"] for v in self.fixtures.get(doc.id, [])],
                    "history": [
                        {**h, "body": public_body(h["body"])} for h in doc.history
                    ],
                }
                for doc in self.documents(item.ecomm_id)
            ],
            "synthetic_only": not any(
                d.body.get("associated_ecomm_id") for d in self.documents(item.ecomm_id)
            ),
            "isolated_only": self.isolated_only,
            "internal_only": True,
            "external_writes_enabled": False,
            "commercial_fields_applied": False,
            "assisted": assisted,
        }
        self.db.commit()
        return result

    def extract(self, ident, expected_version, document_id, document_version):
        item = self.dossier(ident)
        self.expect(item, expected_version)
        doc = self.db.get(self.Document, document_id)
        self.validate_document(ident, doc)
        if not doc or doc.version != document_version:
            raise ValueError("La versión del documento cambió o no existe.")
        if doc.body.get("associated_ecomm_id") not in (None, ident):
            raise ValueError("El documento local pertenece a otro Ecomm ID.")
        if (
            doc.body.get("associated_ecomm_id")
            and doc.body.get("parse_status") != "TEXT_EXTRACTED"
        ):
            raise ValueError(
                "Sin datos accesibles para extraer: referencia sin descarga, información insuficiente o PDF que requiere OCR."
            )
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
                    "Extracción documental; requiere revisión humana independiente.",
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
