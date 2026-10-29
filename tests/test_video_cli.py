import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class VideoCliTests(unittest.TestCase):
    def execute(self, *arguments, stdin=None):
        env = {
            key: value
            for key, value in os.environ.items()
            if key not in {"MODEL", "API_KEY", "BASE_URL"}
        }
        return subprocess.run(
            [sys.executable, "-m", "src.main", *arguments],
            cwd=ROOT,
            env=env,
            input=stdin,
            capture_output=True,
            text=True,
            timeout=15,
        )

    def test_offline_acceptance_cases_have_explicit_exit_codes(self):
        cases = [
            ("normal", "normal", 0, "completed"),
            ("missing", "normal", 3, "needs_input"),
            ("no-materials", "normal", 3, "needs_input"),
            ("tool-failure", "normal", 0, "completed"),
            ("duration-repair", "duration-repair", 0, "completed"),
            ("rules-repair", "rules-repair", 0, "completed"),
            ("unrepairable", "unrepairable", 1, "incomplete"),
        ]
        for name, scenario, exit_code, status in cases:
            with self.subTest(name=name):
                result = self.execute(
                    "--mode",
                    "offline",
                    "--input",
                    f"examples/{name}.input.json",
                    "--offline-scenario",
                    scenario,
                )
                self.assertEqual(result.returncode, exit_code, result.stderr)
                output = json.loads(result.stdout)
                self.assertEqual(
                    (output["status"], output["mode"]), (status, "offline")
                )
                self.assertIn("trace", output)

    def test_live_mode_has_no_silent_mock_fallback(self):
        result = self.execute("--input", "examples/normal.input.json")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)["status"], "configuration_error")
        self.assertNotIn("offline-video-test-double", result.stdout)

    def test_bad_input_and_data_errors_do_not_expose_local_paths(self):
        for arguments, reason in (
            (
                ("--input", "examples/nonexistent.input.json"),
                "unreadable_or_invalid_json",
            ),
            (
                (
                    "--input",
                    "examples/normal.input.json",
                    "--materials",
                    "missing-materials.json",
                ),
                "invalid_model_or_data_configuration",
            ),
        ):
            result = self.execute("--mode", "offline", *arguments)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(json.loads(result.stdout)["reason"], reason)
            self.assertNotIn(str(ROOT), result.stdout)

    def test_interactive_answer_is_read_without_polluting_json_stdout(self):
        result = self.execute(
            "--mode",
            "offline",
            "--input",
            "examples/no-materials.input.json",
            "--interactive",
            stdin="没有额外资料\n",
        )
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)["status"], "incomplete")
        self.assertIn("请补充", result.stderr)
