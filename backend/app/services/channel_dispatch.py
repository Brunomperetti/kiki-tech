"""Durable dispatch guard. No provider calls and no automatic retries.

Use a dedicated transaction per operation. The caller must commit IN_FLIGHT
before performing any network mutation. A crash leaves a blocked record;
there is deliberately no reset or retry transition.
"""
import re
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from .channel_dispatch_storage import ChannelDispatch


class DispatchConflict(ValueError):
    pass


def _now():
    return datetime.now(timezone.utc)


def reserve(db, *, channel, store_id, ecomm_id, sku, fingerprint, actor):
    if channel not in {"tn", "ml"}:
        raise ValueError("Canal inválido.")
    if not isinstance(fingerprint, str) or not re.fullmatch(r"[a-f0-9]{64}", fingerprint):
        raise ValueError("Previsualización inválida.")
    values = (store_id, ecomm_id, sku, actor)
    limits = (64, 64, 256, 240)
    if any(not isinstance(v, str) or not v.strip() or len(v.strip()) > limit
           for v, limit in zip(values, limits)):
        raise ValueError("Identidad de envío inválida.")
    sku_key = sku.strip().casefold()
    if len(sku_key) > 256:
        raise ValueError("SKU demasiado largo.")
    now = _now()
    ident = str(uuid4())
    record = ChannelDispatch(
        id=ident, channel=channel, store_id=store_id.strip(),
        ecomm_id=ecomm_id.strip(), sku_key=sku_key, fingerprint=fingerprint,
        actor=actor.strip(), state="RESERVED", revision=1,
        created_at=now, updated_at=now,
    )
    try:
        db.add(record)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise DispatchConflict("Ya existe una reserva o envío para esa identidad o SKU.") from None
    return ident


def _transition(db, ident, revision, expected, target, remote_id=None):
    if type(revision) is not int or revision < 1:
        raise ValueError("Revisión inválida.")
    result = db.execute(
        update(ChannelDispatch)
        .where(ChannelDispatch.id == ident,
               ChannelDispatch.revision == revision,
               ChannelDispatch.state == expected)
        .values(state=target, revision=revision + 1, updated_at=_now(),
                remote_id=remote_id)
    )
    if result.rowcount != 1:
        db.rollback()
        raise DispatchConflict("El estado del envío cambió; no repetir la operación.")
    db.commit()
    return revision + 1


def begin(db, ident, revision):
    return _transition(db, ident, revision, "RESERVED", "IN_FLIGHT")


def confirm(db, ident, revision, remote_id):
    if not isinstance(remote_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", remote_id):
        raise ValueError("Identificador remoto inválido.")
    return _transition(db, ident, revision, "IN_FLIGHT", "CONFIRMED", remote_id)


def mark_unknown(db, ident, revision):
    return _transition(db, ident, revision, "IN_FLIGHT", "UNKNOWN")


def read_receipt(db, ident):
    row = db.scalar(select(ChannelDispatch).where(ChannelDispatch.id == ident)
                    .execution_options(populate_existing=True))
    if row is None:
        raise ValueError("Envío inexistente.")
    return {key: getattr(row, key) for key in (
        "id", "channel", "store_id", "ecomm_id", "sku_key", "fingerprint",
        "state", "revision", "remote_id", "created_at", "updated_at",
    )}
