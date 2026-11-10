"""Authorized local documents in existing research test tables; no vendor writes."""

import base64
from copy import deepcopy
import hashlib
import json
import socket
import struct
from urllib.parse import urlsplit
from uuid import uuid4
from .research.service import Research, now
from .research.storage import Document, digest

PARSER_SOCKET = "/document-parser/parser.sock"


def parse_local(body):
    request = json.dumps(
        {
            key: getattr(body, key)
            for key in ("filename", "content_type", "content_base64")
        }
    ).encode()
    if len(request) > 750_000:
        raise ValueError("Archivo superior al límite de lectura.")
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(10)
            connection.connect(PARSER_SOCKET)
            connection.sendall(struct.pack("!I", len(request)) + request)
            with connection.makefile("rb") as stream:
                header = stream.read(4)
                size = struct.unpack("!I", header)[0]
                if not 0 < size <= 524_288:
                    raise ValueError("Resultado fuera de límite.")
                result = json.loads(stream.read(size))
    except (OSError, ValueError, struct.error):
        raise ValueError(
            "Lector aislado no disponible o límite de tiempo/memoria excedido. No se importó el documento."
        ) from None
    if not result.get("ok"):
        raise ValueError(result.get("error", "Documento rechazado."))
    return result["result"]


def valid_url(value):
    if not value:
        return
    try:
        url = urlsplit(value)
        if (
            url.scheme != "https"
            or not url.hostname
            or url.username
            or url.password
            or any(ord(c) < 33 for c in value)
        ):
            raise ValueError
    except ValueError:
        raise ValueError(
            "La referencia debe ser HTTPS y no incluir credenciales. No se descargará."
        ) from None


def public_body(body):
    result = deepcopy(body)
    result.pop("original_base64", None)
    return result


class LocalDocuments:
    def __init__(self, db, session):
        self.db = db
        self.research = Research(db, session)

    def document(self, ident, doc_id):
        doc = self.db.get(Document, doc_id)
        if not doc or doc.body.get("associated_ecomm_id") != ident:
            raise ValueError("Documento local no asociado a este Ecomm ID.")
        return doc

    def store_revision(self, doc, body, action):
        if doc.version >= 8:
            raise ValueError(
                "Límite de 8 versiones del documento en este entorno de pruebas."
            )
        doc.history = doc.history + [
            {
                "at": now(),
                "actor": self.research.actor,
                "action": action,
                "version": doc.version,
                "hash": doc.digest,
                "body": doc.body,
            }
        ]
        doc.version += 1
        body["version"] = doc.version
        doc.body, doc.digest = body, digest(body)
        self.db.flush()

    def incorporate(self, ident, body, parsed, *, acquisition=None):
        case = self.research.dossier(ident)
        self.research.expect(case, body.expected_version)
        valid_url(body.reference_url)
        if not body.authorized_local_processing:
            raise ValueError(
                "Se requiere autorización expresa para procesar este documento localmente."
            )
        if len(body.provenance_note.strip()) < 10:
            raise ValueError(
                "Registrá cómo obtuviste el documento. Una URL o nombre no prueba su procedencia."
            )
        if body.document_id:
            doc = self.document(ident, body.document_id)
            if body.expected_document_version != doc.version:
                raise ValueError("El documento cambió en otra sesión; no se reemplazó.")
            key, version = doc.id, doc.version + 1
        else:
            if (
                len(
                    [
                        d
                        for d in self.research.documents(ident)
                        if d.body.get("associated_ecomm_id")
                    ]
                )
                >= 10
            ):
                raise ValueError(
                    "Máximo 10 documentos locales por variante en pruebas."
                )
            doc, key, version = None, "local-" + uuid4().hex, 1
        if body.kind == "URL":
            if (
                not body.reference_url
                or body.content_base64
                or body.filename
                or body.content_type
            ):
                raise ValueError(
                    "Una referencia URL no contiene archivo ni texto descargado."
                )
            content = {
                "identity": {},
                "sections": {},
                "claims": [],
                "parse_status": "REFERENCE_ONLY",
                "parser_warnings": [],
                "parser_blockers": [],
            }
            original = {
                "filename": None,
                "content_type": None,
                "size": 0,
                "sha256": hashlib.sha256(body.reference_url.encode()).hexdigest(),
            }
        else:
            content = parsed
            raw = base64.b64decode(body.content_base64, validate=True)
            original = {
                "filename": body.filename,
                "content_type": body.content_type,
                "size": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
        content = {
            **content,
            "id": key,
            "version": version,
            "synthetic": False,
            "origin_kind": body.kind,
            "associated_ecomm_id": ident,
            "title": body.filename
            if body.kind == "FILE"
            else "Referencia URL · Sin descargar",
            "kind": "Documento local" if body.kind == "FILE" else "Referencia URL",
            "provenance": "local://sha256/" + original["sha256"],
            "original": original,
            "original_base64": body.content_base64,
            "source": {
                "declared_official": body.declared_official,
                "declared_manufacturer": body.declared_manufacturer.strip() or None,
                "declared_consulted_at": body.declared_consulted_at.isoformat()
                if body.declared_consulted_at
                else None,
                "note": body.provenance_note.strip(),
                "reference_url": body.reference_url,
                "registered_at": now(),
                "registered_by": self.research.actor,
                "review_state": "PENDING",
                "reviewer": None,
                "reviewed_at": None,
                "review_reason": None,
            },
        }
        if acquisition:
            content["retrieval"] = {
                **acquisition["trace"],
                "run_id": acquisition["run_snapshot"]["run_id"],
                "candidate_id": acquisition["candidate_id"],
                "acquired_at": now(),
            }
        if doc:
            self.store_revision(doc, content, "REPLACE_DOCUMENT")
        else:
            doc = Document(
                id=key, version=1, body=content, digest=digest(content), history=[]
            )
            self.db.add(doc)
            self.db.flush()
        self.research.commit_change(
            case,
            deepcopy(case.facts),
            "DOCUMENT_INCORPORATED",
            {"document_id": key, "version": doc.version},
        )
        if acquisition:
            run = deepcopy(acquisition["run_snapshot"])
            candidate = next(
                c for c in run["candidates"] if c["id"] == acquisition["candidate_id"]
            )
            candidate.update(
                document_id=key,
                decision="TRANSFERRED",
                version=candidate["version"] + 1,
            )
            candidate["history"].append(
                {
                    "at": now(),
                    "actor": self.research.actor,
                    "decision": "TRANSFERRED",
                    "document_id": key,
                    "version": candidate["version"],
                }
            )
            self.research.commit_change(
                case, deepcopy(case.facts), "ASSISTED_TRANSFER", run
            )
        self.research.refresh(case)
        result = self.research.serialize(case)
        result["incorporated_document_id"] = key
        return result

    def provenance(self, ident, doc_id, body):
        case = self.research.dossier(ident)
        doc = self.document(ident, doc_id)
        if doc.version != body.expected_document_version:
            raise ValueError(
                "La procedencia cambió en otra sesión; recuperá su versión nueva."
            )
        if len(body.reason.strip()) < 10:
            raise ValueError("Registrá un motivo concreto de revisión de procedencia.")
        updated = deepcopy(doc.body)
        updated["source"].update(
            review_state=body.decision,
            reviewer=self.research.actor,
            reviewed_at=now(),
            review_reason=body.reason.strip(),
        )
        self.store_revision(doc, updated, "PROVENANCE_" + body.decision)
        self.research.commit_change(
            case,
            deepcopy(case.facts),
            "PROVENANCE_REVIEWED",
            {"document_id": doc_id, "decision": body.decision},
        )
        self.research.refresh(case)
        return self.research.serialize(case)

    def original(self, ident, doc_id, version):
        self.research.dossier(ident)
        doc = self.document(ident, doc_id)
        stored = (
            doc.body
            if version == doc.version
            else next((h["body"] for h in doc.history if h["version"] == version), None)
        )
        if not stored:
            raise ValueError("Versión original no disponible.")
        result = {
            "document_id": doc.id,
            "version": version,
            "ecomm_id": ident,
            "original": stored["original"],
            "content_base64": stored["original_base64"],
            "reference_url": stored["source"]["reference_url"],
            "isolated_only": True,
            "external_writes_enabled": False,
        }
        self.db.commit()
        return result
