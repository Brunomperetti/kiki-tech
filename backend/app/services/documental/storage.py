"""Additive tables in the existing database; installed only by explicit migration."""

import hashlib
import json
from sqlalchemy import Integer, JSON, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

SCHEMA = None


class ResearchBase(DeclarativeBase):
    pass


class Control(ResearchBase):
    __tablename__ = "kiki_evidence_control"
    __table_args__ = {"schema": SCHEMA}
    id: Mapped[int] = mapped_column(primary_key=True)


class Document(ResearchBase):
    __tablename__ = "kiki_evidence_documents"
    __table_args__ = {"schema": SCHEMA}
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    version: Mapped[int] = mapped_column(Integer)
    body: Mapped[dict] = mapped_column(JSON)
    digest: Mapped[str] = mapped_column(String(64))
    history: Mapped[list] = mapped_column(JSON, default=list)


class Dossier(ResearchBase):
    __tablename__ = "kiki_evidence_dossiers"
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
