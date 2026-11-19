"""Offline smoke of the actual KIKI production Docker image without CAP_KILL.

Executed only by GitHub Actions with a disposable SQLite database, no secrets,
no external network, no Render, no Ecomm-App, no channel writes or AI.
"""
import json
import os
import subprocess
import sys
import time

IMAGE = "kiki-supervisor-shutdown:ci"
NAME = "kiki-supervisor-shutdown-smoke"


def docker(*args, check=True, timeout=30):
    return subprocess.run(
        ["docker", *args], capture_output=True, text=True, timeout=timeout,
        check=check,
    )


def check_processes():
    # Run inside the isolated container, not from host/network.
    client = r"""
import http.client, json, socket, struct
c = http.client.HTTPConnection('127.0.0.1', 8000, timeout=2)
c.request('GET', '/health')
r = c.getresponse()
assert r.status == 200, r.status
body = json.loads(r.read())
assert body.get('database') == 'ok', body
packet = b'{"operation":"health"}'
with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
    s.settimeout(2)
    s.connect('/opt/kiki-reader/run/parser.sock')
    s.sendall(struct.pack('!I', len(packet)) + packet)
    with s.makefile('rb') as f:
        count = struct.unpack('!I', f.read(4))[0]
        assert 0 < count <= 4096
        result = json.loads(f.read(count))
assert result['ok']
assert result['result']['kernel_guard'] is True
assert result['result']['native_network_denied'] is True
assert result['result']['secret_environment_present'] is False
print("API 200 + isolated reader: OK")
"""
    return docker(
        "exec", "--user", "10000:10000", NAME, "python", "-c", client,
        check=False,
    )


def main():
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise SystemExit("Only disposable CI may run the production-image smoke.")
    # Verify this test never silently obtains CAP_KILL or a provider network.
    args = [
        "run", "--detach", "--name", NAME, "--network", "none",
        "--read-only", "--cap-drop", "ALL",
        "--cap-add", "SYS_CHROOT", "--cap-add", "SETUID",
        "--cap-add", "SETGID", "--memory", "512m", "--pids-limit", "32",
        "--tmpfs", "/tmp:rw,size=16m",
        "--tmpfs", "/opt/kiki-reader/run:rw,uid=10001,gid=10000,mode=0750,size=1m",
        "-e", "DATABASE_URL=sqlite:////tmp/ci-smoke.db",
        "-e", "KIKI_AUTO_CREATE_SCHEMA=true",
        "-e", "KIKI_V2_ENABLED=false",
        "-e", "KIKI_DOCUMENT_BOOTSTRAP_ON_STARTUP=false",
        IMAGE,
    ]
    docker(*args)
    try:
        result = None
        for _ in range(80):
            result = check_processes()
            if result.returncode == 0:
                break
            time.sleep(0.25)
        else:
            raise AssertionError(
                "API o lector no inicia en Docker sin CAP_KILL: "
                + (result.stderr or "").splitlines()[-1:][0:1].__str__()
            )
        # A fresh shutdown must not emit the production PermissionError.
        docker("stop", "--time", "20", NAME, timeout=30)
        status = json.loads(docker("inspect", NAME).stdout)[0]
        assert status["State"]["Running"] is False
        assert status["State"]["ExitCode"] == 0
        logs = docker("logs", NAME).stdout + docker("logs", NAME).stderr
        assert "PermissionError" not in logs
        assert "Operation not permitted" not in logs
        assert "Application shutdown complete" in logs, "Uvicorn lifecycle did not finish"
        assert "KIKI_READER_SHUTDOWN_COMPLETE" in logs, "Reader was terminated abruptly"
        print("PASS: actual production image starts and stops without CAP_KILL")
    except Exception:
        details = docker("logs", "--tail", "35", NAME, check=False)
        # Logs can be produced by synthetic initialization only, never secrets.
        print((details.stdout + details.stderr)[-4000:], file=sys.stderr)
        raise
    finally:
        docker("rm", "--force", NAME, check=False)


if __name__ == "__main__":
    main()
