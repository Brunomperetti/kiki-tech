"""Run from Linux/WSL2. Explicit local Docker socket, clean env, no .env/overrides."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = [
    "docker",
    "--host=unix:///var/run/docker.sock",
    "compose",
    "--env-file",
    "/dev/null",
    "--project-directory",
    str(ROOT / "integration"),
    "--file",
    str(ROOT / "integration/compose.yaml"),
    "--project-name",
    "kiki-tech-integration",
]


def clean_environment(*, build=False):
    # Never pass application variables, .env, Docker endpoint/TLS/context selectors.
    allowed = {"PATH", "HOME", "DOCKER_CONFIG", "XDG_RUNTIME_DIR"}
    if build:
        allowed |= {
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "NO_PROXY",
            "ALL_PROXY",
            "http_proxy",
            "https_proxy",
            "no_proxy",
            "all_proxy",
            "SSL_CERT_FILE",
            "SSL_CERT_DIR",
            "CODEX_PROXY_CERT",
        }
    result = {key: value for key, value in os.environ.items() if key in allowed}
    if build:
        directory = ROOT / ".integration-runtime/buildx"
        directory.mkdir(parents=True, exist_ok=True)
        result["BUILDX_CONFIG"] = str(directory)
    return result


def compose(*arguments, capture=False, build=False):
    return subprocess.run(
        COMPOSE + list(arguments),
        check=True,
        cwd=ROOT,
        env=clean_environment(build=build),
        text=True,
        stdout=subprocess.PIPE if capture else None,
    )


def verify_containers():
    ids = compose("ps", "-q", capture=True).stdout.split()
    if len(ids) != 4:
        raise RuntimeError(
            "Se requieren PostgreSQL, backend, lector y recolector simulado locales."
        )
    result = subprocess.run(
        ["docker", "--host=unix:///var/run/docker.sock", "inspect", *ids],
        check=True,
        env=clean_environment(),
        capture_output=True,
        text=True,
    )
    for container in json.loads(result.stdout):
        host = container["HostConfig"]
        if container["Config"]["Labels"].get(
            "com.docker.compose.service"
        ) == "collector" and (
            host["Memory"] != 128 * 1024 * 1024
            or host["PidsLimit"] != 16
            or host["NanoCpus"] != 1_000_000_000
        ):
            raise RuntimeError("Recolector sin límites esperados.")
        if container["Config"]["Labels"].get(
            "com.docker.compose.service"
        ) == "parser" and (
            host["Memory"] != 384 * 1024 * 1024
            or host["PidsLimit"] != 16
            or host["NanoCpus"] != 1_000_000_000
        ):
            raise RuntimeError("Lector sin límites de memoria, CPU o procesos.")
        if (
            host["NetworkMode"] != "none"
            or host["Privileged"]
            or host.get("PortBindings")
        ):
            raise RuntimeError(
                "Contenedor sin aislamiento de red; ejecución cancelada."
            )
        if (
            not host["ReadonlyRootfs"]
            or "no-new-privileges:true" not in host["SecurityOpt"]
        ):
            raise RuntimeError("Contenedor sin endurecimiento esperado.")
    print(
        "Aislamiento Docker verificado: network=none, sin puertos ni privilegios, raíz de sólo lectura."
    )


def runtime_directory():
    directory = ROOT / ".integration-runtime"
    api = directory / "api"
    for path in (directory, api, directory / "documents", directory / "discovery"):
        if path.is_symlink():
            raise RuntimeError("Directorio de ejecución simbólico rechazado.")
        path.mkdir(mode=0o700, exist_ok=True)
        if path.stat().st_uid != os.getuid():
            raise RuntimeError("El directorio local debe pertenecer al usuario actual.")
        path.chmod(0o700)
    if os.getuid() != 1000:
        raise RuntimeError(
            "Este entorno requiere UID 1000 (Linux/WSL2); no cambiar permisos para eludirlo."
        )
    return api


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=[
            "build",
            "up",
            "test",
            "legacy-test",
            "browser-test",
            "down",
            "status",
        ],
    )
    parser.add_argument("--presentation", action="store_true", help="Presentación: canales sintéticos y documentos pendientes de revisión.")
    parser.add_argument("--autonomous", action="store_true", help="Escenario 2R: 5000 variantes sintéticas y ejecución backend.")
    parser.add_argument("--batches", action="store_true", help="Escenario documental sintético para lotes (up/browser-test).")
    parser.add_argument("--channels", action="store_true", help="Cargar escenario de canales sintético (sólo up/browser-test).")
    arguments = parser.parse_args()
    command = arguments.command
    if arguments.presentation and (command not in {"up", "browser-test"} or arguments.autonomous or arguments.batches or arguments.channels):
        parser.error("--presentation requiere up/browser-test y no se combina con otros escenarios.")
    if arguments.autonomous and (command not in {"up", "browser-test"} or arguments.batches or arguments.channels):
        parser.error("--autonomous requiere up/browser-test y un escenario independiente.")
    if arguments.batches and (command not in {"up", "browser-test"} or arguments.channels):
        parser.error("--batches requiere up/browser-test y no se combina con --channels.")
    if arguments.channels and command not in {"up", "browser-test"}:
        parser.error("--channels sólo es válido para up o browser-test en el entorno descartable.")
    if command == "build":
        subprocess.run(
            ["npm", "run", "build:integration"],
            cwd=ROOT / "frontend",
            env=clean_environment(),
            check=True,
        )
        compose("build", "backend", build=True)
        # Runtime pull_policy stays "never"; only this explicit setup step may download.
        compose("pull", "--policy", "missing", "postgres", build=True)
    elif command in {"up", "test", "legacy-test", "browser-test"}:
        if not (ROOT / "frontend/.integration-dist/integration.html").is_file():
            raise RuntimeError(
                "Falta el frontend de integración. Ejecutá primero integration/run.py build."
            )
        directory = runtime_directory()
        (directory / "editorial-mode").write_text("backend" if command in {"up", "browser-test"} else "manual")
        (directory / "editorial-workers").write_text("1")
        try:
            compose("up", "--detach", "--no-build", "--wait", "--wait-timeout", "90")
            verify_containers()
            if arguments.presentation:
                compose("exec", "-T", "backend", "python", "-m", "integration_sandbox.presentation_fixtures")
            if arguments.autonomous:
                compose("exec", "-T", "backend", "python", "-m", "integration_sandbox.editorial_fixtures", "--scale-5000")
            if arguments.batches:
                compose("exec", "-T", "backend", "python", "-m", "integration_sandbox.editorial_fixtures")
            if arguments.channels:
                compose("exec", "-T", "backend", "python", "-m", "integration_sandbox.channel_fixtures")
            if command in {"test", "legacy-test"}:
                # Fresh guarded Python processes inside the already verified offline backend.
                # Avoid starting another identical container for each test module.
                module = "verify" if command == "test" else "legacy_tests"
                compose(
                    "exec",
                    "-T",
                    "backend",
                    "python",
                    "-m",
                    "integration_sandbox." + module,
                )
                if command == "test":
                    compose(
                        "exec",
                        "-T",
                        "backend",
                        "python",
                        "-m",
                        "integration_sandbox.editor_checks",
                    )
                    compose(
                        "exec",
                        "-T",
                        "backend",
                        "python",
                        "-m",
                        "integration_sandbox.research_checks",
                    )
                    compose(
                        "exec",
                        "-T",
                        "backend",
                        "python",
                        "-m",
                        "integration_sandbox.proposal_checks",
                    )
                    compose(
                        "exec",
                        "-T",
                        "backend",
                        "python",
                        "-m",
                        "integration_sandbox.document_checks",
                    )
                    compose(
                        "exec",
                        "-T",
                        "backend",
                        "python",
                        "-m",
                        "integration_sandbox.assisted_checks",
                    )
                    for checks in (
                        "dashboard_checks",
                        "channel_checks",
                        "catalog_operations_checks",
                        "editorial_checks",
                        "autonomous_checks",
                        "documental_workspace_checks",
                        "connector_checks",
                        "pilot_checks",
                        "mama_checks",
                        "hileret_checks",
                        "hileret_authentic_checks",
                    ):
                        compose(
                            "exec",
                            "-T",
                            "backend",
                            "python",
                            "-m",
                            "integration_sandbox." + checks,
                        )
                    subprocess.run([sys.executable, str(ROOT / "integration/test_batch_restart.py")], check=True, env=clean_environment())
                    subprocess.run([sys.executable, str(ROOT / "integration/test_autonomous_restart.py")], check=True, env=clean_environment())
                    subprocess.run(
                        [sys.executable, str(ROOT / "integration/test_gateway.py")],
                        check=True,
                        env=clean_environment(),
                    )
            elif command == "browser-test":
                # Runs its own gateway and Playwright against the actual isolated backend.
                subprocess.run(
                    [sys.executable, str(ROOT / "integration/browser_tests.py"), *(["--presentation"] if arguments.presentation else ["--channels"] if arguments.channels else ["--batches"] if arguments.batches else ["--autonomous"] if arguments.autonomous else [])],
                    check=True,
                    env=clean_environment(),
                )
            else:
                for _ in range(60):
                    if (directory / "api.sock").exists() and (
                        directory / "tls-cert.pem"
                    ).exists():
                        break
                    time.sleep(0.5)
                else:
                    raise RuntimeError(
                        "El backend no creó su socket/certificado local."
                    )
                subprocess.run(
                    [
                        sys.executable,
                        str(ROOT / "integration/gateway.py"),
                        str(directory),
                    ],
                    check=True,
                    env=clean_environment(),
                )
        except (subprocess.CalledProcessError, RuntimeError):
            # Only synthetic containers; retain the startup reason before their removal.
            compose("logs", "--tail", "80", "postgres", "backend")
            raise
        finally:
            # Only this fixed project. tmpfs data and sessions disappear when stopped.
            compose("down", "--volumes")
    elif command == "down":
        compose("down", "--volumes")
    else:
        compose("ps")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
