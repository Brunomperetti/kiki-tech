"""Regressions for KIKI supervisor shutdown without CAP_KILL or external IO."""
import importlib
import os
import signal
import subprocess
import sys
import time
from threading import Event

import pytest

import start


class FakeProcess:
    def __init__(self, *, timeout=False):
        self.timeout = timeout
        self.wait_calls = 0

    def poll(self):
        return None

    def wait(self, timeout=None):
        self.wait_calls += 1
        if self.timeout:
            raise subprocess.TimeoutExpired(["dummy"], timeout)
        return 0

    def terminate(self):
        raise AssertionError("Supervisor must not signal another UID")

    def kill(self):
        raise AssertionError("Supervisor must not require CAP_KILL")


def test_supervisor_closes_pipes_and_waits_while_alive():
    readers_and_writers = [os.pipe(), os.pipe()]
    writers = [pair[1] for pair in readers_and_writers]
    children = [FakeProcess(), FakeProcess()]
    try:
        start.shutdown_children(children, writers, timeout=1)
        for child in children:
            assert child.wait_calls == 1
        for reader, _writer in readers_and_writers:
            assert os.read(reader, 1) == b""  # EOF was delivered before PID 1 exited
    finally:
        for reader, _writer in readers_and_writers:
            os.close(reader)


def test_supervisor_reports_unresponsive_children_without_cross_uid_kill():
    reader, writer = os.pipe()
    child = FakeProcess(timeout=True)
    try:
        start.shutdown_children([child], [writer], timeout=0.001)
        assert child.wait_calls == 1
        assert os.read(reader, 1) == b""
    finally:
        os.close(reader)


@pytest.mark.parametrize("launcher_name", ["api_launcher", "reader_launcher"])
def test_each_child_arms_linux_sigterm_after_matching_parent(monkeypatch, launcher_name):
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
def test_child_fails_closed_if_kernel_denies_parent_watch(monkeypatch, launcher_name):
    launcher = importlib.import_module(launcher_name)

    class Libc:
        def prctl(self, *args):
            return -1

    monkeypatch.setattr(launcher.ctypes, "CDLL", lambda *_args, **_kwargs: Libc())
    monkeypatch.setattr(launcher.ctypes, "get_errno", lambda: 1)
    monkeypatch.setenv("KIKI_SUPERVISOR_PID", "9001")
    with pytest.raises(OSError, match="protección"):
        launcher.arm_parent_death_signal()


@pytest.mark.parametrize("launcher_name", ["api_launcher", "reader_launcher"])
def test_child_signals_itself_when_shutdown_pipe_closes(monkeypatch, launcher_name):
    launcher = importlib.import_module(launcher_name)
    read_fd, write_fd = os.pipe()
    finished = Event()
    seen = []

    def fake_kill(pid, sig):
        seen.append((pid, sig))
        finished.set()

    monkeypatch.setattr(os, "kill", fake_kill)
    monkeypatch.setenv("KIKI_SHUTDOWN_READ_FD", str(read_fd))
    try:
        launcher.start_shutdown_watch()
        assert "KIKI_SHUTDOWN_READ_FD" not in os.environ
        os.close(write_fd)
        assert finished.wait(timeout=2)
        assert seen == [(os.getpid(), signal.SIGTERM)]
    finally:
        if not finished.is_set():
            os.close(write_fd)


def test_linux_kernel_sends_sigterm_when_supervisor_exits(tmp_path):
    """Real process-tree fallback without CAP_KILL or any external network."""
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
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    rules = (root / ".dockerignore").read_text().splitlines()
    assert rules[0] == "**"
    for name in ("start.py", "api_launcher.py", "reader_launcher.py"):
        assert f"!{name}" in rules
        assert (root / name).is_file()
    dockerfile = (root / "Dockerfile").read_text()
    assert "COPY --chmod=755 . ." in dockerfile
