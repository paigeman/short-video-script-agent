"""Generate and check a grounded short-video script through a live or offline Agent."""

import argparse
import json
import sys
from pathlib import Path

from jsonschema.exceptions import ValidationError

from src.config import ConfigurationError
from src.validation import StructuredOutputError, parse_json
from src.video.catalog import Catalog
from src.video.offline import SCENARIOS
from src.video.service import empty_report, run_script


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="JSON request file")
    parser.add_argument("--mode", choices=("live", "offline"), default="live")
    parser.add_argument("--offline-scenario", choices=SCENARIOS, default="normal")
    parser.add_argument("--materials", type=Path, help="Synthetic material JSON")
    parser.add_argument("--rules", type=Path, help="Brand policy JSON")
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Read clarification answers from stdin",
    )
    args = parser.parse_args(argv)

    def read_answer(question):
        print(question, file=sys.stderr)
        try:
            return input().strip() or None
        except EOFError:
            return None

    try:
        request = parse_json(args.input.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, StructuredOutputError):
        report = empty_report(args.mode, "invalid_input", "unreadable_or_invalid_json")
    else:
        try:
            if args.mode == "live" and args.offline_scenario != "normal":
                raise ValueError("Offline scenario is only supported in offline mode")
            catalog = Catalog.load(args.materials, args.rules)
            report = run_script(
                request,
                catalog=catalog,
                mode=args.mode,
                offline_scenario=args.offline_scenario,
                answer_provider=read_answer if args.interactive else None,
            )
        except ConfigurationError as exc:
            report = empty_report(
                args.mode,
                "configuration_error",
                "invalid_model_configuration",
                issues=[{"field": exc.field_name, "code": "invalid_configuration"}],
            )
        except (OSError, UnicodeError, ValueError, ValidationError):
            report = empty_report(
                args.mode, "configuration_error", "invalid_model_or_data_configuration"
            )
        except KeyboardInterrupt:
            report = empty_report(args.mode, "cancelled", "user_interrupted")
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    if report["status"] == "completed":
        return 0
    if report["status"] in {"invalid_input", "configuration_error"}:
        return 2
    if report["status"] == "needs_input":
        return 3
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
