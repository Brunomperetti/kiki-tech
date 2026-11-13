"""Separate, additive PostgreSQL schema. Never part of production Base metadata."""

import hashlib
import json
from sqlalchemy import Integer, JSON, String, select, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from .documents import FIXTURES

SCHEMA = "kiki_research_test"


class ResearchBase(DeclarativeBase):
    pass


class Control(ResearchBase):
    __tablename__ = "control"
    __table_args__ = {"schema": SCHEMA}
    id: Mapped[int] = mapped_column(primary_key=True)


class Document(ResearchBase):
    __tablename__ = "documents"
    __table_args__ = {"schema": SCHEMA}
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    version: Mapped[int] = mapped_column(Integer)
    body: Mapped[dict] = mapped_column(JSON)
    digest: Mapped[str] = mapped_column(String(64))
    history: Mapped[list] = mapped_column(JSON, default=list)


class Dossier(ResearchBase):
    __tablename__ = "dossiers"
    __table_args__ = {"schema": SCHEMA}
    ecomm_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, default=0)
    identity: Mapped[dict] = mapped_column(JSON)
    identity_digest: Mapped[str] = mapped_column(String(64))
    facts: Mapped[list] = mapped_column(JSON, default=list)
    history: Mapped[list] = mapped_column(JSON, default=list)


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def initialize(engine, factory):
    # Called only after 2B preflight + source fixture validation, never from app.main.
    with engine.begin() as connection:
        connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}"))
        ResearchBase.metadata.create_all(connection)
    with factory() as db:
        if not db.get(Control, 1):
            db.add(Control(id=1))
            db.flush()
        db.scalar(select(Control).where(Control.id == 1).with_for_update())
        for key, versions in FIXTURES.items():
            record = db.get(Document, key)
            if record:
                expected = next(
                    (v for v in versions if v["version"] == record.version), None
                )
                if (
                    expected is None
                    or record.digest != digest(expected)
                    or record.body != expected
                ):
                    raise RuntimeError(
                        "Documento no perteneciente a los fixtures sintéticos."
                    )
            else:
                body = versions[0]
                db.add(
                    Document(
                        id=key, version=1, body=body, digest=digest(body), history=[]
                    )
                )
        db.commit()
