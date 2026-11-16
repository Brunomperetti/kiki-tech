"""End-to-end commercial draft regression using an entirely disposable SQLite DB.

The name/size and source text are synthetic fixtures modelled after the real
Natural Seed naming discrepancy. There is NO web access, official source
verification, AI invocation, provider traffic or customer database connection.
"""
from types import SimpleNamespace

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database.models import (
    Base, CatalogSnapshot, EcommApiProductEdit, KikiAiEditorialDraft,
)
from app.services.documental.storage import (
    ResearchBase, Control, Document, Dossier, digest,
)
from app.services.documental.research import Research
from app.services.documental.proposals import Proposals
from app.services.ecomm_api_product_workspace_service import (
    EcommApiProductWorkspace, blank_fields,
)


IDENT = "7518949"
RAW_NAME = "Mix Semillas P/ Ensaladas Sopas Natural Seed X 250gr"
DOCUMENT_ID = "local-" + "a" * 32


def evidence(field, value, loc, presentation="250 g"):
    quote = f"{field}: {value}"
    return {
        "field": field,
        "value": value,
        "unit": None,
        "location": loc,
        "quote": quote,
        "presentation": presentation,
        "commercial_field": "attributes",
    }


def synthetic_document():
    claims = [
        evidence("product_name", "Mix Ensaladas y Sopas", "texto/linea/1"),
        evidence("presentation", "250 g", "texto/linea/2"),
        evidence(
            "characteristics", "3 frutos secos y 3 semillas al oreganato",
            "texto/linea/3",
        ),
    ]
    sections = {claim["location"]: claim["quote"] for claim in claims}
    return {
        "id": DOCUMENT_ID,
        "version": 1,
        "synthetic": False,
        "associated_ecomm_id": IDENT,
        "identity": {
            "name": "Mix Ensaladas y Sopas",
            "presentation": "250 g",
            "ean": None,
            "brand": None,
            "manufacturer": None,
            "is_combo": None,
        },
        "identity_evidence": {
            "name": {
                "value": "Mix Ensaladas y Sopas",
                "location": "texto/linea/1",
                "quote": sections["texto/linea/1"],
            },
            "presentation": {
                "value": "250 g",
                "location": "texto/linea/2",
                "quote": sections["texto/linea/2"],
            },
        },
        "source": {
            "review_state": "REVIEWED",
            "reference_url": "https://fabricante-prueba.invalid/mix-250g",
        },
        "provenance": "local://sha256/" + "1" * 64,
        "parse_status": "TEXT_EXTRACTED",
        "parser_blockers": [],
        "parser_warnings": [],
        "original": {"sha256": "1" * 64, "size": 150, "content_type": "text/plain"},
        "sections": sections,
        "claims": claims,
        "kind": "Documento local",
        "title": "fabricante-prueba.txt",
    }


def prepare(tmp_path):
    engine = create_engine("sqlite:///" + str(tmp_path / "documental-acceptance.db"))
    Base.metadata.create_all(engine)
    ResearchBase.metadata.create_all(engine)
    stage = [{
        "page": 1, "total": 1, "total_pages": 1, "per_page": 50,
        "captured_at": "2026-11-15T23:25:30+00:00",
        "items": [{
            "code": "9995", "description": RAW_NAME,
            "is_combo": False,
            "variants": [{
                "id": int(IDENT), "sku": "9995", "is_combo": False,
                "description": RAW_NAME, "variant_description": RAW_NAME,
                "gtin": None, "barcode": None, "total_stock": 1,
            }],
        }],
    }]
    with Session(engine) as db:
        db.add(CatalogSnapshot(source="ECOMM_APP_API_STAGE", payload=stage))
        db.add(Control(id=1))
        doc = synthetic_document()
        db.add(Document(
            id=DOCUMENT_ID, version=1, body=doc,
            digest=digest(doc), history=[],
        ))
        db.commit()
    return engine, stage


def test_real_naming_discrepancy_flows_to_versioned_internal_draft(tmp_path, monkeypatch):
    import app.services.documental.research as module

    monkeypatch.setattr(
        module, "get_settings", lambda: SimpleNamespace(kiki_admin_username="test"),
    )
    engine, original_capture = prepare(tmp_path)
    user = SimpleNamespace(id=1)
    with Session(engine) as db:
        research = Research(db, user)
        dossier = research.dossier(IDENT)
        assert dossier.version == 0
        assert research.identity_blockers(dossier, db.get(Document, DOCUMENT_ID))

        reviewed = research.review_document_identity(
            IDENT, dossier.version, DOCUMENT_ID, 1, "APPROVED",
            "Contraste de etiqueta ficticia y nombre/peso para este caso de prueba.",
        )
        assert reviewed["documents"][0]["identity_reconciliation"]["current"] is True
        extracted = research.extract(
            IDENT, reviewed["version"], DOCUMENT_ID, 1,
        )
        assert len(extracted["facts"]) == 3
        assert all(not fact["verified"] for fact in extracted["facts"])

        for candidate in extracted["facts"]:
            current = research.dossier(IDENT)
            fact = next(x for x in current.facts if x["id"] == candidate["id"])
            extracted = research.review(
                IDENT, current.version, fact["id"], fact["version"],
                "APPROVED", "Verifiqué la cita exacta del archivo SINTÉTICO de prueba.",
            )
        assert len([f for f in extracted["facts"] if f["verified"]]) == 3

        service = Proposals(db, user)
        proposed = service.generate(IDENT, 0)
        assert proposed["fields"]["presentation"]["value"] == "250 g"
        assert "Mix Ensaladas y Sopas" in proposed["fields"]["title"]["value"]
        assert proposed["fields"]["seo_title"]["value"].endswith("250 g")
        assert "3 frutos secos y 3 semillas" in proposed["fields"]["description"]["value"]
        assert "category" not in proposed["fields"]
        assert "subcategory" not in proposed["fields"]
        assert "media" not in proposed["fields"]
        assert "sin tacc" not in str(proposed).lower()
        assert "7798180790097" not in str(proposed)

        decisions = {
            key: {"decision": "ACCEPTED", "value": value["value"]}
            for key, value in proposed["fields"].items()
            if key in {
                "presentation", "title", "short_title", "description",
                "short_description", "seo_title", "seo_description", "details",
                "attributes", "seo_keywords",
            }
        }
        reviewed_proposal = service.review(
            IDENT, proposed["draft_id"], proposed["revision"], decisions,
        )
        fields = blank_fields()
        for key, decision in decisions.items():
            fields[key] = decision["value"]

        class FieldsPayload:
            def model_dump(self):
                return fields

        saved = service.apply(
            IDENT, proposed["draft_id"], reviewed_proposal["revision"],
            SimpleNamespace(expected_version=0, status="DRAFT", fields=FieldsPayload()),
        )
        assert saved["version"] == 1
        assert saved["status"] == "DRAFT"
        assert saved["fields"]["presentation"] == "250 g"
        assert saved["external_writes_enabled"] is False

    with Session(engine) as db:
        persisted = EcommApiProductWorkspace(db).get(IDENT)
        assert persisted["fields"]["presentation"] == "250 g"
        assert persisted["fields"]["title"] == "Mix Ensaladas y Sopas · 250 g"
        assert persisted["fields"]["short_title"] == "Mix Ensaladas y Sopas"
        assert persisted["fields"]["seo_keywords"] == "Mix Ensaladas y Sopas, 250 g"
        assert persisted["version"] == 1
        assert len(persisted["history"]) == 1
        doc_reloaded = db.get(Document, DOCUMENT_ID)
        assert doc_reloaded.digest == digest(doc_reloaded.body)
        assert db.get(Dossier, IDENT).version >= 5
        research = Research(db, user)
        current = research.dossier(IDENT)
        assert research.equivalence_current(current, doc_reloaded)
        research.refresh(current)
        assert len([f for f in current.facts if f["state"] == "APPROVED"]) == 3
        assert db.scalar(select(KikiAiEditorialDraft)).review_status == "APPLIED"
        assert db.scalar(select(CatalogSnapshot).where(
            CatalogSnapshot.source == "ECOMM_APP_API_STAGE"
        )).payload == original_capture
        assert db.scalars(select(EcommApiProductEdit)).one().source_sku == "9995"
