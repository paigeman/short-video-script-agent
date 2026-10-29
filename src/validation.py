"""JSON parsing and Schema validation reused across model and tool boundaries."""

import json
import math

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError


class StructuredOutputError(ValueError):
    def __init__(self, category: str, field_path: str = "$"):
        self.category = category
        self.field_path = field_path
        super().__init__(f"{category} at {field_path}")


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError("Non-finite JSON constant")


def _finite_float(value: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("JSON number exceeds finite float range")
    return result


def parse_json(text: str) -> object:
    try:
        return json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
            parse_float=_finite_float,
        )
    except ValueError as exc:
        raise StructuredOutputError("parse_error") from exc


def validate_json(text: str, schema: dict[str, object]) -> object:
    # Invalid schemas are programming/configuration errors, not model mistakes.
    Draft202012Validator.check_schema(schema)
    data = parse_json(text)
    try:
        Draft202012Validator(schema).validate(data)
    except ValidationError as exc:
        path = ".".join(str(part) for part in exc.absolute_path) or "$"
        raise StructuredOutputError("schema_validation_error", path) from exc
    return data
