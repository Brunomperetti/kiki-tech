"""PG18-only synthetic directory dump and restore, never a Render backup.

Uses the PostgreSQL 18 container already supplied to the CI job.
Does not handle real customer data and refuses to run outside GitHub CI.
"""
import os
import subprocess

if (
    os.environ.get("GITHUB_ACTIONS") != "true"
    or os.environ.get("KIKI_CI_SYNTHETIC_ONLY") != "1"
    or not os.environ.get("KIKI_CI_PG18_CONTAINER")
):
    raise SystemExit("Only the existing GitHub CI PG18 synthetic container is allowed.")

import psycopg  # noqa: E402

from app.services.documental.source_intake_migration import UP, DOWN  # noqa: E402

CONTAINER = os.environ["KIKI_CI_PG18_CONTAINER"]
SRC = "kiki_ci_synthetic"
DEST = "kiki_ci_restored"
ARCHIVE = "/tmp/kiki-ci-synthetic-intake.dir"
USER = "kiki_ci"


def run(*args, check=True):
    return subprocess.run(
        ["docker", *args], text=True, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, timeout=40, check=check,
    )


def exec_pg(*args):
    return run("exec", CONTAINER, *args)


def main():
    image = run("inspect", "--format", "{{.Config.Image}}", CONTAINER).stdout.strip()
    if image != "postgres:18":
        raise RuntimeError("PG18 synthetic container identity mismatch: aborted")
    try:
        # Previous smoke already committed this synthetic guard record.
        assert exec_pg(
            "psql", "-X", "-U", USER, "-d", SRC, "-Atqc",
            "SELECT COUNT(*) FROM public.ci_intake_guard",
        ).stdout.strip() == "1"
        exec_pg("pg_dump", "-U", USER, "-d", SRC, "--format=directory",
                "--file", ARCHIVE, "--no-owner", "--no-acl")
        listing = exec_pg("pg_restore", "-l", "--format=directory", ARCHIVE).stdout
        assert "ci_intake_guard" in listing, "Synthetic archive has no guard table"
        exec_pg("createdb", "-U", USER, DEST)
        exec_pg(
            "pg_restore", "-U", USER, "--format=directory",
            "--no-owner", "--no-acl", "--exit-on-error",
            "-d", DEST, ARCHIVE,
        )
        with psycopg.connect(
            host="127.0.0.1", port=5432, dbname=DEST, user=USER,
            password="synthetic_ci_only", connect_timeout=5,
        ) as db:
            version = db.execute("SHOW server_version").fetchone()[0]
            assert version.startswith("18."), version
            assert db.execute(
                "SELECT COUNT(*) FROM ci_intake_guard"
            ).fetchone()[0] == 1
            assert db.execute(
                "SELECT to_regclass('public.kiki_source_intake_jobs')"
            ).fetchone()[0] is None
            # Exact migration from main branch, not a copied SQL approximation.
            for sql in UP:
                db.execute(sql)
            assert db.execute(
                "SELECT COUNT(*) FROM ci_intake_guard"
            ).fetchone()[0] == 1
            assert db.execute(
                "SELECT to_regclass('public.kiki_source_intake_jobs')"
            ).fetchone()[0] is not None
            for sql in DOWN:  # safe because synthetic queue is empty
                db.execute(sql)
            assert db.execute(
                "SELECT COUNT(*) FROM ci_intake_guard"
            ).fetchone()[0] == 1
            db.rollback()
        print("PG18 synthetic directory dump/pg_restore, migration, "
              "empty-only reversal and pre-existing table preservation PASS")
    finally:
        run("exec", CONTAINER, "dropdb", "-U", USER, "--if-exists", DEST, check=False)
        run("exec", CONTAINER, "rm", "-rf", ARCHIVE, check=False)


if __name__ == "__main__":
    main()
