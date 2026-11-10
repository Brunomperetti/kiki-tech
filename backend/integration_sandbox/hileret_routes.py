"""Two auxiliary cases in existing test dossier/editor storage, never a catalog."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session
from app.core.security import require_csrf, require_session
from app.database.session import get_db
from app.services.ecomm_api_product_workspace_service import blank_fields
from .hileret_reference import (
    PILOTS,
    SOURCE_EVENT,
    URL,
    REQUESTED_FIELDS,
    references,
    reference,
)
from .research.service import Research, identity_digest
from .research.storage import Dossier, digest
from .research.routes import execute
from .local_documents import LocalDocuments
from .document_routes import Incorporate
from .proposals import Proposals

router = APIRouter(
    prefix="/api/test-commercial-pilot/hileret-200", tags=["isolated-commercial-pilot"]
)


class Prepare(BaseModel):
    model_config = ConfigDict(extra="forbid")


def report(db, session):
    research = Research(db, session)
    cases = []
    for ident, pilot in PILOTS.items():
        if db.get(Dossier, ident) is None:
            continue
        item = research.dossier(ident)
        initial = next(e["detail"] for e in item.history if e["action"] == SOURCE_EVENT)
        edit, _, approved, _ = Proposals(db, session).context(ident)
        proposed, missing = Proposals.generate_fields(approved)
        documents = []
        for doc in research.documents(ident):
            body = doc.body
            documents.append(
                {
                    "id": doc.id,
                    "version": doc.version,
                    "kind": body["origin_kind"],
                    "parse_status": body["parse_status"],
                    "original": body["original"]
                    if body["origin_kind"] == "FILE"
                    else None,
                    "source_review_state": body["source"]["review_state"],
                    "issues": research.identity_issues(item.identity, body),
                    "locations": list(body["sections"]),
                }
            )
        has_pdf = any(
            d["original"] and d["original"]["content_type"] == "application/pdf"
            for d in documents
        )
        cases.append(
            {
                "test_id": ident,
                "test_id_is_synthetic": True,
                "authentic_ecomm_id": None,
                "binding_status": "PENDING",
                "references": initial["references"],
                "reference_record_hash": initial["reference_record_hash"],
                "initial_fields": initial["initial_fields"],
                "current_fields": edit["fields"],
                "workspace_version": edit["version"],
                "approved_fact_count": len(approved),
                "proposed_fields_preview": proposed,
                "blocked_fields": [
                    key for key in REQUESTED_FIELDS if key not in proposed
                ],
                "missing": missing,
                "documents": documents,
                "original_pdf_available": has_pdf,
                "document_status": "LOCAL_PDF_REQUIRES_REVIEW"
                if has_pdf
                else "BLOCKED_NO_ORIGINAL_PDF",
                "variant": {
                    "id": ident,
                    "name": pilot["name"],
                    "presentation": pilot["presentation"],
                    "sku": item.identity["sku"],
                    "stock": None,
                    "capturedAt": None,
                    "gtin": None,
                    "isCombo": pilot["is_combo"],
                },
            }
        )
    db.commit()
    return {
        "cases": cases,
        "network_enabled": False,
        "external_writes_enabled": False,
        "automatic_discovery_enabled": False,
    }


def prepare(db, session):
    for ident in PILOTS:
        research = Research(db, session)
        if db.get(Dossier, ident) is not None:
            db.commit()
            continue
        ref = reference(ident)
        item = Dossier(
            ecomm_id=ident,
            version=0,
            identity=ref,
            identity_digest=identity_digest(ref),
            facts=[],
            history=[],
        )
        db.add(item)
        db.flush()
        refs = references(ident)
        research.commit_change(
            item,
            [],
            SOURCE_EVENT,
            {
                "references": refs,
                "reference_record_hash": digest(refs),
                "initial_fields": blank_fields(),
            },
        )
        # References only: no bytes, document hash, extraction or official approval.
        LocalDocuments(db, session).incorporate(
            ident,
            Incorporate(
                kind="URL",
                expected_version=item.version,
                reference_url=URL,
                declared_official=True,
                provenance_note="Folleto en dominio Hileret informado por el usuario, página 2. No descargado ni procesado: faltan bytes originales. Unidad 200 ml, pack x6 y caja x9 no son equivalentes.",
                authorized_local_processing=True,
            ),
            None,
        )
    return report(db, session)


@router.get("")
def get_report(db: Session = Depends(get_db), session=Depends(require_session)):
    return execute(db, lambda: report(db, session))


@router.post("/prepare")
def prepare_report(
    body: Prepare, db: Session = Depends(get_db), session=Depends(require_csrf)
):
    return execute(db, lambda: prepare(db, session))
