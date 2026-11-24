"""Private browser scenario: fabricated originals and local DNS/HTTP doubles.

Importing this module does not initialize the application or database. The
guarded bootstrap alone installs its route and initializes it after disposable
schema preparation. Nothing here can be selected by the production server.
"""

from urllib.parse import urlsplit

from .ci_stage3_pipeline_smoke import HOST, MockManufacturer, source_url, synthetic_page

VARIANTS = {
    "900003": ("Semillas de chía sintéticas", "250 g"),
    "900004": ("Harina integral sintética", "1 kg"),
    "900005": ("Avena sintética", "500 g"),
    "900006": ("Lentejas sintéticas", "1 kg"),
}
RETRY_ONCE_ID = "900004"


class BrowserManufacturer(MockManufacturer):
    """Same local HTTP/DNS double, actual kernel-guarded reader over UDS."""

    def import_exact(self, db, actor, **kwargs):
        from app.services.documental.explicit_url_intake import import_explicit_url
        from app.services.documental.local_documents import parse_local

        return import_explicit_url(
            db,
            actor,
            **kwargs,
            downloader=self.download,
            parser=parse_local,
        )


def fixture_manufacturer():
    manufacturer = BrowserManufacturer(
        {
            urlsplit(source_url(ident)).path: synthetic_page(name, presentation)
            for ident, (name, presentation) in VARIANTS.items()
        }
    )
    manufacturer.fail_once.add(urlsplit(source_url(RETRY_ONCE_ID)).path)
    return manufacturer


def initialize(application, factory):
    """Keep archived evidence/jobs unchanged on a synthetic API restart."""
    from sqlalchemy import select
    from app.services.documental.source_intake_storage import SourceIntakeJob

    manufacturer = fixture_manufacturer()
    # A restart must not turn a deliberate one-time transport failure into a
    # second failure. Read the existing receipt, do not rewrite or reseed jobs.
    with factory() as db:
        for items in db.scalars(
            select(SourceIntakeJob.items).execution_options(stream_results=True)
        ):
            if any(
                row.get("ecomm_id") == RETRY_ONCE_ID and row.get("attempts", 0) > 0
                for row in items
            ):
                manufacturer.fail_once.clear()
                break
    application.state.stage3_manufacturer = manufacturer


def install_routes(application):
    """Override only the private harness step, preserving core DTO/auth/rules."""
    from uuid import UUID
    from fastapi import APIRouter, Depends, HTTPException
    from sqlalchemy.orm import Session
    from app.core.security import require_csrf
    from app.database.session import get_db
    from app.api.routes.documental_workspace import (
        IntakeRevision,
        _resumable_intake_ready,
    )
    from app.services.documental.source_intake_queue import SourceIntakeQueue

    router = APIRouter()

    class Stage3Queue(SourceIntakeQueue):
        def step(self, ident, revision):
            if self.hosts != frozenset({HOST}):
                raise ValueError("El fabricante del ensayo aislado no coincide.")
            current = self.detail(ident)
            if current["selection_mode"] != "EXACT_OPERATOR_URL":
                raise ValueError("El ensayo admite únicamente URLs sintéticas exactas.")
            manufacturer = application.state.stage3_manufacturer
            return super().step(
                ident, revision, explicit_importer=manufacturer.import_exact
            )

    @router.post("/api/ecomm-app/workspace/sources/intake-jobs/{job_id}/step")
    def step(
        job_id: UUID,
        body: IntakeRevision,
        db: Session = Depends(get_db),
        session=Depends(require_csrf),
    ):
        settings = _resumable_intake_ready(db)
        if not settings.kiki_document_explicit_url_intake_enabled:
            raise HTTPException(403, "URLs sintéticas exactas no habilitadas.")
        try:
            return Stage3Queue(
                db, session, settings.kiki_document_source_fetch_hosts
            ).step(
                str(job_id),
                body.expected_revision,
            )
        except ValueError as exc:
            db.rollback()
            raise HTTPException(409, str(exc)) from None

    application.router.routes[0:0] = router.routes


def verify_reader():
    """Actual backend UDS health with all production kernel checks required."""
    from .policy import preflight, DATABASE_URL

    preflight()
    from app.core import config

    settings = config.Settings(
        _env_file=None,
        database_url=DATABASE_URL,
        kiki_document_parser_kernel_required=True,
    )
    config.get_settings = lambda: settings
    from app.services.documental.local_documents import reader_available

    if not reader_available():
        raise RuntimeError(
            "El lector stage3 no acredita chroot, seccomp y ausencia de secretos."
        )
    print(
        "Lector stage3: reader_available=True con kernel_guard, red nativa denegada, sin /proc, backend ni secretos.",
        flush=True,
    )


if __name__ == "__main__":
    import sys

    if sys.argv[1:] != ["--verify-reader"]:
        raise SystemExit("Sólo se admite verificar el lector sintético.")
    verify_reader()
