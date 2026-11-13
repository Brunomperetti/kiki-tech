"""Default-deny boundary with scoped native calls for an authorized query only."""

from enum import Enum
from contextlib import contextmanager
from contextvars import ContextVar
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
    AUTHORIZATION = "MISSING_OR_INVALID_SCOPE_ATTESTATION"
    SECRET_FILE = "PRIVATE_CREDENTIAL_FILE_REQUIRED"
    ENVIRONMENT = "DIRECT_VERIFIED_TRANSPORT_UNAVAILABLE"


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
_network_call = ContextVar("ecomm_single_native_call", default=None)


@contextmanager
def native_call(grant, operation, *, channel=None, address=None, family=None):
    """One closed native operation, never a process-wide/network environment flag.

    Imported lazily so offline import installs the default-deny guard first.
    Both the authority and the deployment environment are checked at every call.
    """
    from .authorization import QueryAuthorization
    from .native import require_direct_environment

    if type(grant) is not QueryAuthorization:
        raise Failure(Code.AUTHORIZATION)
    grant.validate()
    require_direct_environment()
    if operation not in {"dns", "open", "connect", "tls"}:
        raise Failure(Code.IO)
    token = _network_call.set((operation, channel, address, family))
    try:
        yield
    finally:
        _network_call.reset(token)


def permitted_socket_event(event, args):
    from .policy import HOST, public_addresses

    scope = _network_call.get()
    if scope is None:
        return False
    operation, channel, address, family = scope
    if event == "socket.getaddrinfo" and operation == "dns":
        # AF_UNSPEC=0, SOCK_STREAM=1, IPPROTO_TCP=6, flags=0, fixed host/port.
        return args == (HOST, 443, 0, 1, 6, 0)
    if event == "socket.__new__" and operation in {"open", "tls"}:
        return args[1:] == (family, 1, 6) and family in (2, 10)
    if event == "socket.connect" and operation == "connect":
        if args[0] is not channel or args[1] != address:
            return False
        public_addresses([address[0]])
        return address[1] == 443
    return False


def forbidden_module(name):
    return any(name == p or name.startswith(p + ".") for p in FORBIDDEN_IMPORTS)


def install():
    global _installed
    if any(forbidden_module(name) for name in sys.modules):
        raise Failure(Code.CONTEXT)
    if _installed:
        return

    # No environment/CLI "live" flag relaxes this irreversible audit hook.
    # A typed, validated grant permits only the exact native call in its scope.
    def guard(event, args):
        if event == "import" and forbidden_module(args[0]):
            raise Failure(Code.CONTEXT)
        if event.startswith("socket."):
            if not permitted_socket_event(event, args):
                raise Failure(Code.IO)
        if event in {
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
