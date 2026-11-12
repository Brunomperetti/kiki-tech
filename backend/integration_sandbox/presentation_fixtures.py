"""One presentation scenario, using existing services. No approvals or provider IO."""

import base64
from pathlib import Path
from types import SimpleNamespace

TEXT = """Nombre: Semillas de chía sintéticas
Marca: Marca sintética KIKI
Fabricante: Fabricante de prueba
EAN: 12345670
Presentación: 250 g
Tipo de venta: Unidad
Contenido neto: 250 g
Características: Semillas enteras de demostración
Categoría: Dietética
Subcategoría: Semillas
"""
ACTOR = SimpleNamespace(id="PRESENTACION-PREPARACION-AUTOMATIZADA-SIN-APROBACIONES")


def install(factory):
    from .channel_fixtures import install as channels
    from app.services.documental.local_documents import LocalDocuments, parse_local
    from app.services.documental.contracts import Incorporate
    from app.services.documental.research import Research

    # This existing installer refuses an occupied/unknown catalogue before writing.
    channels(factory)
    with factory() as db:
        research = Research(db, ACTOR)
        case = research.dossier("900003")
        body = Incorporate(
            kind="FILE",
            expected_version=case.version,
            filename="presentacion-chia-exclusivamente-sintetica.txt",
            content_type="text/plain",
            content_base64=base64.b64encode(TEXT.encode()).decode(),
            authorized_local_processing=True,
            declared_official=False,
            provenance_note="Documento inventado para la presentación. No es del cliente ni de un fabricante real. Ningún hecho está aprobado.",
        )
        result = LocalDocuments(db, ACTOR).incorporate(
            "900003", body, parse_local(body)
        )
        doc = next(
            d
            for d in result["documents"]
            if d["id"] == result["incorporated_document_id"]
        )
        research.extract("900003", result["version"], doc["id"], doc["version"])

        from .hileret_routes import prepare
        from .hileret_reference import UNIT_ID, URL
        from .hileret_brochure import matches
        from .research.service import Research as PilotResearch
        from .document_routes import Incorporate as PilotIncorporate
        from .local_documents import (
            LocalDocuments as PilotDocuments,
            parse_local as pilot_parse,
        )

        prepare(db, ACTOR)
        original = Path("/pilot-inputs/hileret-original.pdf")
        if not original.is_file():
            print(
                "Hileret pendiente: PDF original no disponible; no fue procesado.",
                flush=True,
            )
            return
        raw = original.read_bytes()
        if not matches(raw):
            raise ValueError("Original Hileret incompatible; no se amplían límites.")
        pilot = PilotResearch(db, ACTOR)
        case = pilot.dossier(UNIT_ID)
        body = PilotIncorporate(
            kind="FILE",
            expected_version=case.version,
            filename="Folleto Ventas Hileret 17x25_400s.pdf",
            content_type="application/pdf",
            content_base64=base64.b64encode(raw).decode(),
            reference_url=URL,
            declared_official=True,
            authorized_local_processing=True,
            provenance_note="Original suministrado por el usuario, quien declara descarga oficial. Hash y página 2 comprobados localmente. Sin descarga web ni aprobación humana inferida.",
        )
        result = PilotDocuments(db, ACTOR).incorporate(UNIT_ID, body, pilot_parse(body))
        doc = next(
            d
            for d in result["documents"]
            if d["id"] == result["incorporated_document_id"]
        )
        pilot.extract(UNIT_ID, result["version"], doc["id"], doc["version"])
    print(
        "Presentación preparada: catálogo/canales sintéticos y PDF Hileret auténtico; cero aprobaciones automáticas.",
        flush=True,
    )


if __name__ == "__main__":
    from .policy import preflight

    preflight()
    from .bootstrap import create_sandbox_app

    create_sandbox_app()
    from app.database.session import SessionLocal

    install(SessionLocal)
