"""Input and model-output contracts for the short-video task."""

from copy import deepcopy

from jsonschema import Draft202012Validator

TEXT = {"type": "string", "minLength": 1, "maxLength": 500, "pattern": r"\S"}
BRIEF_SCHEMA = {
    "type": "object",
    "required": [
        "topic",
        "audience",
        "platform",
        "duration_seconds",
        "style",
        "product_id",
    ],
    "properties": {
        "topic": TEXT,
        "audience": TEXT,
        "platform": TEXT,
        "style": TEXT,
        "duration_seconds": {"type": "integer", "minimum": 1, "maximum": 300},
        "product_id": {"type": "string", "pattern": r"^[A-Za-z0-9_-]{1,40}$"},
        "simulate_tool_failure": {"type": "boolean"},
    },
    "additionalProperties": False,
}
SCENE_SCHEMA = {
    "type": "object",
    "required": ["id", "visual", "narration", "subtitle", "hold_seconds", "fact_ids"],
    "properties": {
        "id": {"type": "string", "pattern": r"^[A-Za-z0-9_-]{1,30}$"},
        "visual": {
            "enum": [
                "title_card",
                "screen_demo",
                "screen_closeup",
                "step_card",
                "recap_card",
                "closing_card",
            ]
        },
        "narration": {"type": "string", "maxLength": 2000},
        "subtitle": {"type": "string", "maxLength": 2000},
        "hold_seconds": {"type": "number", "minimum": 0, "maximum": 300},
        "fact_ids": {
            "type": "array",
            "items": {"type": "string", "maxLength": 50},
            "uniqueItems": True,
            "maxItems": 20,
        },
    },
    "additionalProperties": False,
}
DRAFT_SCHEMA = {
    "type": "object",
    "required": ["title", "scenes"],
    "properties": {
        "title": {"type": "string", "minLength": 1, "maxLength": 120},
        "scenes": {
            "type": "array",
            "items": SCENE_SCHEMA,
            "minItems": 1,
            "maxItems": 12,
        },
    },
    "additionalProperties": False,
}
BRIEF_SCHEMA["properties"]["initial_draft"] = DRAFT_SCHEMA
FINAL_SCHEMA = {
    "oneOf": [
        {
            "type": "object",
            "required": ["status", "draft_id"],
            "properties": {
                "status": {"const": "completed"},
                "draft_id": {"type": "string", "pattern": r"^[a-f0-9]{64}$"},
            },
            "additionalProperties": False,
        },
        {
            "type": "object",
            "required": ["status", "reason"],
            "properties": {
                "status": {"const": "incomplete"},
                "reason": {
                    "enum": [
                        "no_materials",
                        "cannot_meet_constraints",
                        "tool_failure",
                        "insufficient_information",
                    ]
                },
            },
            "additionalProperties": False,
        },
    ]
}


def validate_brief(value: object) -> tuple[dict, list[str], list[dict]]:
    if not isinstance(value, dict):
        return {}, [], [{"field": "$", "code": "object_required"}]
    brief = deepcopy(value)
    for name, content in brief.items():
        if isinstance(content, str):
            brief[name] = content.strip()
    missing = [
        name
        for name in BRIEF_SCHEMA["required"]
        if name not in brief or brief[name] in (None, "")
    ]
    present_schema = {**BRIEF_SCHEMA, "required": []}
    present = {name: content for name, content in brief.items() if name not in missing}
    errors = [
        {
            "field": ".".join(str(p) for p in error.absolute_path) or "$",
            "code": error.validator,
        }
        for error in Draft202012Validator(present_schema).iter_errors(present)
    ]
    return brief, missing, errors
