"""Private E4 browser data, entirely authored for offline acceptance tests.

The local original bytes, source decisions and fact approvals below are a
SYNTHETIC SEED, not customer/manufacturer evidence or actual human acceptance.
The browser must explicitly perform each new commercial decision afterwards.
Importing this module does not import the application or create any database.
"""
import base64
from copy import deepcopy
import os
from types import SimpleNamespace

ELIGIBLE_IDS = tuple(str(9104001 + index) for index in range(20))
PACK_ID = "9104091"
SHARED_IDS = ("9104092", "9104093")
NATURAL_SEED_ID = "7518949"
EXCEPTION_IDS = (PACK_ID, *SHARED_IDS, NATURAL_SEED_ID)
ALL_IDS = (*ELIGIBLE_IDS, *EXCEPTION_IDS)
HOST = "fabricante-stage4.invalid"
SOURCE_MARKER = "KIKI_STAGE4_SYNTHETIC_ONLY"
REASON = "SYNTHETIC TEST SEED: authored original and fixture-only decision; not a manufacturer or customer approval."


def _gtin(ident):
    first = "200" + f"{int(ident):09d}"
    checksum = (10 - sum(int(digit) * (3 if index % 2 == 0 else 1)
                         for index, digit in enumerate(reversed(first))) % 10) % 10
    return first + str(checksum)


def source_url(ident):
    return f"https://{HOST}/producto/{ident}/"


def image_url(ident):
    return f"https://{HOST}/recursos/{ident}.png"


def video_url(ident):
    return f"https://{HOST}/recursos/{ident}.mp4"


def _name(ident):
    if ident == NATURAL_SEED_ID:
        return "Mix Natural Seed · CASO SINTÉTICO de falta de licencia"
    if ident == PACK_ID:
        return "Semillas de ensayo E4 · pack x2"
    if ident in SHARED_IDS:
        return "Semillas de ensayo E4 · código compartido " + ident
    return "Semillas sintéticas E4 " + f"{int(ident) - 9104000:02d}"


def baseline_capture():
    """Exact initial six-variant fixture from integration_sandbox.fixtures."""
    items = []
    for index, (name, presentation, sku) in enumerate([
        ("Almendras sintéticas", "250 g", "DEMO-ALM"),
        ("Almendras sintéticas", "1 kg", "DEMO-ALM"),
        ("Semillas de chía sintéticas", "250 g", "DEMO-CHIA"),
        ("Harina integral sintética", "1 kg", "DEMO-HAR"),
        ("Avena sintética", "500 g", "DEMO-AVE"),
        ("Lentejas sintéticas", "1 kg", "DEMO-LEN"),
    ], 1):
        items.append({
            "code": f"SYNTHETIC-{index}", "description": name, "is_combo": False,
            "variants": [{"id": 900000 + index, "sku": sku,
                          "description": presentation, "is_combo": False,
                          "gtin": None, "total_stock": index * 3, "warehouses": []}],
        })
    return [{"page": 1, "total": 6, "total_pages": 1, "per_page": 50,
             "captured_at": "2026-11-01T12:00:00+00:00", "items": items}]


def capture():
    pages = baseline_capture()
    for ident in ALL_IDS:
        combo = ident == PACK_ID
        presentation = "2 x 250 g" if combo else "250 g"
        barcode = _gtin(SHARED_IDS[0] if ident in SHARED_IDS else ident)
        pages[0]["items"].append({
            "code": "STAGE4-SYNTHETIC-" + ident,
            "description": _name(ident), "is_combo": combo,
            "variants": [{
                "id": int(ident), "sku": "E4-SYNTHETIC-" + ident,
                "description": presentation, "variant_description": presentation,
                "is_combo": combo, "barcode": barcode, "gtin": None,
                "total_stock": 3, "warehouses": [],
            }],
        })
    pages[0].update(total=len(pages[0]["items"]),
                    captured_at="2026-11-24T18:00:00+00:00", scenario=SOURCE_MARKER)
    return pages


def original_text(ident):
    lines = [f"Nombre: {_name(ident)}", "Presentación: " + ("2 x 250 g" if ident == PACK_ID else "250 g"),
             "Tipo de venta: " + ("Combo" if ident == PACK_ID else "Unidad"),
             "Características: Material ficticio para pruebas locales de catálogo"]
    if ident != NATURAL_SEED_ID:
        lines.extend([
            "Marca: Marca sintética E4", "Fabricante: Fabricante sintético E4",
            "Categoría: Dietética sintética", "Subcategoría: Semillas de ensayo",
            "Conservación: Mantener en un lugar ficticio de prueba",
            f"Licencia imagen: El titular autoriza el uso comercial de {image_url(ident)} para el catálogo KIKI, presentación 250 g, hasta 2030-12-31.",
            f"Licencia video: El titular autoriza el uso comercial de {video_url(ident)} para el catálogo KIKI, presentación 250 g, hasta 2030-12-31.",
        ])
    return "\n".join(lines) + "\n"


def _guard(db):
    from sqlalchemy import text
    from app.core.config import get_settings
    from .policy import DATABASE_URL, MARKER

    if (os.environ.get("KIKI_INTEGRATION_MODE") != "local-synthetic"
            or get_settings().database_url != DATABASE_URL):
        raise RuntimeError("Stage4 fixtures require the checked disposable sandbox.")
    actual = db.execute(text("""SELECT current_database(), current_user, inet_server_addr(),
      shobj_description(oid, 'pg_database') FROM pg_database
      WHERE datname=current_database()""")).one()
    if tuple(actual) != ("kiki_integration", "kiki_integration", None, MARKER):
        raise RuntimeError("Stage4 refused a non-synthetic PostgreSQL identity.")


def initialize(factory):
    """Seed once; later restarts preserve all explicit browser decisions."""
    from sqlalchemy import select
    from app.database.models import CatalogSnapshot, EcommApiProductEdit, MercadoLibreConnection
    from app.services.documental.contracts import Incorporate, Provenance
    from app.services.documental.local_documents import LocalDocuments, parse_local
    from app.services.documental.research import Research
    from app.services.documental.proposals import Proposals
    from app.services.documental.storage import Document
    from app.services.ecomm_api_product_workspace_service import EcommApiProductWorkspace, blank_fields

    with factory() as db:
        _guard(db)
        if db.scalar(select(MercadoLibreConnection)):
            raise RuntimeError("Provider connections do not belong in stage4 fixtures.")
        snapshot = db.scalar(select(CatalogSnapshot).where(CatalogSnapshot.source == "ECOMM_APP_API_STAGE"))
        if snapshot and snapshot.payload == capture():
            return
        if snapshot is None or snapshot.payload != baseline_capture():
            raise RuntimeError("Stage4 only promotes the exact initial synthetic capture.")
        if db.scalar(select(EcommApiProductEdit.ecomm_id).where(EcommApiProductEdit.ecomm_id.in_(ALL_IDS))):
            raise RuntimeError("Stage4 will not replace existing commercial records.")
        if db.scalar(select(Document.id).where(Document.body["associated_ecomm_id"].as_string().in_(ALL_IDS))):
            raise RuntimeError("Stage4 will not replace existing documentary records.")
        preparing = capture()
        preparing[0]["scenario"] = "KIKI_STAGE4_PREPARING"
        snapshot.payload = preparing
        db.commit()

        actor = SimpleNamespace(id="SYNTHETIC_STAGE4_FIXTURE_SEED_NOT_HUMAN")
        for ident in ALL_IDS:
            raw = original_text(ident).encode("utf-8")
            request = Incorporate(
                kind="FILE", expected_version=0,
                filename="solo-prueba-stage4-" + ident + ".txt",
                content_type="text/plain", content_base64=base64.b64encode(raw).decode("ascii"),
                provenance_note=REASON, reference_url=source_url(ident),
                declared_official=False, authorized_local_processing=True,
            )
            service = LocalDocuments(db, actor)
            added = service.incorporate(ident, request, parse_local(request))
            document_id = added["incorporated_document_id"]
            source = db.get(Document, document_id)
            reviewed = service.provenance(ident, document_id, Provenance(
                expected_document_version=source.version, decision="REVIEWED", reason=REASON,
            ))
            source = db.get(Document, document_id)
            research = Research(db, actor)
            extracted = research.extract(ident, reviewed["version"], document_id, source.version)
            chosen = [SimpleNamespace(fact_id=fact["id"], expected_fact_version=fact["version"], reason=REASON)
                      for fact in extracted["facts"] if fact["state"] == "PENDING" and fact["document_id"] == document_id]
            if not chosen:
                raise RuntimeError("Stage4 fixture original did not produce cited candidates.")
            research.review_batch(ident, extracted["version"], document_id, source.version, chosen)

            fields = blank_fields()
            fields["note"] = REASON
            fields["presentation"] = "2 x 250 g" if ident == PACK_ID else "250 g"
            if ident in {ELIGIBLE_IDS[0], NATURAL_SEED_ID}:
                fields["media"] = [{"kind": "IMAGE", "url": image_url(ident),
                                    "alt": "Imagen SINTÉTICA de ensayo", "source_url": source_url(ident)}]
                if ident != NATURAL_SEED_ID:
                    fields["media"].append({"kind": "VIDEO", "url": video_url(ident),
                                             "alt": "Video SINTÉTICO de ensayo", "source_url": source_url(ident)})
            if ident == NATURAL_SEED_ID:
                fields.update(title=_name(ident), presentation="250 g")
            workspace = EcommApiProductWorkspace(db)
            saved = workspace.save(ident, fields, "DRAFT", 0)
            if ident == NATURAL_SEED_ID:
                for number in range(2, 7):
                    fields["note"] = REASON + " · versión sintética " + str(number)
                    saved = workspace.save(ident, deepcopy(fields), "DRAFT", saved["version"])
                if saved["status"] != "DRAFT" or saved["version"] != 6:
                    raise RuntimeError("Stage4 incomplete fixture must remain DRAFT v6.")
            # Proposals are fixture setup, not field acceptance. The actual
            # browser operator must choose fields and confirm a DRAFT save.
            Proposals(db, actor).generate(ident, saved["version"])
        snapshot = db.scalar(select(CatalogSnapshot).where(CatalogSnapshot.source == "ECOMM_APP_API_STAGE"))
        snapshot.payload = capture()
        db.commit()
        print("Stage4: 20 units + pack/shared-code/incomplete fixtures, actual local originals; prior approvals are explicitly SYNTHETIC SEEDS, not human acceptance.", flush=True)
