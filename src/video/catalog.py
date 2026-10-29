"""Read validated synthetic materials and a configurable brand policy."""

import json
import re
from copy import deepcopy
from pathlib import Path

from jsonschema import Draft202012Validator

from src.validation import parse_json

DATA_ROOT = Path(__file__).resolve().parents[2] / "data"
MATERIALS_SCHEMA = {
    "type": "object",
    "required": ["synthetic", "materials"],
    "properties": {
        "synthetic": {"const": True},
        "materials": {
            "type": "array",
            "maxItems": 500,
            "items": {
                "type": "object",
                "required": ["id", "product_id", "title", "facts", "source"],
                "properties": {
                    "id": {"type": "string", "pattern": r"^[A-Za-z0-9_-]{1,40}$"},
                    "product_id": {
                        "type": "string",
                        "pattern": r"^[A-Za-z0-9_-]{1,40}$",
                    },
                    "title": {"type": "string", "minLength": 1, "maxLength": 200},
                    "source": {"type": "string", "minLength": 1, "maxLength": 200},
                    "facts": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 20,
                        "uniqueItems": True,
                        "items": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 500,
                            "pattern": r"\S",
                        },
                    },
                },
                "additionalProperties": False,
            },
        },
    },
    "additionalProperties": False,
}
POLICY_SCHEMA = {
    "type": "object",
    "required": ["synthetic", "rules", "neutral_copy", "prohibited_phrases", "timing"],
    "properties": {
        "synthetic": {"const": True},
        "rules": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["id", "description"],
                "properties": {
                    "id": {"type": "string"},
                    "description": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
        "neutral_copy": {
            "type": "array",
            "minItems": 1,
            "maxItems": 100,
            "uniqueItems": True,
            "items": {
                "type": "string",
                "minLength": 1,
                "maxLength": 120,
                "pattern": r"\S",
            },
        },
        "prohibited_phrases": {
            "type": "array",
            "uniqueItems": True,
            "items": {"type": "string", "minLength": 1},
        },
        "timing": {
            "type": "object",
            "required": [
                "speech_units_per_second",
                "subtitle_units_per_second",
                "punctuation_pause_seconds",
                "transition_seconds",
            ],
            "properties": {
                "speech_units_per_second": {
                    "type": "number",
                    "exclusiveMinimum": 0,
                    "maximum": 20,
                },
                "subtitle_units_per_second": {
                    "type": "number",
                    "exclusiveMinimum": 0,
                    "maximum": 30,
                },
                "punctuation_pause_seconds": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 3,
                },
                "transition_seconds": {"type": "number", "minimum": 0, "maximum": 3},
            },
            "additionalProperties": False,
        },
    },
    "additionalProperties": False,
}


class Catalog:
    def __init__(self, materials: dict, policy: dict):
        json.dumps([materials, policy], allow_nan=False)
        Draft202012Validator(MATERIALS_SCHEMA).validate(materials)
        Draft202012Validator(POLICY_SCHEMA).validate(policy)
        self.materials = deepcopy(materials["materials"])
        self.policy = deepcopy(policy)
        ids = [item["id"] for item in self.materials]
        if len(ids) != len(set(ids)):
            raise ValueError("Material IDs must be unique")
        if any(
            not any(char.isalnum() for char in fact)
            for item in self.materials
            for fact in item["facts"]
        ):
            raise ValueError("Material facts must contain meaningful text")
        self.facts = {
            f"{item['id']}:F{index + 1}": {
                "fact_id": f"{item['id']}:F{index + 1}",
                "source_id": item["id"],
                "product_id": item["product_id"],
                "text": fact,
            }
            for item in self.materials
            for index, fact in enumerate(item["facts"])
        }

    @classmethod
    def load(cls, materials_path: Path | None = None, policy_path: Path | None = None):
        materials = parse_json(
            (materials_path or DATA_ROOT / "materials.json").read_text(encoding="utf-8")
        )
        policy = parse_json(
            (policy_path or DATA_ROOT / "brand_rules.json").read_text(encoding="utf-8")
        )
        return cls(materials, policy)

    def search(self, product_id: str, query: str, limit: int = 5) -> list[dict]:
        query = query.strip().casefold()
        words = set(re.findall(r"[a-z0-9_]+|[\u3400-\u9fff]{2}", query))
        # Overlapping bigrams tolerate longer Chinese phrases and query rewrites.
        for phrase in re.findall(r"[\u3400-\u9fff]+", query):
            words.update(phrase[i : i + 2] for i in range(len(phrase) - 1))
        ranked = []
        for item in self.materials:
            if item["product_id"] != product_id:
                continue
            haystack = (item["title"] + " " + " ".join(item["facts"])).casefold()
            score = sum(word in haystack for word in words)
            if query in {product_id.casefold(), item["id"].casefold()}:
                score += 100
            if query and query in haystack:
                score += 10
            if score:
                ranked.append((score, item))
        ranked.sort(key=lambda entry: (-entry[0], entry[1]["id"]))
        return [
            {
                "source_id": item["id"],
                "product_id": item["product_id"],
                "title": item["title"],
                "source": item["source"],
                "facts": [
                    deepcopy(self.facts[f"{item['id']}:F{i + 1}"])
                    for i in range(len(item["facts"]))
                ],
            }
            for _, item in ranked[:limit]
        ]
