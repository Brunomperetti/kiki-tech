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
    if len(ids) != 2:
        raise RuntimeError("Se requieren exactamente dos contenedores locales activos.")
    result = subprocess.run(
        ["docker", "--host=unix:///var/run/docker.sock", "inspect", *ids],
        check=True,
        env=clean_environment(),
        capture_output=True,
        text=True,
    )
    for container in json.loads(result.stdout):
        host = container["HostConfig"]
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
    for path in (directory, api):
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
    command = parser.parse_args().command
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
        try:
            compose("up", "--detach", "--no-build", "--wait", "--wait-timeout", "90")
            verify_containers()
            if command in {"test", "legacy-test"}:
                module = "verify" if command == "test" else "legacy_tests"
                compose(
                    "run",
                    "--rm",
                    "--no-deps",
                    "backend",
                    "python",
                    "-m",
                    "integration_sandbox." + module,
                )
                if command == "test":
                    compose(
                        "run",
                        "--rm",
                        "--no-deps",
                        "backend",
                        "python",
                        "-m",
                        "integration_sandbox.editor_checks",
                    )
                    compose(
                        "run",
                        "--rm",
                        "--no-deps",
                        "backend",
                        "python",
                        "-m",
                        "integration_sandbox.research_checks",
                    )
                    subprocess.run(
                        [sys.executable, str(ROOT / "integration/test_gateway.py")],
                        check=True,
                        env=clean_environment(),
                    )
            elif command == "browser-test":
                # Runs its own gateway and Playwright against the actual isolated backend.
                subprocess.run(
                    [sys.executable, str(ROOT / "integration/browser_tests.py")],
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
