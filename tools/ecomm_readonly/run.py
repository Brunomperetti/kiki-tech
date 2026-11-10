"""Host launcher for one unrelated, offline container. Never starts KIKI or SQL."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
DOCKER = ["docker", "--host=unix:///var/run/docker.sock"]
IMAGE = "kiki-ecomm-reader-offline:local"
BASE = "kiki-tech-integration:local"


def run(command):
    if command not in ("build", "test", "plan", "demo"):
        print("UNSUPPORTED_OFFLINE_COMMAND")
        return 2
    # Empty disposable Docker config: never read inherited registry credentials.
    with tempfile.TemporaryDirectory(prefix="kiki-reader-docker-") as config_dir:
        env = {k: v for k, v in os.environ.items() if k in {"PATH", "HOME"}}
        env["DOCKER_CONFIG"] = config_dir
        return _run(command, env)


def _run(command, env):
    if command == "build":
        # Reuse the already installed base; this task must not fetch new services.
        found = subprocess.run(
            DOCKER + ["image", "inspect", BASE], env=env, capture_output=True
        )
        if found.returncode:
            print("LOCAL_BASE_IMAGE_REQUIRED; nothing downloaded")
            return 2
        args = DOCKER + [
            "build",
            "--pull=false",
            "--network=none",
            "-t",
            IMAGE,
            str(ROOT),
        ]
    else:
        args = DOCKER + [
            "run",
            "--rm",
            "--network=none",
            "--read-only",
            "--user=1000:1000",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges:true",
            "--memory=192m",
            "--cpus=1",
            "--pids-limit=16",
            "--pull=never",
        ]
        for key in (
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "ALL_PROXY",
            "NO_PROXY",
            "http_proxy",
            "https_proxy",
            "all_proxy",
            "no_proxy",
        ):
            args += ["--env", key + "="]
        # No mounts, ports, credential forwarding, .env files or production endpoints.
        args += [IMAGE, command]
    try:
        return subprocess.run(
            args, env=env, timeout=120 if command == "build" else 60
        ).returncode
    except (OSError, subprocess.TimeoutExpired):
        print("OFFLINE_LAUNCH_FAILED; no fallback")
        return 2


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1]) if len(sys.argv) == 2 else 2)
