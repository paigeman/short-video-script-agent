"""Read a JSON request and report the scaffold's implementation status."""

import argparse
import json
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="JSON input file")
    args = parser.parse_args(argv)

    try:
        request = json.loads(args.input.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        result = {"status": "invalid_input", "message": str(exc), "trace": []}
        exit_code = 2
    else:
        if not isinstance(request, dict):
            result = {
                "status": "invalid_input",
                "message": "Input must be a JSON object.",
                "trace": [],
            }
            exit_code = 2
        else:
            result = {
                "status": "not_implemented",
                "message": "Project scaffold only; model and tools are not implemented.",
                "trace": [],
            }
            exit_code = 0

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
