"""Explicit test double driven by actual tool observations, never a live fallback."""

import json
from copy import deepcopy

from src.llm.types import ModelRequest, ModelResponse
from src.tools.protocol import ToolCallRequest, ToolCallResult

SCENARIOS = (
    "normal",
    "duration-repair",
    "rules-repair",
    "tool-failure",
    "persistent-failure",
    "unrepairable",
    "limit",
)


class OfflineModel:
    model = "offline-video-test-double"

    def __init__(self, brief: dict, policy: dict, scenario: str = "normal"):
        if scenario not in SCENARIOS:
            raise ValueError("Unknown offline scenario")
        self.brief = deepcopy(brief)
        self.policy = deepcopy(policy)
        self.scenario = scenario
        self.sequence = 0
        self.facts = []
        self.last_call = None
        self.last_arguments = None
        self.search_rewritten = False
        self.failures_seen = 0
        self.duration_repaired = False
        self.rules_repaired = False
        self.last_script = None

    def call(self, name, arguments, purpose):
        self.sequence += 1
        if name != "ask_user":
            arguments = {**arguments, "reason": purpose}
        self.last_call, self.last_arguments = name, deepcopy(arguments)
        return ModelResponse(
            text=purpose,
            tool_calls=[
                ToolCallRequest(
                    f"offline-{self.sequence}",
                    name,
                    json.dumps(arguments, ensure_ascii=False),
                )
            ],
        )

    @staticmethod
    def stop(reason):
        return ModelResponse(
            text=json.dumps({"status": "incomplete", "reason": reason})
        )

    def draft(self, compact=False, clean=False):
        facts = sorted(
            self.facts, key=lambda fact: (len(fact["text"]), fact["fact_id"])
        )
        selected = facts[:1] if compact else facts[:2]
        scenes = []
        for index, fact in enumerate(selected, 1):
            hold = (
                0
                if compact
                else self.brief["duration_seconds"] / max(1, len(selected)) * 0.6
            )
            if self.scenario == "duration-repair" and not compact:
                hold = min(300, self.brief["duration_seconds"] * 1.2)
            text = fact["text"]
            if self.scenario == "rules-repair" and not clean:
                text += "\uff0c效率提升80%\uff0c保证有效。"
            scenes.append(
                {
                    "id": f"S{index}",
                    "visual": "screen_demo",
                    "narration": text,
                    "subtitle": fact["text"],
                    "hold_seconds": round(hold, 2),
                    "fact_ids": [fact["fact_id"]],
                }
            )
        self.last_script = {"title": self.policy["neutral_copy"][0], "scenes": scenes}
        return self.last_script

    def send(self, request: ModelRequest) -> ModelResponse:
        results = [item for item in request.input if isinstance(item, ToolCallResult)]
        if not results:
            return self.call(
                "search_materials",
                {"query": self.brief["topic"]},
                "先查找主题相关的产品事实。",
            )
        observed = json.loads(results[-1].output)
        if "error" in observed:
            self.failures_seen += 1
            if self.failures_seen > 1:
                return self.stop("tool_failure")
            return self.call(
                self.last_call,
                self.last_arguments,
                "工具返回错误\uff0c进行一次有记录的重试。",
            )
        if self.last_call == "ask_user":
            return self.stop("insufficient_information")
        if self.scenario == "limit":
            return self.call(
                "search_materials",
                {"query": self.brief["product_id"]},
                "继续查找素材以验证运行上限。",
            )
        if self.last_call == "search_materials":
            self.facts = [
                fact for material in observed["materials"] for fact in material["facts"]
            ]
            if not self.facts:
                if not self.search_rewritten:
                    self.search_rewritten = True
                    return self.call(
                        "search_materials",
                        {"query": self.brief["product_id"]},
                        "主题检索为空\uff0c改用指定产品 ID 检索。",
                    )
                return self.call(
                    "ask_user",
                    {
                        "question": "未找到指定产品的可引用素材\uff0c请补充合成素材文件或确认产品 ID 后重新运行。"
                    },
                    "两次检索均无依据\uff0c请求补充资料。",
                )
            return self.call(
                "estimate_duration",
                {"script": deepcopy(self.brief.get("initial_draft")) or self.draft()},
                "根据实际检索到的事实编写首稿并估时。",
            )
        if self.last_call == "estimate_duration":
            if not observed["passed"]:
                if self.duration_repaired:
                    return self.stop("cannot_meet_constraints")
                self.duration_repaired = True
                return self.call(
                    "estimate_duration",
                    {"script": self.draft(compact=True, clean=self.rules_repaired)},
                    "估时超限\uff0c保留最短事实、减少分镜和停留后重新估算。",
                )
            return self.call(
                "check_rules",
                {"draft_id": observed["draft_id"]},
                "估时通过\uff0c检查同一草稿的事实引用和品牌规则。",
            )
        if self.last_call == "check_rules":
            if not observed["passed"]:
                if self.rules_repaired:
                    return self.stop("cannot_meet_constraints")
                self.rules_repaired = True
                return self.call(
                    "estimate_duration",
                    {"script": self.draft(compact=self.duration_repaired, clean=True)},
                    "规则检查不通过\uff0c删除无依据表述后重新估时与检查。",
                )
            return ModelResponse(
                text=json.dumps(
                    {"status": "completed", "draft_id": observed["draft_id"]}
                )
            )
        return self.stop("cannot_meet_constraints")
