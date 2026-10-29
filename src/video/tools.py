"""Per-run tools and receipts; only checked, immutable draft IDs can be delivered."""

import hashlib
import json
from copy import deepcopy

from src.tools.definition import RegisteredTool, ToolDefinition
from src.tools.errors import InvalidToolArgumentsError
from src.tools.registry import ToolRegistry
from src.video.catalog import Catalog
from src.video.checks import VISUALS, check_rules, estimate_duration
from src.video.schemas import DRAFT_SCHEMA

REASON_SCHEMA = {"type": "string", "minLength": 1, "maxLength": 300, "pattern": r"\S"}


def draft_id(draft: dict) -> str:
    return hashlib.sha256(
        json.dumps(
            draft,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


class VideoTools:
    def __init__(
        self, brief: dict, catalog: Catalog, failures: dict[str, int] | None = None
    ):
        self.brief = deepcopy(brief)
        self.catalog = catalog
        self.retrieved: set[str] = set()
        self.drafts: dict[str, dict] = {}
        self.duration_checks: dict[str, dict] = {}
        self.rule_checks: dict[str, dict] = {}
        self.records: list[dict] = []
        self.failures = dict(failures or {})

    def _recorded(self, name, handler):
        def execute(arguments):
            record = {
                "tool": name,
                "reason": arguments["reason"],
                "arguments": deepcopy(dict(arguments)),
            }
            if self.failures.get(name, 0) > 0:
                self.failures[name] -= 1
                record.update(status="error", error="simulated_tool_failure")
                self.records.append(record)
                raise RuntimeError("Simulated tool failure")
            try:
                output = handler(arguments)
            except InvalidToolArgumentsError:
                record.update(status="error", error="invalid_arguments")
                self.records.append(record)
                raise
            record.update(status="returned", result=deepcopy(output))
            self.records.append(record)
            return output

        return execute

    def registry(self) -> ToolRegistry:
        def tool(name, description, properties, handler):
            schema = {
                "type": "object",
                "properties": {**properties, "reason": REASON_SCHEMA},
                "required": [*properties, "reason"],
                "additionalProperties": False,
            }
            return RegisteredTool(
                ToolDefinition(
                    name,
                    description + " reason 写简短动作目的\uff0c不需要内部思维过程。",
                    schema,
                ),
                self._recorded(name, handler),
            )

        return ToolRegistry(
            [
                tool(
                    "search_materials",
                    "检索指定产品的合成素材\uff1b无结果可改写 query 或使用产品 ID 查询。返回可引用的 fact_id 与原文。",
                    {
                        "query": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 300,
                            "pattern": r"\S",
                        }
                    },
                    self.search,
                ),
                tool(
                    "estimate_duration",
                    "存储候选脚本并估算分镜与总时长。每次修改必须重新调用\uff0c返回新的 draft_id。",
                    {"script": DRAFT_SCHEMA},
                    self.estimate,
                ),
                tool(
                    "check_rules",
                    "核对已存储草稿的素材引用与品牌规则。使用 estimate_duration 返回的 draft_id。",
                    {"draft_id": {"type": "string", "pattern": r"^[a-f0-9]{64}$"}},
                    self.check,
                ),
            ]
        )

    def search(self, arguments):
        matches = self.catalog.search(self.brief["product_id"], arguments["query"])
        results = []
        truncated = False
        for item in matches:
            visible = {**item, "facts": []}
            for fact in item["facts"]:
                proposal = [*results, {**visible, "facts": [*visible["facts"], fact]}]
                if (
                    len(json.dumps(proposal, ensure_ascii=False).encode("utf-8"))
                    > 16_000
                ):
                    truncated = True
                    break
                visible["facts"].append(fact)
            if visible["facts"]:
                results.append(visible)
            if truncated:
                break
        self.retrieved.update(
            fact["fact_id"] for item in results for fact in item["facts"]
        )
        return {
            "query": arguments["query"],
            "product_id": self.brief["product_id"],
            "materials": results,
            "count": len(results),
            "truncated": truncated,
            "synthetic": True,
        }

    def estimate(self, arguments):
        draft = deepcopy(arguments["script"])
        key = draft_id(draft)
        report = estimate_duration(
            draft, self.brief["duration_seconds"], self.catalog.policy["timing"]
        )
        self.drafts[key] = draft
        self.duration_checks[key] = report
        return {"draft_id": key, **report}

    def check(self, arguments):
        key = arguments["draft_id"]
        if key not in self.drafts:
            raise InvalidToolArgumentsError(
                "Unknown draft_id; estimate the exact draft first"
            )
        report = check_rules(
            self.drafts[key], self.catalog, self.brief["product_id"], self.retrieved
        )
        self.rule_checks[key] = report
        return {
            "draft_id": key,
            "passed": report["passed"],
            "issues": report["issues"][:20],
            "issue_count": len(report["issues"]),
            "fact_ids": [fact["fact_id"] for fact in report["citations"]],
        }

    def finalize(self, key: str) -> tuple[dict | None, list[dict]]:
        if (
            key not in self.drafts
            or key not in self.duration_checks
            or key not in self.rule_checks
        ):
            return None, [
                {
                    "code": "missing_checks",
                    "message": "最终草稿缺少实际估时或规则检查记录。",
                }
            ]
        draft = self.drafts[key]
        if draft_id(draft) != key:
            return None, [
                {"code": "draft_changed", "message": "草稿内容与已检查的标识不一致。"}
            ]
        duration = estimate_duration(
            draft, self.brief["duration_seconds"], self.catalog.policy["timing"]
        )
        rules = check_rules(
            draft, self.catalog, self.brief["product_id"], self.retrieved
        )
        issues = deepcopy(rules["issues"])
        if not self.rule_checks[key]["passed"]:
            issues.append(
                {
                    "code": "rule_check_not_passed",
                    "message": "最终草稿必须经过一次通过的模型工具检查。",
                }
            )
        if not duration["passed"] or not self.duration_checks[key]["passed"]:
            issues.append(
                {
                    "code": "duration_exceeded",
                    "message": "最终草稿超过请求的硬性时长上限。",
                }
            )
        if issues:
            return None, issues
        facts = {fact["fact_id"]: fact for fact in rules["citations"]}
        scenes = []
        for scene, timing in zip(draft["scenes"], duration["scenes"], strict=True):
            scenes.append(
                {
                    **deepcopy(scene),
                    "visual": VISUALS[scene["visual"]],
                    "visual_kind": scene["visual"],
                    "estimated_seconds": timing["estimated_seconds"],
                    "start_seconds": timing["start_seconds"],
                    "end_seconds": timing["end_seconds"],
                    "source_ids": sorted(
                        {facts[key]["source_id"] for key in scene["fact_ids"]}
                    ),
                }
            )
        used_ids = {fact["source_id"] for fact in facts.values()}
        sources = [
            {
                "id": item["id"],
                "title": item["title"],
                "source": item["source"],
                "facts": [
                    deepcopy(fact)
                    for fact in facts.values()
                    if fact["source_id"] == item["id"]
                ],
            }
            for item in self.catalog.materials
            if item["id"] in used_ids
        ]
        return {
            "draft_id": key,
            "title": draft["title"],
            "scenes": scenes,
            "estimated_total_seconds": duration["estimated_total_seconds"],
            "target_duration_seconds": self.brief["duration_seconds"],
            "sources": sources,
            "checks": {"duration": duration, "rules": rules},
            "risks": [
                "素材为合成演示资料。",
                "时长按公开的本地估算规则计算\uff0c录制后仍需复核实际时长。",
            ],
        }, []
