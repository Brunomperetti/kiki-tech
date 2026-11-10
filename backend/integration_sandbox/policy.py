"""No application imports: these checks must precede engine initialization."""

import os
import sys
import re
from collections.abc import Mapping

DATABASE_URL = (
    "postgresql+psycopg://kiki_integration:kiki-synthetic-only@/kiki_integration"
    "?host=/var/run/postgresql&port=5432"
)
MARKER = "KIKI_LOCAL_SYNTHETIC_2B"
PG_SOCKET = "/var/run/postgresql/.s.PGSQL.5432"
ALLOWED_ROUTES = frozenset(
    {
        ("GET", "/health"),
        ("POST", "/api/auth/login"),
        ("GET", "/api/auth/me"),
        ("POST", "/api/auth/logout"),
        ("GET", "/api/ecomm-app/stage/catalog"),
    }
)


def is_workspace_route(method: str, path: str) -> bool:
    # Deliberately only the six synthetic variants; no reserved/AI/bulk subroutes.
    return method in {"GET", "POST"} and bool(
        re.fullmatch(r"/api/ecomm-app/workspace/90000[1-6]", path)
    )


def route_allowed(method: str, path: str) -> bool:
    return (
        (method, path) in ALLOWED_ROUTES
        or is_workspace_route(method, path)
        or is_research_route(method, path)
    )


def is_research_route(method: str, path: str) -> bool:
    if method == "GET":
        return bool(re.fullmatch(r"/api/test-research/90000[1-6]", path))
    if method != "POST":
        return False
    return bool(
        re.fullmatch(
            r"/api/test-research/90000[1-6]/(?:extract|facts/[a-z0-9.:-]{1,160}/review)",
            path,
        )
        or re.fullmatch(r"/api/test-research/documents/[a-z0-9-]{1,80}/revision", path)
    )


CSP = (
    "default-src 'none'; connect-src 'self'; img-src 'none'; media-src 'none'; "
    "frame-src 'none'; frame-ancestors 'none'; form-action 'none'; base-uri 'none'"
)


class IsolationError(RuntimeError):
    pass


def validate_environment(environ: Mapping[str, str]) -> None:
    if environ.get("KIKI_INTEGRATION_MODE") != "local-synthetic":
        raise IsolationError("Se requiere modo explícito local-synthetic.")
    if environ.get("DATABASE_URL") != DATABASE_URL:
        raise IsolationError(
            "Destino rechazado: sólo PostgreSQL sintético por socket local."
        )
    # Reject inherited application settings, including alternate case. No values in errors.
    generic = {
        "APP_NAME",
        "CORS_ORIGINS",
        "MAX_UPLOAD_MB",
        "APP_SESSION_SECRET",
        "APP_ENCRYPTION_KEY",
        "SESSION_TTL_HOURS",
        "FRONTEND_URL",
        "ENABLE_API_DOCS",
        "AUTH_MAX_ATTEMPTS",
        "AUTH_WINDOW_MINUTES",
        "AUTH_BLOCK_MINUTES",
        "PGHOST",
        "PGHOSTADDR",
        "PGPORT",
        "PGDATABASE",
        "PGUSER",
        "PGPASSWORD",
        "PGSERVICE",
        "PGSERVICEFILE",
        "PGPASSFILE",
        "PGOPTIONS",
        "PGSSLMODE",
    }
    for key, value in environ.items():
        upper = key.upper()
        if upper in {"DATABASE_URL", "KIKI_INTEGRATION_MODE"}:
            if key != upper:
                raise IsolationError("Configuración duplicada o ambigua rechazada.")
            continue
        if upper in generic or upper.startswith(("KIKI_", "ML_", "ECOMM_", "OPENAI_")):
            raise IsolationError(
                "Configuración heredada de aplicación/proveedor rechazada."
            )
        if upper.endswith("_PROXY") and value:
            raise IsolationError("Proxies de salida prohibidos en ejecución.")
    if any(name == "app" or name.startswith("app.") for name in sys.modules):
        raise IsolationError(
            "El aislamiento debe validarse antes de importar la aplicación."
        )


def install_network_guard(*, unix_socket: str = PG_SOCKET) -> None:
    """Defense in depth. Docker network_mode:none also covers native libpq/C calls.

    Irreversible per process. Tests of rejected calls run in this same guarded process.
    This is not a general Python sandbox; containers must not mount tools/secrets.
    """

    def guard(event, args):
        if event == "socket.connect":
            address = args[1]
            if address != unix_socket:
                raise IsolationError("Conexión de salida bloqueada.")
        if event in {
            "socket.getaddrinfo",
            "socket.gethostbyname",
            "socket.gethostbyaddr",
            "socket.sendto",
            "socket.sendmsg",
            "subprocess.Popen",
            "os.system",
            "os.exec",
            "os.posix_spawn",
            "os.fork",
            "os.forkpty",
        }:
            raise IsolationError("Red/procesos externos bloqueados por aislamiento.")

    sys.addaudithook(guard)


def validate_database_identity(connection) -> None:
    # No DDL, migrations or app imports before these server-side assertions.
    row = connection.execute("""
        SELECT current_database(), current_user, inet_server_addr(),
               shobj_description(oid, 'pg_database')
        FROM pg_database WHERE datname = current_database()
    """).fetchone()
    if row != ("kiki_integration", "kiki_integration", None, MARKER):
        raise IsolationError(
            "Identidad PostgreSQL no sintética: inicio cancelado antes del DDL."
        )
    role = connection.execute(
        "SELECT rolsuper, rolcreatedb, rolcreaterole, rolreplication "
        "FROM pg_roles WHERE rolname = current_user"
    ).fetchone()
    if role != (False, False, False, False):
        raise IsolationError(
            "El usuario de aplicación debe carecer de privilegios administrativos."
        )


def preflight() -> None:
    validate_environment(os.environ)
    install_network_guard()
    import psycopg

    # Explicit arguments; never consume libpq environment/service files or a TCP fallback.
    with psycopg.connect(
        host="/var/run/postgresql",
        port=5432,
        dbname="kiki_integration",
        user="kiki_integration",
        password="kiki-synthetic-only",
        connect_timeout=3,
        passfile="/dev/null",
        sslmode="disable",
    ) as connection:
        validate_database_identity(connection)
