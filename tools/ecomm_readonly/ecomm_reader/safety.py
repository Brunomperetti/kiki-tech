"""Offline process boundary. No application, database or environment imports."""

from enum import Enum
import sys


class Code(str, Enum):
    OFFLINE_ONLY = "REAL_NETWORK_DISABLED"
    CONTEXT = "BACKEND_OR_DATABASE_FORBIDDEN"
    IO = "NETWORK_PROCESS_OR_WRITE_FORBIDDEN"
    REQUEST = "GET_TARGET_REJECTED"
    DNS = "DNS_OR_DESTINATION_REJECTED"
    REBINDING = "DNS_CHANGED"
    TLS = "TLS_POLICY_OR_PEER_REJECTED"
    REDIRECT = "REDIRECT_REJECTED"
    HTTP = "HTTP_RESPONSE_REJECTED"
    LIMIT = "SIZE_OR_WORK_LIMIT"
    TIME = "TIME_LIMIT"
    JSON = "INVALID_JSON_OR_SCHEMA"
    PAGINATION = "INVALID_OR_CHANGED_PAGINATION"
    ID = "INVALID_OR_DUPLICATE_VARIANT_ID"
    SECRET = "SENSITIVE_DATA_REJECTED"
    CREDENTIAL = "INVALID_CREDENTIAL"
    COMMAND = "UNSUPPORTED_OFFLINE_COMMAND"
    INTERNAL = "OFFLINE_READER_FAILED"


class Failure(ValueError):
    """Never retain/echo arbitrary exceptions, input values or response text."""

    def __init__(self, code):
        self.code = code if isinstance(code, Code) else Code.INTERNAL
        super().__init__(self.code.value)


FORBIDDEN_IMPORTS = (
    "app",
    "backend",
    "sqlalchemy",
    "psycopg",
    "psycopg2",
    "sqlite3",
    "_sqlite3",
    "ctypes",
    "_ctypes",
)
_installed = False


def forbidden_module(name):
    return any(name == p or name.startswith(p + ".") for p in FORBIDDEN_IMPORTS)


def install():
    global _installed
    if any(forbidden_module(name) for name in sys.modules):
        raise Failure(Code.CONTEXT)
    if _installed:
        return

    # No mutable "live" flag is consulted by this irreversible audit hook.
    def guard(event, args):
        if event == "import" and forbidden_module(args[0]):
            raise Failure(Code.CONTEXT)
        if event.startswith("socket.") or event in {
            "subprocess.Popen",
            "os.system",
            "os.exec",
            "os.posix_spawn",
            "os.fork",
            "os.forkpty",
            "sqlite3.connect",
            "ctypes.dlopen",
            "os.remove",
            "os.rename",
            "os.rmdir",
            "os.mkdir",
            "os.link",
            "os.symlink",
            "os.truncate",
            "os.chmod",
            "os.chown",
        }:
            raise Failure(Code.IO)
        if event == "open":
            mode, flags = args[1], args[2]
            # O_WRONLY/RDWR/CREAT/EXCL/TRUNC/APPEND; no persistent reader outputs.
            if (isinstance(mode, str) and any(c in mode for c in "wax+")) or (
                isinstance(flags, int) and flags & (1 | 2 | 64 | 128 | 512 | 1024)
            ):
                raise Failure(Code.IO)

    class NoBackendImports:
        def find_spec(self, fullname, path=None, target=None):
            if forbidden_module(fullname):
                raise Failure(Code.CONTEXT)
            return None

    sys.meta_path.insert(0, NoBackendImports())
    sys.addaudithook(guard)
    _installed = True
