"""Supervise the existing API and isolated document reader in one container.

Children run under distinct UIDs. Render's container may not grant CAP_KILL,
so the root supervisor must not rely on signalling those UIDs during shutdown.
Each child arms a Linux parent-death SIGTERM *after* changing credentials.
No database changes are made unless the pre-existing opt-in gate is enabled.
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


def shutdown_children(children):
    """Best-effort graceful stop; never wait on an unsignalable foreign UID.

    A child that rejects SIGTERM here exits when this supervisor itself exits,
    via PR_SET_PDEATHSIG set by its launcher. Never cross the reader boundary,
    escalate container privileges, or mask the situation as a clean child stop.
    """
    inaccessible = set()
    for child in children:
        if child.poll() is not None:
            continue
        try:
            child.terminate()
        except PermissionError:
            inaccessible.add(child)
            print(
                "El hijo no admite SIGTERM entre usuarios; "
                "se activará SIGTERM al finalizar el supervisor.",
                flush=True,
            )
    for child in children:
        if child in inaccessible or child.poll() is not None:
            continue
        try:
            child.wait(timeout=15)
        except subprocess.TimeoutExpired:
            try:
                child.kill()
                child.wait(timeout=3)
            except PermissionError:
                print(
                    "Sin permiso de SIGKILL; se delega salida al "
                    "resguardo de muerte del supervisor.",
                    flush=True,
                )
            except subprocess.TimeoutExpired:
                print("Hijo sin terminar; se cierra el supervisor.", flush=True)


def main():
    # Existing explicit operator-controlled database bootstrap gate.
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

    parent_pid = str(os.getpid())
    boundary = os.getuid() == 0
    if boundary:
        try:
            os.setgroups([])
            os.setgid(10000)
        except OSError:
            boundary = False

    reader = None
    if not boundary:
        print(
            "Lector bloqueado: frontera de usuarios/chroot no disponible; "
            "se conserva la API existente.",
            flush=True,
        )

    if boundary and os.environ.get("KIKI_DOCUMENT_PARSER_ENABLED", "true").lower() == "true":
        # The reader sees ONLY these non-secret variables.
        reader_env = {
            "PATH": "/usr/local/bin:/usr/bin",
            "LANG": "C.UTF-8",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONUNBUFFERED": "1",
            "KIKI_SUPERVISOR_PID": parent_pid,
        }
        reader = subprocess.Popen(
            [sys.executable, "/app/reader_launcher.py"],
            env=reader_env,
            close_fds=True,
        )
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline and reader.poll() is None:
            if health("/opt/kiki-reader/run/parser.sock"):
                break
            time.sleep(0.1)
        else:
            if reader.poll() is None:
                try:
                    reader.terminate()
                    reader.wait(timeout=3)
                except (PermissionError, subprocess.TimeoutExpired):
                    # Cannot guarantee a failed reader is gone. Fail closed:
                    # supervisor exit triggers the reader's parent-death SIGTERM.
                    raise SystemExit(
                        "No se pudo detener un lector no disponible; "
                        "se aborta el inicio antes de exponer documentos."
                    ) from None
            print(
                "Lector documental no disponible: carga bloqueada; "
                "API anterior conservada.",
                flush=True,
            )

    if "--reader-only" in sys.argv:
        if reader is None or reader.poll() is not None:
            raise SystemExit(1)
        api = None
    else:
        port = int(os.environ.get("PORT", "8000"))
        if not 1024 <= port <= 65535:
            raise SystemExit("Puerto de API fuera de rango.")
        api_env = os.environ.copy()
        api_env["KIKI_SUPERVISOR_PID"] = parent_pid
        command = [sys.executable, "/app/api_launcher.py", str(port)]
        try:
            api = subprocess.Popen(
                command,
                **({"user": 10000, "group": 10000, "extra_groups": []} if boundary else {}),
                env=api_env,
                close_fds=True,
            )
        except PermissionError:
            # Historical unprivileged fallback; never run documents in the API.
            print(
                "No se pudo cambiar el usuario API; "
                "se conserva el usuario de ejecución existente.",
                flush=True,
            )
            api = subprocess.Popen(command, env=api_env, close_fds=True)

    children = [child for child in (api, reader) if child is not None]

    def stop(signum, frame):
        # Exiting ensures Linux notifies both differently owned children.
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        target = api or reader
        return target.wait()
    finally:
        shutdown_children(children)


if __name__ == "__main__":
    raise SystemExit(main())
