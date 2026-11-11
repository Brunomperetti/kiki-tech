"""Opt-in authored documentary approvals; never client approvals or real identity."""

from copy import deepcopy
from types import SimpleNamespace
from sqlalchemy import select
from .document_test_fixtures import TEXT
import base64


def approved(db, ident="900001"):
    from app.services.documental.local_documents import LocalDocuments, parse_local
    from app.services.documental.contracts import Incorporate, Provenance
    from app.services.documental.research import Research

    actor = SimpleNamespace(id="SYNTHETIC-BATCH-TEST-APPROVAL")
    service = Research(db, actor)
    case = service.dossier(ident)
    payload = Incorporate(
        kind="FILE",
        expected_version=case.version,
        filename="dietética-sintetica.txt",
        content_type="text/plain",
        content_base64=base64.b64encode(TEXT.encode()).decode(),
        authorized_local_processing=True,
        declared_official=False,
        provenance_note="Documento inventado y decisiones automatizadas exclusivamente de prueba.",
    )
    result = LocalDocuments(db, actor).incorporate(ident, payload, parse_local(payload))
    doc = next(
        d for d in result["documents"] if d["id"] == result["incorporated_document_id"]
    )
    result = LocalDocuments(db, actor).provenance(
        ident,
        doc["id"],
        Provenance(
            expected_document_version=doc["version"],
            decision="REVIEWED",
            reason="Procedencia sintética verificada automáticamente por el test, sin aprobación del cliente.",
        ),
    )
    doc = next(d for d in result["documents"] if d["id"] == doc["id"])
    result = Research(db, actor).extract(
        ident, result["version"], doc["id"], doc["version"]
    )
    for key in [f["id"] for f in result["facts"]]:
        fact = next(f for f in result["facts"] if f["id"] == key)
        if not fact["blockers"]:
            result = Research(db, actor).review(
                ident,
                result["version"],
                key,
                fact["version"],
                "APPROVED",
                "Decisión automatizada del test sobre documento sintético; no es aprobación humana del cliente.",
            )
    return result


def catalogue(db, size):
    from app.database.models import CatalogSnapshot

    record = db.scalar(
        select(CatalogSnapshot).where(CatalogSnapshot.source == "ECOMM_APP_API_STAGE")
    )
    parent = deepcopy(record.payload[0]["items"][0])
    items = []
    for index in range(size):
        item = deepcopy(parent)
        item["code"] = f"BATCH-SYNTHETIC-{index}"
        item["variants"][0].update(id=900001 + index, sku=f"BATCH-SYNTHETIC-{index}")
        items.append(item)
    # Preserve captured pagination; the DB source contract consumes captured pages.
    record.payload = [
        {
            "page": i // 50 + 1,
            "total": size,
            "total_pages": (size + 49) // 50,
            "per_page": 50,
            "captured_at": "2026-11-01T12:00:00+00:00",
            "items": items[i : i + 50],
        }
        for i in range(0, size, 50)
    ]
    db.commit()


def install(factory):
    from app.database.models import CatalogSnapshot

    with factory() as db:
        record = db.scalar(
            select(CatalogSnapshot).where(
                CatalogSnapshot.source == "ECOMM_APP_API_STAGE"
            )
        )
        if (
            not record
            or len(record.payload[0]["items"]) != 6
            or record.payload[0]["items"][0]["description"] != "Almendras sintéticas"
        ):
            raise RuntimeError(
                "El escenario de lotes requiere el catálogo sintético inicial intacto."
            )
        approved(db)


if __name__ == "__main__":
    from .policy import preflight

    preflight()
    from .bootstrap import create_sandbox_app

    create_sandbox_app()
    from app.database.session import SessionLocal

    install(SessionLocal)
