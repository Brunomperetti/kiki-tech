"""Regression for Render cross-UID shutdown without CAP_KILL.

All tests are offline. No Docker, database, provider, Render, or privileges.
"""
import importlib
import os
import signal
import subprocess
import sys
import time
import pytest

import start


class FakeProcess:
    def __init__(self, *, permission_denied=False, timeout=False, kill_denied=False):
        self.permission_denied = permission_denied
        self.timeout = timeout
        self.kill_denied = kill_denied
        self.terminate_calls = 0
        self.wait_calls = 0
        self.kill_calls = 0

    def poll(self):
        return None

    def terminate(self):
        self.terminate_calls += 1
        if self.permission_denied:
            raise PermissionError(1, "Operation not permitted")

    def wait(self, timeout=None):
        self.wait_calls += 1
        if self.timeout:
            raise subprocess.TimeoutExpired(["dummy"], timeout)
        return 0

    def kill(self):
        self.kill_calls += 1
        if self.kill_denied:
            raise PermissionError(1, "Operation not permitted")


def test_different_uid_does_not_raise_or_wait_for_unstoppable_child():
    foreign = FakeProcess(permission_denied=True)
    local = FakeProcess()
    start.shutdown_children([foreign, local])
    assert foreign.terminate_calls == 1
    assert foreign.wait_calls == 0  # parent exit triggers PDEATHSIG
    assert foreign.kill_calls == 0
    assert local.terminate_calls == 1
    assert local.wait_calls == 1


def test_timeout_with_denied_kill_does_not_crash_supervisor():
    process = FakeProcess(timeout=True, kill_denied=True)
    start.shutdown_children([process])
    assert process.terminate_calls == 1
    assert process.wait_calls == 1
    assert process.kill_calls == 1


@pytest.mark.parametrize("launcher_name", ["api_launcher", "reader_launcher"])
def test_each_child_arms_linux_sigterm_after_matching_parent(
    monkeypatch, launcher_name
):
    launcher = importlib.import_module(launcher_name)
    calls = []

    class Libc:
        def prctl(self, *args):
            calls.append(args)
            return 0

    monkeypatch.setattr(launcher.ctypes, "CDLL", lambda *_args, **_kwargs: Libc())
    monkeypatch.setattr(os, "getppid", lambda: 32145)
    monkeypatch.setenv("KIKI_SUPERVISOR_PID", "32145")
    launcher.arm_parent_death_signal()

    assert calls == [(1, signal.SIGTERM, 0, 0, 0)]
    assert "KIKI_SUPERVISOR_PID" not in os.environ


@pytest.mark.parametrize("launcher_name", ["api_launcher", "reader_launcher"])
def test_child_fails_closed_on_missing_or_lost_parent(monkeypatch, launcher_name):
    launcher = importlib.import_module(launcher_name)

    class Libc:
        def prctl(self, *args):
            return 0

    monkeypatch.setattr(launcher.ctypes, "CDLL", lambda *_args, **_kwargs: Libc())
    monkeypatch.delenv("KIKI_SUPERVISOR_PID", raising=False)
    with pytest.raises(SystemExit, match="no identificado"):
        launcher.arm_parent_death_signal()
    monkeypatch.setenv("KIKI_SUPERVISOR_PID", "9001")
    monkeypatch.setattr(os, "getppid", lambda: 9002)
    with pytest.raises(SystemExit, match="terminó"):
        launcher.arm_parent_death_signal()


@pytest.mark.parametrize("launcher_name", ["api_launcher", "reader_launcher"])
def test_child_fails_closed_if_kernel_denies_parent_watch(
    monkeypatch, launcher_name
):
    launcher = importlib.import_module(launcher_name)

    class Libc:
        def prctl(self, *args):
            return -1

    monkeypatch.setattr(launcher.ctypes, "CDLL", lambda *_args, **_kwargs: Libc())
    monkeypatch.setattr(launcher.ctypes, "get_errno", lambda: 1)
    monkeypatch.setenv("KIKI_SUPERVISOR_PID", "9001")
    with pytest.raises(OSError, match="protección"):
        launcher.arm_parent_death_signal()


def test_linux_kernel_sends_sigterm_when_supervisor_exits(tmp_path):
    """Real, network-free Linux process tree, not just an emulated prctl call."""
    if sys.platform != "linux":
        pytest.skip("PR_SET_PDEATHSIG is Linux-specific")

    armed = tmp_path / "armed"
    signalled = tmp_path / "signalled"
    child_code = """
import signal,sys,time
from pathlib import Path
from api_launcher import arm_parent_death_signal

def stop(signum, frame):
    Path(sys.argv[2]).write_text('SIGTERM')
    raise SystemExit(0)

signal.signal(signal.SIGTERM, stop)
arm_parent_death_signal()
Path(sys.argv[1]).write_text('ready')
while True:
    time.sleep(0.1)
"""
    supervisor_code = """
import os,subprocess,sys,time
from pathlib import Path

env = os.environ.copy()
env['KIKI_SUPERVISOR_PID'] = str(os.getpid())
subprocess.Popen([sys.executable, '-c', sys.argv[3], sys.argv[1], sys.argv[2]],
                 env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                 stderr=subprocess.DEVNULL, close_fds=True)
for _ in range(150):
    if Path(sys.argv[1]).exists():
        break
    time.sleep(0.02)
else:
    raise SystemExit('Child never armed PDEATHSIG')
"""
    subprocess.run(
        [sys.executable, "-c", supervisor_code, str(armed), str(signalled), child_code],
        check=True, timeout=8,
    )
    for _ in range(150):
        if signalled.exists():
            break
        time.sleep(0.02)
    assert signalled.read_text() == "SIGTERM"


def test_docker_build_context_contains_supervisor_and_child_launchers():
    """Regression: the real Render Docker build context uses a deny-all rule."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    rules = (root / ".dockerignore").read_text().splitlines()
    assert rules[0] == "**"  # Fail closed: every runtime file needs explicit allowlist.
    for name in ("start.py", "api_launcher.py", "reader_launcher.py"):
        assert f"!{name}" in rules
        assert (root / name).is_file()
    dockerfile = (root / "Dockerfile").read_text()
    assert "COPY --chmod=755 . ." in dockerfile
