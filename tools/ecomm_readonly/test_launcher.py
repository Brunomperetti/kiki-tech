"""Host-side launcher checks, with every Docker subprocess replaced by a mock."""

import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

import run as launcher


class Launcher(unittest.TestCase):
    @patch.object(launcher.subprocess, "run")
    def test_run_is_offline_nonroot_readonly_without_mounts_or_inherited_secrets(
        self, execute
    ):
        execute.return_value = subprocess.CompletedProcess([], 0)
        with patch.dict(
            os.environ,
            {
                "ECOMM_APP_API_TOKEN": "NON_SECRET_INHERITED_CONTROL",
                "DATABASE_URL": "postgresql://never-used.invalid/blocked",
                "DOCKER_HOST": "tcp://never-used.invalid:2375",
                "DOCKER_CONFIG": "/must-not-read-inherited-config",
                "HTTPS_PROXY": "http://never-used.invalid:1234",
            },
        ):
            self.assertEqual(launcher.run("test"), 0)
            args = execute.call_args.args[0]
            env = execute.call_args.kwargs["env"]
        self.assertEqual(args[:2], ["docker", "--host=unix:///var/run/docker.sock"])
        for flag in (
            "--network=none",
            "--read-only",
            "--user=1000:1000",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges:true",
            "--memory=192m",
            "--pids-limit=16",
            "--pull=never",
            "--rm",
        ):
            self.assertIn(flag, args)
        self.assertEqual(args[-2:], [launcher.IMAGE, "test"])
        for prohibited in (
            "--mount",
            "-v",
            "--volume",
            "-p",
            "--publish",
            "--env-file",
            "--privileged",
            "--network=host",
        ):
            self.assertNotIn(prohibited, args)
        self.assertFalse(
            any(
                "NON_SECRET_INHERITED_CONTROL" in value
                for value in args + list(env.values())
            )
        )
        self.assertEqual(set(env) - {"PATH", "HOME"}, {"DOCKER_CONFIG"})
        self.assertFalse(Path(env["DOCKER_CONFIG"]).exists())
        self.assertIn("HTTPS_PROXY=", args)

    @patch.object(launcher.subprocess, "run")
    def test_build_cannot_pull_or_include_the_repository(self, execute):
        execute.return_value = subprocess.CompletedProcess([], 0)
        self.assertEqual(launcher.run("build"), 0)
        args = execute.call_args.args[0]
        self.assertIn("--pull=false", args)
        self.assertIn("--network=none", args)
        self.assertEqual(args[-1], str(Path(__file__).resolve().parent))
        self.assertEqual(execute.call_count, 2)

    @patch.object(launcher.subprocess, "run")
    def test_missing_local_base_stops_without_pull_or_fallback(self, execute):
        execute.return_value = subprocess.CompletedProcess([], 1)
        self.assertEqual(launcher.run("build"), 2)
        self.assertEqual(execute.call_count, 1)
        self.assertIn("inspect", execute.call_args.args[0])

    @patch.object(launcher.subprocess, "run")
    def test_unknown_live_or_production_commands_never_run_docker(self, execute):
        for command in (
            "live",
            "refresh",
            "sync",
            "deploy",
            "--token",
            "https://admin.ecomm-app.com",
        ):
            self.assertEqual(launcher.run(command), 2)
        execute.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
