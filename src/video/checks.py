"""Deterministic duration, citation, and brand checks for a stored draft."""

import re
import unicodedata
from decimal import ROUND_CEILING, Decimal

from src.video.catalog import Catalog

VISUALS = {
    "title_card": "显示标题卡",
    "screen_demo": "展示操作界面\uff08示意\uff0c制作时替换为实际画面\uff09",
    "screen_closeup": "字幕区域特写\uff08以实际界面为准\uff0c突出本分镜引用的事实\uff09",
    "step_card": "步骤提示卡\uff08按本分镜字幕排版\uff0c不添加未提供的按钮或操作\uff09",
    "recap_card": "要点回顾卡\uff08只展示本分镜已引用事实与获准过渡语\uff09",
    "closing_card": "显示结束卡",
}


def units(text: str) -> int:
    return len(re.findall(r"[A-Za-z]+|\d|[^\W\d_]", text))


def _decimal(value) -> Decimal:
    return Decimal(str(value))


def _ceil(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.1"), rounding=ROUND_CEILING)


def estimate_duration(draft: dict, target_seconds: int, timing: dict) -> dict:
    scenes = []
    for scene in draft["scenes"]:
        spoken = units(scene["narration"])
        subtitle = units(scene["subtitle"])
        pauses = len(
            re.findall(r"[\uff0c。\uff01\uff1f\uff1b,.!?;]", scene["narration"])
        )
        speech_seconds = _ceil(
            _decimal(spoken) / _decimal(timing["speech_units_per_second"])
            + _decimal(pauses) * _decimal(timing["punctuation_pause_seconds"])
        )
        subtitle_seconds = _ceil(
            _decimal(subtitle) / _decimal(timing["subtitle_units_per_second"])
        )
        duration = _ceil(
            max(speech_seconds, subtitle_seconds, _decimal(scene["hold_seconds"]))
        )
        scenes.append(
            {
                "scene_id": scene["id"],
                "spoken_units": spoken,
                "subtitle_units": subtitle,
                "narration_seconds": float(speech_seconds),
                "subtitle_seconds": float(subtitle_seconds),
                "hold_seconds": scene["hold_seconds"],
                "estimated_seconds": float(duration),
            }
        )
    transitions = _ceil(
        _decimal(len(scenes) - 1) * _decimal(timing["transition_seconds"])
    )
    total = sum((_decimal(scene["estimated_seconds"]) for scene in scenes), transitions)
    elapsed = Decimal(0)
    for index, scene in enumerate(scenes):
        offset = _ceil(_decimal(index) * _decimal(timing["transition_seconds"]))
        scene["start_seconds"] = float(elapsed + offset)
        elapsed += _decimal(scene["estimated_seconds"])
        scene["end_seconds"] = float(elapsed + offset)
    return {
        "passed": total <= target_seconds,
        "target_seconds": target_seconds,
        "estimated_total_seconds": float(total),
        "over_by_seconds": float(max(Decimal(0), total - target_seconds)),
        "transition_seconds": float(transitions),
        "scenes": scenes,
        "assumptions": {
            **timing,
            "unit_definition": "每个中文等非 ASCII 字母、每位数字计 1 单位\uff1b连续英文字母计 1 单词单位",
            "scene_duration": "max(口播估算, 字幕阅读估算, 画面停留)\uff0c最后加镜头间转场",
        },
    }


def normalized(text: str) -> str:
    return "".join(
        char
        for char in unicodedata.normalize("NFKC", text).casefold()
        if not char.isspace()
    )


def _uncovered(text: str, allowed: list[str]) -> str:
    remaining = normalized(text)
    for phrase in sorted({normalized(item) for item in allowed}, key=len, reverse=True):
        if phrase:
            remaining = remaining.replace(phrase, "")
    # Keep meaningful numeric operators: dropping decimal points inside facts
    # would incorrectly equate values such as 0.8 and 08.
    return "".join(char for char in remaining if char.isalnum() or char in "%+-=/")


def check_rules(
    draft: dict, catalog: Catalog, product_id: str, retrieved: set[str]
) -> dict:
    issues = []
    citations = {}
    seen_scene_ids = set()
    policy = catalog.policy

    def issue(code, field, message, rule_id="R01"):
        issues.append(
            {"code": code, "field": field, "message": message, "rule_id": rule_id}
        )

    def check_copy(text, allowed_facts, field):
        approved = policy["neutral_copy"] + [fact["text"] for fact in allowed_facts]
        uncovered = _uncovered(text, approved)
        if uncovered:
            issue(
                "unverified_copy",
                field,
                "文本超出引用事实原文与获准过渡语\uff1a" + uncovered[:100],
            )
        if re.search(r"\d|[%\uff05]", uncovered):
            issue("unsupported_number", field, "缺少原文依据的数值或量化效果。", "R02")
        text_key = "".join(
            char for char in normalized(text) if char.isalnum() or char == "%"
        )
        for phrase in policy["prohibited_phrases"]:
            phrase_key = "".join(
                char for char in normalized(phrase) if char.isalnum() or char == "%"
            )
            if phrase_key and phrase_key in text_key:
                issue(
                    "prohibited_claim", field, f"品牌规则禁止表述\uff1a{phrase}", "R03"
                )

    if not any(char.isalnum() for char in draft["title"]):
        issue("empty_title", "title", "标题必须含有有效文本。")
    for index, scene in enumerate(draft["scenes"]):
        prefix = f"scenes.{index}"
        if scene["id"] in seen_scene_ids:
            issue("duplicate_scene_id", prefix + ".id", "分镜 ID 必须唯一。")
        seen_scene_ids.add(scene["id"])
        if not any(char.isalnum() for char in scene["narration"] + scene["subtitle"]):
            issue("empty_scene_copy", prefix, "每个分镜至少需要旁白或字幕。")
        facts = []
        for fact_id in scene["fact_ids"]:
            fact = catalog.facts.get(fact_id)
            if fact is None:
                issue("unknown_fact", prefix + ".fact_ids", "引用的事实 ID 不存在。")
            elif fact["product_id"] != product_id:
                issue(
                    "wrong_product", prefix + ".fact_ids", "引用不属于请求指定的产品。"
                )
            elif fact_id not in retrieved:
                issue(
                    "unretrieved_fact",
                    prefix + ".fact_ids",
                    "必须先通过素材工具检索到所引用事实。",
                )
            elif not any(
                normalized(fact["text"]) in normalized(scene[field])
                for field in ("narration", "subtitle")
            ):
                issue(
                    "unused_citation",
                    prefix + ".fact_ids",
                    "引用必须对应本分镜实际使用的完整事实原文。",
                )
            else:
                facts.append(fact)
                citations[fact_id] = fact
        for field in ("narration", "subtitle"):
            check_copy(scene[field], facts, prefix + "." + field)
    check_copy(draft["title"], list(citations.values()), "title")
    if not citations:
        issue(
            "missing_evidence", "scenes", "脚本至少需要一条已检索且实际使用的产品事实。"
        )
    return {
        "passed": not issues,
        "issues": issues,
        "citations": list(citations.values()),
    }
