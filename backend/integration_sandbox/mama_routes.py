"""One explicit commercial pilot in existing dossier/editor storage, no new DB."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session
from app.core.security import require_csrf, require_session
from app.database.session import get_db
from app.services.ecomm_api_product_workspace_service import blank_fields
from .mama_reference import (
    PILOT_ID,
    SOURCE_EVENT,
    PROVENANCE_EVENT,
    references,
    reference,
    URL,
    NAME,
)
from copy import deepcopy
from .research.service import Research, identity_digest
from .research.storage import Dossier, digest
from .research.routes import execute
from .local_documents import LocalDocuments
from .document_routes import Incorporate
from .proposals import Proposals

router = APIRouter(
    prefix="/api/test-commercial-pilot/mama-350", tags=["isolated-commercial-pilot"]
)


class Prepare(BaseModel):
    model_config = ConfigDict(extra="forbid")


def report(db, session):
    research = Research(db, session)
    if db.get(Dossier, PILOT_ID) is None:
        return {"available": False, "test_id": PILOT_ID, "network_enabled": False}
    item = research.dossier(PILOT_ID)
    initial = next(e["detail"] for e in item.history if e["action"] == SOURCE_EVENT)
    registered = next(
        e["detail"]
        for e in reversed(item.history)
        if e["action"] in {SOURCE_EVENT, PROVENANCE_EVENT}
    )
    edit, _, approved, fingerprint = Proposals(db, session).context(PILOT_ID)
    proposed, missing = Proposals.generate_fields(approved)
    requested = [
        "title",
        "short_description",
        "description",
        "details",
        "presentation",
        "category",
        "subcategory",
        "seo_title",
        "seo_description",
    ]
    result = {
        "available": True,
        "test_id": PILOT_ID,
        "authentic_ecomm_id": None,
        "test_id_is_synthetic": True,
        "binding_status": "PENDING",
        "references": registered["references"],
        "reference_record_hash": registered["reference_record_hash"],
        "initial_fields": initial["initial_fields"],
        "current_fields": edit["fields"],
        "workspace_version": edit["version"],
        "approved_fact_count": len(approved),
        "proposed_fields_preview": proposed,
        "missing": missing,
        "blocked_fields": [key for key in requested if key not in proposed],
        "network_enabled": False,
        "automatic_discovery_enabled": False,
        "variant": {
            "id": PILOT_ID,
            "name": NAME,
            "sku": "SYNTHETIC-LOCAL-PILOT-NOT-A-SKU-LINK",
            "presentation": "350 g",
            "stock": None,
            "capturedAt": None,
            "gtin": None,
            "isCombo": None,
        },
    }
    db.commit()
    return result


def prepare(db, session):
    research = Research(db, session)
    item = db.get(Dossier, PILOT_ID)
    if item is None:
        ref = reference()
        item = Dossier(
            ecomm_id=PILOT_ID,
            version=0,
            identity=ref,
            identity_digest=identity_digest(ref),
            facts=[],
            history=[],
        )
        db.add(item)
        db.flush()
        refs = references()
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
        LocalDocuments(db, session).incorporate(
            PILOT_ID,
            Incorporate(
                kind="URL",
                expected_version=item.version,
                reference_url=URL,
                declared_official=True,
                declared_manufacturer="Thai President Foods",
                provenance_note="URL oficial CANDIDATA informada por el usuario en etapa 2J. No visitada ni descargada. No confirma EAN, ingredientes, alérgenos, nutrientes ni contenido de un archivo auténtico.",
                authorized_local_processing=True,
            ),
            None,
        )
    else:
        registered = next(
            e["detail"]
            for e in reversed(item.history)
            if e["action"] in {SOURCE_EVENT, PROVENANCE_EVENT}
        )
        updated = references()
        if registered["reference_record_hash"] != digest(updated):
            research.commit_change(
                item,
                deepcopy(item.facts),
                PROVENANCE_EVENT,
                {
                    "references": updated,
                    "reference_record_hash": digest(updated),
                    "previous_reference_record_hash": registered[
                        "reference_record_hash"
                    ],
                    "reason": "Actualización de procedencia autorizada: Excel comprobado externamente y referencia secundaria no oficial. Sin aprobar hechos ni modificar ficha comercial.",
                },
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
