"""Synthetic fixtures and pilot profiles only; shared algorithms live in app."""

from copy import deepcopy
from sqlalchemy import select
from app.database.models import EcommApiProductEdit
from app.services.documental.research import (
    Research as CommonResearch,
    now,
    fact_digest as fact_digest,
    identity_digest as identity_digest,
)
from ..workspace import EcommApiProductWorkspace
from .documents import BRAND, MANUFACTURER, FIXTURES
from .storage import Control, Document, Dossier, digest


class Research(CommonResearch):
    Control, Document, Dossier = Control, Document, Dossier
    workspace_type = EcommApiProductWorkspace
    fixtures = FIXTURES
    isolated_only = True

    def __init__(self, db, session):
        super().__init__(db, session)
        self.actor = self.actor.replace(" · sesión ", " · sesión de prueba ")

    def assisted(self, item):
        from ..assisted_research import assisted_view

        return assisted_view(self, item)

    def validate_document(self, ident, doc):
        from ..mama_reference import PILOT_ID
        from ..hileret_reference import PILOTS

        if ident == PILOT_ID or ident in PILOTS:
            super().validate_document(ident, doc)

    def additional_blockers(self, item, doc):
        if item.identity.get("hileret_pilot") and (
            doc.body.get("origin_kind") != "FILE"
            or doc.body.get("original", {}).get("content_type") != "application/pdf"
        ):
            return [
                "Piloto Hileret: requiere PDF original; una transcripción o URL no sustituye al folleto."
            ]
        return []

    def reference(self, ident):
        from ..mama_reference import PILOT_ID, reference
        from ..hileret_reference import PILOTS, reference as hileret_reference

        if ident in PILOTS:
            return hileret_reference(
                ident, EcommApiProductWorkspace(self.db).get(ident)["fields"]
            )
        if ident == PILOT_ID:
            return reference(EcommApiProductWorkspace(self.db).get(ident)["fields"])
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
        # Alias exceptions are ONLY pilot fixtures, never normal API identities.
        comparison = deepcopy(reference)
        if reference.get("commercial_pilot") or reference.get("hileret_pilot"):
            comparison["name"] = body["identity"].get("name")
        if reference.get("commercial_pilot") and reference.get("is_combo") is None:
            comparison["is_combo"] = body["identity"].get("is_combo")
        issues = CommonResearch.identity_issues(comparison, body)
        if reference.get("hileret_pilot"):
            from ..hileret_reference import identity_issues

            issues.extend(identity_issues(reference, body))
        if reference.get("commercial_pilot"):
            from ..mama_reference import identity_issues

            issues.extend(identity_issues(reference, body))
        return issues

    def documents(self, ident=None):
        from ..mama_reference import PILOT_ID
        from ..hileret_reference import PILOTS

        return [
            d
            for d in self.db.scalars(select(Document).order_by(Document.id))
            if (
                ident != PILOT_ID
                and ident not in PILOTS
                and not d.body.get("associated_ecomm_id")
            )
            or d.body.get("associated_ecomm_id") == ident
        ]

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
