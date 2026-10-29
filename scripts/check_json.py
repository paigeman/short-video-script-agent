"""Validate project JSON syntax, duplicate keys, and non-finite numbers."""

import json
from pathlib import Path


def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate object key: {key!r}")
        result[key] = value
    return result


def reject_constant(value: str) -> None:
    raise ValueError(f"Non-finite number is not valid JSON: {value}")


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    paths = set(root.glob("*.json"))
    for directory in ("data", "examples"):
        paths.update(root.joinpath(directory).rglob("*.json"))

    errors = []
    for path in sorted(paths):
        try:
            json.loads(
                path.read_text(encoding="utf-8"),
                object_pairs_hook=unique_object,
                parse_constant=reject_constant,
            )
        except (OSError, UnicodeError, ValueError) as exc:
            errors.append(f"{path.relative_to(root)}: {exc}")

    if errors:
        print("\n".join(errors))
        return 1
    print(f"Validated {len(paths)} JSON files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
