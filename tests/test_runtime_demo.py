import json
import subprocess
import sys
import unittest
from pathlib import Path


class RuntimeDemoTests(unittest.TestCase):
    def test_actual_cli_runs_all_offline_scenarios(self):
        cases = [
            ("normal", "completed", 1),
            ("tool-failure", "completed", 2),
            ("limit", "incomplete", 2),
        ]
        for scenario, status, executions in cases:
            with self.subTest(scenario=scenario):
                process = subprocess.run(
                    [sys.executable, "-m", "src.agent.demo", "--scenario", scenario],
                    cwd=Path(__file__).resolve().parents[1],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=True,
                )
                result = json.loads(process.stdout)
                self.assertEqual(result["mode"], "offline_demo")
                self.assertEqual(result["status"], status)
                self.assertEqual(result["tool_executions"], executions)
                if scenario == "tool-failure":
                    outputs = [
                        event["output_summary"]
                        for event in result["trace"]
                        if event["event"] == "tool"
                    ]
                    self.assertIn("error", json.loads(outputs[0]))
                    self.assertEqual(json.loads(outputs[1]), {"value": "ready"})
