import io
import json
import unittest
from contextlib import redirect_stdout
from dataclasses import replace
from unittest.mock import Mock, patch

from src.config import ConfigurationError, ModelConfig
from src.config import main as check_config
from src.main import main
from src.video.catalog import Catalog
from src.video.offline import OfflineModel
from src.video.service import run_script
from tests.video_fixtures import brief

ENV = {
    "MODEL": "test-model",
    "API_KEY": "unit-test-placeholder",
    "BASE_URL": "https://model.example.invalid/private-route",
    "MODEL_TIMEOUT_SECONDS": "12.5",
    "MAX_OUTPUT_TOKENS": "8192",
    "REASONING_EFFORT": "high",
    "MAX_RUN_SECONDS": "300",
}


class LiveConfigTests(unittest.TestCase):
    def test_defaults_accept_unregistered_models_without_reading_files(self):
        with patch("pathlib.Path.read_text", side_effect=AssertionError("No files")):
            config = ModelConfig.from_env(
                {"MODEL": " custom-model ", "API_KEY": " unit-test-placeholder "}
            )
        self.assertEqual(config.model, "custom-model")
        self.assertEqual(config.api_key, "unit-test-placeholder")
        self.assertEqual(config.timeout_seconds, 30)
        self.assertEqual(config.max_output_tokens, 4096)
        self.assertEqual(config.max_run_seconds, 180)
        self.assertIsNone(config.base_url)
        self.assertIsNone(config.reasoning_effort)

    def test_environment_is_loaded_explicitly_and_parsed_without_mutation(self):
        env = dict(ENV)
        with patch.dict("os.environ", env, clear=True):
            config = ModelConfig.from_env()
        self.assertEqual(config.timeout_seconds, 12.5)
        self.assertEqual(config.max_output_tokens, 8192)
        self.assertEqual(config.max_run_seconds, 300)
        self.assertEqual(config.reasoning_effort, "high")
        self.assertEqual(env, ENV)

    def test_invalid_values_report_the_field_without_exposing_values(self):
        cases = [
            ("MODEL", " "),
            ("API_KEY", ""),
            ("MODEL_TIMEOUT_SECONDS", "0"),
            ("MODEL_TIMEOUT_SECONDS", "NaN"),
            ("MODEL_TIMEOUT_SECONDS", "Infinity"),
            ("MAX_RUN_SECONDS", "-1"),
            ("MAX_RUN_SECONDS", "NaN"),
            ("MAX_OUTPUT_TOKENS", "0"),
            ("MAX_OUTPUT_TOKENS", "1.5"),
            ("MAX_OUTPUT_TOKENS", "unit-test-private-value"),
            ("REASONING_EFFORT", ""),
            ("REASONING_EFFORT", "unit-test-private-value"),
            ("BASE_URL", "ftp://model.example.invalid"),
            ("BASE_URL", "https://model.example.invalid?key=unit-test-placeholder"),
            ("BASE_URL", "https://user:unit-test-placeholder@model.example.invalid"),
            ("BASE_URL", "https://model.example.invalid#fragment"),
            ("BASE_URL", "https://model.example.invalid:bad"),
            ("BASE_URL", "https://model.example.invalid/has space"),
        ]
        for name, value in cases:
            with self.subTest(name=name, value=value):
                with self.assertRaises(ConfigurationError) as caught:
                    ModelConfig.from_env({**ENV, name: value})
                self.assertEqual(caught.exception.field_name, name)
                self.assertEqual(str(caught.exception), f"Missing or invalid {name}")

    def test_direct_construction_also_rejects_invalid_numeric_types(self):
        config = ModelConfig.from_env(ENV)
        for field, value in (
            ("max_output_tokens", True),
            ("max_output_tokens", 3.5),
            ("timeout_seconds", True),
            ("timeout_seconds", float("nan")),
            ("max_run_seconds", False),
            ("reasoning_effort", []),
            ("base_url", 42),
        ):
            with self.subTest(field=field), self.assertRaises(ConfigurationError):
                replace(config, **{field: value})

    def test_public_settings_and_repr_exclude_credentials_and_endpoint(self):
        config = ModelConfig.from_env(ENV)
        public = json.dumps(config.public_settings())
        for sensitive in (ENV["API_KEY"], ENV["BASE_URL"], "private-route"):
            self.assertNotIn(sensitive, public)
            self.assertNotIn(sensitive, repr(config))
        self.assertEqual(config.public_settings()["endpoint"], "custom")
        self.assertEqual(
            replace(config, base_url=None).public_settings()["endpoint"], "sdk_default"
        )

    def test_config_check_is_local_only_and_has_safe_exit_codes(self):
        for env, code, status in (
            (ENV, 0, "configuration_valid"),
            (
                {**ENV, "MAX_OUTPUT_TOKENS": "unit-test-private-value"},
                2,
                "configuration_error",
            ),
        ):
            with (
                self.subTest(status=status),
                patch.dict("os.environ", env, clear=True),
                patch("sys.argv", ["src.config"]),
                patch(
                    "src.llm.responses.OpenAI", side_effect=AssertionError("No client")
                ),
                redirect_stdout(io.StringIO()) as output,
            ):
                self.assertEqual(check_config(), code)
                report = json.loads(output.getvalue())
                self.assertEqual(report["status"], status)
                self.assertNotIn(ENV["API_KEY"], output.getvalue())
                self.assertNotIn(ENV["BASE_URL"], output.getvalue())

    def test_live_cli_uses_config_once_and_closes_owned_client(self):
        offline = OfflineModel(brief(), Catalog.load().policy)
        client = Mock(model="test-model")
        client.send.side_effect = offline.send
        with (
            patch.dict("os.environ", ENV, clear=True),
            patch(
                "src.video.service.ResponsesClient.from_config", return_value=client
            ) as factory,
            redirect_stdout(io.StringIO()) as output,
        ):
            self.assertEqual(
                main(["--mode", "live", "--input", "examples/normal.input.json"]), 0
            )
        factory.assert_called_once_with(ModelConfig.from_env(ENV))
        client.close.assert_called_once()
        report = json.loads(output.getvalue())
        self.assertEqual(
            report["model_settings"],
            {
                **ModelConfig.from_env(ENV).public_settings(),
                "output_format": "json_object",
            },
        )
        self.assertEqual(report["runtime"]["limits"]["max_run_seconds"], 300)
        for call in client.send.call_args_list:
            request = call.args[0]
            self.assertEqual(request.max_output_tokens, 8192)
            self.assertEqual(request.reasoning_effort, "high")
            self.assertLessEqual(request.timeout_seconds, 12.5)
        self.assertNotIn(ENV["API_KEY"], output.getvalue())
        self.assertNotIn(ENV["BASE_URL"], output.getvalue())

    def test_bad_live_config_fails_before_creating_a_client(self):
        with (
            patch.dict(
                "os.environ",
                {**ENV, "MAX_OUTPUT_TOKENS": "unit-test-private-value"},
                clear=True,
            ),
            patch("src.video.service.ResponsesClient.from_config") as factory,
            redirect_stdout(io.StringIO()) as output,
        ):
            self.assertEqual(main(["--input", "examples/normal.input.json"]), 2)
        factory.assert_not_called()
        report = json.loads(output.getvalue())
        self.assertEqual(report["reason"], "invalid_model_configuration")
        self.assertEqual(report["issues"][0]["field"], "MAX_OUTPUT_TOKENS")
        self.assertNotIn("unit-test-private-value", output.getvalue())

    def test_offline_and_missing_input_do_not_read_live_configuration(self):
        with patch(
            "src.video.service.ModelConfig.from_env",
            side_effect=AssertionError("No environment"),
        ):
            self.assertEqual(run_script(brief(), mode="offline")["status"], "completed")
            self.assertEqual(run_script({})["status"], "needs_input")
        with self.assertRaises(ValueError):
            run_script(brief(), mode="offline", config=ModelConfig.from_env(ENV))
