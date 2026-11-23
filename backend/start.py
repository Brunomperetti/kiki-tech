"""Supervise KIKI API and isolated reader without CAP_KILL in Render.

The supervisor is PID 1, so exiting before its children would force-kill
them. A separate inherited shutdown pipe per child sends EOF when the
supervisor closes its writer. Each differently-owned child then signals
ITSELF, allowing Uvicorn lifespan and the isolated reader to exit cleanly.
PR_SET_PDEATHSIG remains a fallback for unexpected supervisor death.
"""
import json
import os
import signal
import socket
import struct
import subprocess
import sys
import time


def health(path):
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(1)
            sock.connect(path)
            data = b'{"operation":"health"}'
            sock.sendall(struct.pack("!I", len(data)) + data)
            with sock.makefile("rb") as stream:
                size = struct.unpack("!I", stream.read(4))[0]
                if not 0 < size < 4096:
                    return False
                result = json.loads(stream.read(size))
            return (
                result.get("ok")
                and result["result"].get("kernel_guard") is True
                and result["result"].get("native_network_denied") is True
                and result["result"].get("secret_environment_present") is False
            )
    except (OSError, ValueError, KeyError, struct.error):
        return False


def close_shutdown_writer(writer):
    try:
        os.close(writer)
    except OSError:
        pass


def shutdown_children(children, writers, *, timeout=40):
    """Ask children to exit *before* PID 1 terminates.

    This is a cooperative protocol over anonymous pipes, not inter-UID
    signals. Never elevate privileges or send SIGKILL to the reader.
    """
    for writer in writers:
        close_shutdown_writer(writer)
    for child in children:
        if child.poll() is not None:
            continue
        try:
            child.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            print(
                "Un hijo no finalizó a tiempo; no se eleva CAP_KILL. "
                "Revisar los registros antes del próximo despliegue.",
                flush=True,
            )


def launch_child(command, env, writers, *, uid=None):
    """Create one readable pipe for the child, retaining only its writer."""
    read_fd, write_fd = os.pipe()
    child_env = env.copy()
    child_env["KIKI_SHUTDOWN_READ_FD"] = str(read_fd)
    credentials = (
        {"user": uid, "group": 10000, "extra_groups": []}
        if uid is not None else {}
    )
    try:
        try:
            child = subprocess.Popen(
                command, env=child_env, close_fds=True,
                pass_fds=(read_fd,), **credentials,
            )
        except PermissionError:
            if uid is None:
                raise
            print(
                "No se pudo cambiar el usuario API; "
                "se conserva el usuario de ejecución existente.",
                flush=True,
            )
            child = subprocess.Popen(
                command, env=child_env, close_fds=True,
                pass_fds=(read_fd,),
            )
    except Exception:
        os.close(read_fd)
        os.close(write_fd)
        raise
    os.close(read_fd)
    writers.append(write_fd)
    return child, write_fd


def main():
    # Explicitly approved one-shot intake migration for 23/11/2026.
    # No flag, no DDL. The token is set only in the KIKI API Render service.
    if os.environ.get("KIKI_SOURCE_INTAKE_SCHEMA_RELEASE_20261123") == "APPLY_ONCE_23NOV_KIKI":
        try:
            from app.database.session import engine
            from app.services.documental.intake_release_20261123 import migrate_once
            outcome = migrate_once(engine, expected_database="kiki_tech_db")
            print(
                "KIKI_INTAKE_MIGRATION_OK: created="
                + str(outcome["created"]).lower() + "; table_verified=1",
                flush=True,
            )
        except Exception:
            print(
                "KIKI_INTAKE_MIGRATION_FAILED: transacción revertida; API preservada. "
                "Revisar error de esquema antes de habilitar la cola.",
                flush=True,
            )
    # Existing explicit migration gate; never perform schema DDL implicitly.
    if os.environ.get("KIKI_DOCUMENT_BOOTSTRAP_ON_STARTUP", "false").lower() == "true":
        try:
            from app.database.session import engine
            from app.services.documental.one_time_bootstrap import apply_additive_schema

            result = apply_additive_schema(engine, expected_database="kiki_tech_db")
            print(
                "KIKI document schema verified; tables="
                + str(result["tables"]) + "; no Ecomm/channel writes.",
                flush=True,
            )
        except Exception:
            print(
                "KIKI document schema bootstrap rejected: no partial DDL "
                "committed; existing API preserved. Check protected logs.",
                flush=True,
            )

    supervisor_pid = str(os.getpid())
    boundary = os.getuid() == 0
    if boundary:
        try:
            os.setgroups([])
            os.setgid(10000)
        except OSError:
            boundary = False

    writers = []
    children = []
    reader = None
    api = None

    if not boundary:
        print(
            "Lector bloqueado: frontera de usuarios/chroot no disponible; "
            "se conserva la API existente.",
            flush=True,
        )

    def stop(signum, frame):
        # finally sends EOF to children and waits while PID 1 remains alive.
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    try:
        if boundary and os.environ.get("KIKI_DOCUMENT_PARSER_ENABLED", "true").lower() == "true":
            # No application secrets, database credentials or provider settings.
            reader_env = {
                "PATH": "/usr/local/bin:/usr/bin",
                "LANG": "C.UTF-8",
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONUNBUFFERED": "1",
                "KIKI_SUPERVISOR_PID": supervisor_pid,
            }
            reader, reader_writer = launch_child(
                [sys.executable, "/app/reader_launcher.py"],
                reader_env, writers,
            )
            children.append(reader)
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline and reader.poll() is None:
                if health("/opt/kiki-reader/run/parser.sock"):
                    break
                time.sleep(0.1)
            else:
                if reader.poll() is None:
                    close_shutdown_writer(reader_writer)
                    writers.remove(reader_writer)
                    try:
                        reader.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        raise SystemExit(
                            "Lector no pudo detenerse: arranque bloqueado."
                        ) from None
                print(
                    "Lector documental no disponible: carga bloqueada; "
                    "API anterior conservada.",
                    flush=True,
                )

        if "--reader-only" in sys.argv:
            if reader is None or reader.poll() is not None:
                raise SystemExit(1)
        else:
            port = int(os.environ.get("PORT", "8000"))
            if not 1024 <= port <= 65535:
                raise SystemExit("Puerto de API fuera de rango.")
            env = os.environ.copy()
            env["KIKI_SUPERVISOR_PID"] = supervisor_pid
            api, _ = launch_child(
                [sys.executable, "/app/api_launcher.py", str(port)],
                env, writers,
                uid=10000 if boundary else None,
            )
            children.append(api)

        target = api or reader
        return target.wait()
    finally:
        # Never leave PID 1 before all cooperative children were asked to exit.
        shutdown_children(children, writers)


if __name__ == "__main__":
    raise SystemExit(main())
