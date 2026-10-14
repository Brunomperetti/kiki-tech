"""Persistent human review of AI drafts with source-change detection."""
import hashlib
import json
from datetime import datetime, timedelta, timezone
from sqlalchemy import select

from ..database.models import TiendanubeAiDraftRecord
from ..core.config import get_settings
from .tiendanube_ai_pilot_service import TiendanubeAiPilotService


class TiendanubeAiDraftReviewService:
    def __init__(self, db):
        self.db = db
        self.ai = TiendanubeAiPilotService(db)

    def fingerprint(self, product_key):
        rows = self.ai.proposals.catalog.repo.snapshot("TIENDANUBE")
        selected = [r for r in rows if str(r.get("slug") or "").strip() == product_key]
        if not selected:
            raise ValueError("El producto ya no existe en la importación de Tiendanube.")
        canonical = json.dumps(selected, sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha256(canonical.encode()).hexdigest()

    def view(self, product_key):
        record = self.db.scalar(select(TiendanubeAiDraftRecord).where(
            TiendanubeAiDraftRecord.product_key == product_key
        ))
        if record is None:
            return {"available": False, "product_key": product_key}
        try:
            current = self.fingerprint(product_key)
            stale = current != record.evidence_hash
        except ValueError:
            stale = True
        return {"available": True, "product_key": product_key,
                "status": "STALE" if stale else record.status,
                "stale": stale, "draft": record.draft,
                "history": record.history, "note": record.note}

    def generate_and_save(self, product_key):
        evidence_hash = self.fingerprint(product_key)
        settings = get_settings()
        if not settings.kiki_ai_enabled or not settings.kiki_ai_api_key:
            raise RuntimeError("El piloto de IA está deshabilitado.")
        if not 1 <= settings.kiki_ai_daily_request_limit <= 100:
            raise RuntimeError("Configuración del límite diario de IA inválida.")
        if not 1 <= settings.kiki_ai_min_regenerate_hours <= 720:
            raise RuntimeError("Configuración del intervalo de IA inválida.")
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=1)
        records = self.db.scalars(select(TiendanubeAiDraftRecord)).all()
        # This is an additional conservative application-level guard, not a
        # concurrency-safe monetary quota. A hard cost ceiling belongs at the API provider.
        usage = 0
        for existing in records:
            generated = [
                datetime.fromisoformat(event["at"])
                for event in (existing.history or [])
                if event.get("event") == "AI_GENERATED" and event.get("at")
            ]
            usage += sum(timestamp >= cutoff for timestamp in generated)
            if existing.product_key == product_key and generated:
                if now - max(generated) < timedelta(hours=settings.kiki_ai_min_regenerate_hours):
                    raise ValueError("Ya existe un borrador reciente. Consultalo antes de volver a generar.")
        if usage >= settings.kiki_ai_daily_request_limit:
            raise ValueError("Se alcanzó el límite diario de solicitudes de IA. Probá mañana.")
        draft = self.ai.draft(product_key)
        # Do not persist a result if another request/import changed its source during generation.
        if self.fingerprint(product_key) != evidence_hash:
            raise ValueError("El catálogo cambió durante la generación. Volvé a revisar la ficha.")
        record = self.db.scalar(select(TiendanubeAiDraftRecord).where(
            TiendanubeAiDraftRecord.product_key == product_key
        ))
        if record is None:
            record = TiendanubeAiDraftRecord(product_key=product_key, history=[])
            self.db.add(record)
        event = {"at": datetime.now(timezone.utc).isoformat(), "event": "AI_GENERATED",
                 "evidence_hash": evidence_hash, "draft": draft}
        record.evidence_hash = evidence_hash
        record.draft = draft
        record.status = "PENDING_REVIEW"
        record.note = None
        record.history = [*(record.history or []), event][-100:]
        record.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        return self.view(product_key)

    def review(self, product_key, decision, note):
        if decision not in {"APPROVED_INTERNAL", "REJECTED"}:
            raise ValueError("Decisión no admitida.")
        if len((note or "").strip()) < 10:
            raise ValueError("El motivo debe tener al menos 10 caracteres.")
        record = self.db.scalar(select(TiendanubeAiDraftRecord).where(
            TiendanubeAiDraftRecord.product_key == product_key
        ))
        if record is None:
            raise ValueError("No existe un borrador generado para este producto.")
        if self.fingerprint(product_key) != record.evidence_hash:
            raise ValueError("La ficha cambió desde que se generó la propuesta. Generá un nuevo borrador.")
        if record.status != "PENDING_REVIEW":
            raise ValueError("El borrador ya fue evaluado; generá uno nuevo para cambiar la decisión.")
        record.status = decision
        record.note = note.strip()
        record.history = [*(record.history or []), {
            "at": datetime.now(timezone.utc).isoformat(), "event": decision,
            "note": note.strip(), "evidence_hash": record.evidence_hash
        }][-100:]
        record.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        return self.view(product_key)
