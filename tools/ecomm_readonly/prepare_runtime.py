"""Build-time only: copy cached CPython/OS libraries; never import the donor app.

The final FROM scratch stage gets no application, installed packages, image env,
credentials, shell, Docker client or database executables. No network/install.
"""

from pathlib import Path
import re
import shutil
import subprocess
import sys

DEST = Path("/offline-python")
PYTHON = Path("/usr/local/bin/python3.12")
STDLIB = Path("/usr/local/lib/python3.12")

if sys.version_info[:2] != (3, 12) or not sys.flags.isolated or not sys.flags.no_site:
    raise SystemExit("ISOLATED_CACHED_PYTHON_312_REQUIRED")


def copy_file(source):
    target = DEST / source.relative_to("/")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target, follow_symlinks=True)


shutil.copytree(
    STDLIB,
    DEST / STDLIB.relative_to("/"),
    ignore=shutil.ignore_patterns(
        "site-packages",
        "__pycache__",
        "ensurepip",
        "_tkinter*",
        "tkinter",
        "idlelib",
        "turtledemo",
        "turtle.py",
    ),
)
copy_file(PYTHON)
copy_file(Path("/etc/ssl/certs/ca-certificates.crt"))

# ldd is applied only to the trusted cached interpreter and stdlib extensions.
# Copy resolved dependencies (and their dependencies), not whole OS directories.
pending = [
    PYTHON,
    *sorted((DEST / STDLIB.relative_to("/") / "lib-dynload").glob("*.so")),
]
# Inspect the original paths, which resolve dependencies in the donor OS cache.
pending = [
    Path("/") / p.relative_to(DEST) if p.is_relative_to(DEST) else p for p in pending
]
seen = set()
while pending:
    source = pending.pop()
    if source in seen:
        continue
    seen.add(source)
    result = subprocess.run(
        ["/usr/bin/ldd", str(source)],
        capture_output=True,
        text=True,
        check=True,
        env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"},
    )
    if "not found" in result.stdout:
        raise SystemExit("CACHED_OS_LIBRARY_MISSING: " + source.name)
    for match in re.finditer(r"(?:=>\s+|^\s*)(/[^\s()]+)", result.stdout, re.MULTILINE):
        dependency = Path(match[1])
        if dependency not in seen:
            copy_file(dependency)
            pending.append(dependency)
