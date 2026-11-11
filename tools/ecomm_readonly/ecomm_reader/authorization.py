"""Offline verification of an owner's scope attestation, NOT token introspection.

No production config imports, token discovery, issuance, refresh or API calls.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import os
import re
import stat

from .catalog import unique_object
from .policy import BARCODE, HOST, PATH
from .safety import Code, Failure
from .wire import Credential

SCOPE = "inventario:leer"
FIELDS = {
    "version",
    "host",
    "path",
    "method",
    "barcode",
    "max_pages",
    "scopes",
    "credential_sha256",
    "account_reference",
    "permissions_reference",
    "reviewed_at",
    "expires_at",
    "reviewed_by_owner",
}


def utcnow():
    return datetime.now(timezone.utc)


def timestamp(value):
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value
    ):
        raise Failure(Code.AUTHORIZATION)
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@dataclass(frozen=True, repr=False)
class QueryAuthorization:
    credential: Credential = field(repr=False)
    max_pages: int
    evidence_sha256: str
    reviewed_at: datetime
    expires_at: datetime

    def validate(self, *, now=None):
        now = now or utcnow()
        if (
            type(self.credential) is not Credential
            or type(self.max_pages) is not int
            or self.max_pages not in (1, 2)
            or not re.fullmatch(r"[0-9a-f]{64}", self.evidence_sha256)
            or self.reviewed_at > now + timedelta(seconds=60)
            or self.expires_at <= now
            or self.expires_at <= self.reviewed_at
            or self.expires_at - self.reviewed_at > timedelta(hours=24)
            or now - self.reviewed_at > timedelta(hours=24)
        ):
            raise Failure(Code.AUTHORIZATION)


def attest(credential, body, *, max_pages=1, now=None):
    """Bind owner-supplied scope metadata to THIS secret, without displaying it.

    Only the vendor/account owner can attest actual permissions. A SHA binds the
    record to the supplied token; it does not verify the provider's scope state.
    """
    try:
        if type(credential) is not Credential or len(body) > 16384:
            raise Failure(Code.AUTHORIZATION)
        value = json.loads(body.decode("utf-8"), object_pairs_hook=unique_object)
        if (
            not isinstance(value, dict)
            or set(value) != FIELDS
            or type(value["version"]) is not int
            or value["version"] != 1
            or value["host"] != HOST
            or value["path"] != PATH
            or value["method"] != "GET"
            or value["barcode"] != BARCODE
            or value["scopes"] != [SCOPE]
            or value["reviewed_by_owner"] is not True
            or type(value["max_pages"]) is not int
            or value["max_pages"] not in (1, 2)
            or type(max_pages) is not int
            or max_pages not in (1, 2)
            or max_pages > value["max_pages"]
        ):
            raise Failure(Code.AUTHORIZATION)
        for key in ("account_reference", "permissions_reference"):
            if (
                not isinstance(value[key], str)
                or not 1 <= len(value[key].strip()) <= 200
                or any(ord(c) < 32 for c in value[key])
                or credential.value in value[key]
            ):
                raise Failure(Code.AUTHORIZATION)
        fingerprint = hashlib.sha256(credential.value.encode("ascii")).hexdigest()
        if not isinstance(value["credential_sha256"], str) or not hmac.compare_digest(
            fingerprint, value["credential_sha256"]
        ):
            raise Failure(Code.AUTHORIZATION)
        grant = QueryAuthorization(
            credential,
            max_pages,
            hashlib.sha256(body).hexdigest(),
            timestamp(value["reviewed_at"]),
            timestamp(value["expires_at"]),
        )
        grant.validate(now=now)
        return grant
    except Failure:
        raise
    except Exception:
        raise Failure(Code.AUTHORIZATION) from None


def read_private(path, limit):
    """Linux/WSL: owner-only regular file, no symlinks/FIFO/devices/hardlinks.

    A secret manager/owner provisions these files separately. Never copy .env.
    """
    fd = None
    try:
        if not isinstance(path, str) or not path.startswith("/") or "\x00" in path:
            raise Failure(Code.SECRET_FILE)
        if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "geteuid"):
            raise Failure(Code.SECRET_FILE)
        fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK)
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.geteuid()
            or info.st_mode & 0o077
            or info.st_nlink != 1
            or not 0 < info.st_size <= limit
        ):
            raise Failure(Code.SECRET_FILE)
        raw = bytearray()
        while len(raw) <= limit:
            chunk = os.read(fd, min(4096, limit + 1 - len(raw)))
            if not chunk:
                break
            raw.extend(chunk)
        after = os.fstat(fd)
        if (
            len(raw) > limit
            or len(raw) != info.st_size
            or (after.st_size, after.st_mtime_ns, after.st_ctime_ns)
            != (info.st_size, info.st_mtime_ns, info.st_ctime_ns)
        ):
            raise Failure(Code.SECRET_FILE)
        return bytes(raw)
    except Failure:
        raise
    except Exception:
        raise Failure(Code.SECRET_FILE) from None
    finally:
        if fd is not None:
            os.close(fd)


def load_authorization(credential_path, evidence_path, *, max_pages=1):
    try:
        raw = read_private(credential_path, 4097)
        if raw.endswith(b"\n"):
            raw = raw[:-1]
        credential = Credential(raw.decode("ascii"))
    except Exception:
        raise Failure(Code.CREDENTIAL) from None
    return attest(credential, read_private(evidence_path, 16384), max_pages=max_pages)
