import unittest
from typing import ClassVar

from jsonschema.exceptions import SchemaError

from src.validation import StructuredOutputError, validate_json


class ValidationTests(unittest.TestCase):
    schema: ClassVar[dict] = {
        "type": "object",
        "required": ["value"],
        "properties": {"value": {"type": "integer"}},
    }

    def test_valid_document(self):
        self.assertEqual(validate_json('{"value":2}', self.schema), {"value": 2})

    def test_invalid_json_is_not_repaired(self):
        for value in (
            "{",
            "```json\n{}\n```",
            '{"value":1,"value":2}',
            '{"value":NaN}',
            '{"value":1e999}',
            '{"value":-1e999}',
        ):
            with (
                self.subTest(value=value),
                self.assertRaises(StructuredOutputError) as caught,
            ):
                validate_json(value, self.schema)
            self.assertEqual(caught.exception.category, "parse_error")

    def test_schema_failure_is_distinct_and_does_not_echo_content(self):
        with self.assertRaises(StructuredOutputError) as caught:
            validate_json('{"value":"synthetic-private-text"}', self.schema)
        self.assertEqual(caught.exception.category, "schema_validation_error")
        self.assertEqual(caught.exception.field_path, "value")
        self.assertNotIn("synthetic-private-text", str(caught.exception))

    def test_bad_schema_is_a_configuration_error(self):
        with self.assertRaises(SchemaError):
            validate_json("{}", {"type": "not-a-json-type"})
