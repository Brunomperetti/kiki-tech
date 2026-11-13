"""Opt-in backend consumer of the SAME 2Q queue; no DDL, scheduler or provider IO."""

import logging
from types import SimpleNamespace
from uuid import uuid4
from sqlalchemy import select, func, cast, Text
from app.database.models import CatalogSnapshot
from app.integrations.ecomm_app.catalog_stage import STAGE_SOURCE
from .context import sources
from .service import Batches

log = logging.getLogger(__name__)


class SourceCache:
    """Single bounded capture cache, validated by DB bytes hash under shared lock."""

    def __init__(self):
        self.key = None
        self.value = None

    def load(self, db, lock=False):
        stmt = select(
            CatalogSnapshot.id,
            func.encode(
                func.sha256(
                    func.convert_to(cast(CatalogSnapshot.payload, Text), "UTF8")
                ),
                "hex",
            ).label("signature"),
        ).where(CatalogSnapshot.source == STAGE_SOURCE)
        if lock:
            stmt = stmt.with_for_update(read=True)
        row = db.execute(stmt).first()
        if row is None:
            raise ValueError("Captura API no disponible.")
        key = (id(db.bind), row.id, row.signature)
        if self.key != key:
            value = sources(db, lock=lock)
            self.key, self.value = key, value
        return self.value


class Executor:
    def __init__(self, factory, *, ident=None):
        self.factory = factory
        self.ident = ident or str(uuid4())
        self.cache = SourceCache()
        self.session = SimpleNamespace(id="EJECUTOR:" + self.ident)

    def after_claim(self, claim):
        """Hook for lifecycle instrumentation; cannot bypass ownership validation."""

    def tick(self):
        with self.factory() as db:
            service = Batches(db, self.session, source_loader=self.cache.load)
            claim = service.claim_next()
            if not claim:
                return False
            ident, token, ids, kind = claim
            self.after_claim(claim)
            try:
                if kind == "PREVIEW":
                    service.preview_step(ident, token, ids)
                else:
                    service.process(ident, token, ids)
            except Exception:
                service.fail_claim(ident, token, ids, kind)
                log.warning(
                    "Paso editorial revertido; lote %s; ejecutor %s", ident, self.ident
                )
            return True

    def run(self, stop):
        # Idle polling does not touch providers. Work survives this process in PG.
        while not stop.is_set():
            try:
                worked = self.tick()
            except Exception:
                log.warning(
                    "Ejecutor editorial sin acceso seguro al trabajo; reintento acotado por supervisor."
                )
                raise
            stop.wait(0.05 if worked else 0.4)
