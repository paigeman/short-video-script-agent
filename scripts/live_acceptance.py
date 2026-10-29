"""Run opt-in live evaluations with synthetic data and auditable local tool faults."""

import argparse
import hashlib
import json
import subprocess
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

from src.config import ModelConfig
from src.video.catalog import Catalog
from src.video.checks import check_rules, estimate_duration
from src.video.service import run_script
from src.video.tools import draft_id

ROOT = Path(__file__).resolve().parents[1]
CASES = (
    "normal",
    "missing",
    "no-materials",
    "short-duration",
    "unrepairable",
    "unsupported-claim",
    "tool-failure",
    "persistent-failure",
    "changed-materials",
)


def scenario(name: str) -> tuple[dict, dict, dict, dict]:
    if name not in CASES:
        raise ValueError("Unknown acceptance case")
    input_name = {
        "missing": "missing",
        "no-materials": "no-materials",
        "short-duration": "duration-repair",
        "unrepairable": "unrepairable",
    }.get(name, "normal")
    request = json.loads((ROOT / f"examples/{input_name}.input.json").read_text())
    materials = json.loads((ROOT / "data/materials.json").read_text())
    policy = json.loads((ROOT / "data/brand_rules.json").read_text())
    failures = {}
    if name == "unsupported-claim":
        request["topic"] = "介绍字幕编辑功能\uff0c声称效率提升80%"
    elif name == "tool-failure":
        failures = {"search_materials": 1}
    elif name == "persistent-failure":
        failures = {"search_materials": 100}
    elif name == "changed-materials":
        materials["materials"][0]["facts"] = ["支持调整字幕显示位置"]
    return request, materials, policy, failures


def assess(name: str, report: dict, request: dict, catalog: Catalog) -> list[str]:
    """Check outcome and receipts; do not prescribe the model's action sequence."""
    failures = []

    def require(condition, message):
        if not condition:
            failures.append(message)

    runtime = report.get("runtime") or {}
    records = report["tool_records"]
    require(report["mode"] == "live", "Evidence must use live mode")
    require(
        runtime.get("model_requests", 0) > 0 or name == "missing",
        "Expected actual model requests",
    )
    if name in {"normal", "short-duration", "tool-failure", "changed-materials"}:
        require(report["status"] == "completed", "Expected a completed script")
    elif name == "missing":
        require(report["status"] == "needs_input", "Expected a clarification")
        require(report["missing_fields"] == ["platform"], "Wrong missing field")
        require(not runtime and not records, "Missing input must stop before model")
    elif name in {"no-materials", "unsupported-claim"}:
        require(
            report["status"] in {"needs_input", "incomplete"},
            "Unsupported request must not be delivered",
        )
        if report["status"] == "needs_input":
            require(bool(report["question"]), "Clarification must include a question")
        else:
            require(
                report["reason"] in {"no_materials", "insufficient_information"},
                "Expected an evidence-related stop reason",
            )
    elif name == "unrepairable":
        require(
            (report["status"], report["reason"])
            == ("incomplete", "cannot_meet_constraints"),
            "Impossible duration must be explicit",
        )
    elif name == "persistent-failure":
        require(
            (report["status"], report["reason"]) == ("incomplete", "tool_failure"),
            "Persistent failure must stop explicitly",
        )
    if name in {"tool-failure", "persistent-failure"}:
        require(
            bool(records) and records[0].get("error") == "simulated_tool_failure",
            "Expected the injected tool failure to be observed",
        )
        require(bool(report.get("evaluation")), "Fault injection must be disclosed")
        if name == "tool-failure":
            require(
                any(
                    r["tool"] == "search_materials" and r["status"] == "returned"
                    for r in records[1:]
                ),
                "Expected recovery after a failed search",
            )
    if report["status"] != "completed":
        require(report["script"] is None, "Unfinished run must not deliver a script")
        return failures

    script = report["script"]
    if not isinstance(script, dict):
        return [*failures, "Missing completed script"]
    key = script["draft_id"]
    drafts = {d["draft_id"]: d["script"] for d in report["drafts"]}
    if key not in drafts:
        return [*failures, "Final draft has no stored candidate"]
    draft = drafts[key]
    require(draft_id(draft) == key, "Final content hash does not match")
    retrieved = {
        fact["fact_id"]
        for r in records
        if r["tool"] == "search_materials" and r["status"] == "returned"
        for item in r["result"]["materials"]
        for fact in item["facts"]
    }
    duration = estimate_duration(
        draft, request["duration_seconds"], catalog.policy["timing"]
    )
    rules = check_rules(draft, catalog, request["product_id"], retrieved)
    require(duration["passed"] and rules["passed"], "Recomputed checks failed")
    require(
        script["checks"] == {"duration": duration, "rules": rules}, "Check mismatch"
    )
    require(
        script["estimated_total_seconds"] == duration["estimated_total_seconds"]
        and script["target_duration_seconds"] == request["duration_seconds"],
        "Final duration mismatch",
    )
    for tool in ("estimate_duration", "check_rules"):
        require(
            any(
                r["tool"] == tool
                and r.get("result", {}).get("draft_id") == key
                and r["result"]["passed"]
                for r in records
            ),
            f"Missing successful {tool} receipt for the delivered draft",
        )
    require(
        {f["fact_id"]: f for source in script["sources"] for f in source["facts"]}
        == {f["fact_id"]: f for f in rules["citations"]},
        "Source facts do not match checked citations",
    )
    require(len(script["scenes"]) == len(draft["scenes"]), "Scene count mismatch")
    for scene, candidate, timing in zip(
        script["scenes"], draft["scenes"], duration["scenes"], strict=False
    ):
        require(
            all(
                scene[field] == candidate[field]
                for field in ("id", "narration", "subtitle", "hold_seconds", "fact_ids")
            )
            and scene["estimated_seconds"] == timing["estimated_seconds"]
            and scene["source_ids"]
            == sorted(
                {
                    catalog.facts[f]["source_id"]
                    for f in candidate["fact_ids"]
                    if f in catalog.facts
                }
            ),
            "Delivered scene differs from its checked candidate",
        )
    return failures


def source_version() -> dict:
    paths = [
        *ROOT.joinpath("src").rglob("*.py"),
        ROOT / "scripts/live_acceptance.py",
        ROOT / "pyproject.toml",
        ROOT / "uv.lock",
    ]
    return {
        "base_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "files_sha256": {
            str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(paths)
        },
        "note": "Hashes identify executed files, including changes after base_commit.",
    }


def write_json(path: Path, value: dict) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--case", action="append", choices=CASES)
    args = parser.parse_args(argv)
    config = ModelConfig.from_env()
    # A fresh directory keeps failed attempts and prior evidence intact.
    args.output_dir.mkdir(parents=True, exist_ok=False)
    manifest = {
        "started_at": datetime.now(UTC).isoformat(),
        "source_version": source_version(),
        "model_settings": {**config.public_settings(), "output_format": "json_object"},
        "cases": [],
    }
    for name in dict.fromkeys(args.case or CASES):
        request, materials, policy, injected = scenario(name)
        inputs = {
            "request": request,
            "materials": materials,
            "policy": policy,
            "injected_tool_failures": injected,
        }
        write_json(args.output_dir / f"{name}.input.json", inputs)
        started = datetime.now(UTC).isoformat()
        report = run_script(
            deepcopy(request),
            config=config,
            catalog=Catalog(materials, policy),
            evaluation_failures=injected or None,
        )
        write_json(args.output_dir / f"{name}.output.json", report)
        failures = assess(name, report, request, Catalog(materials, policy))
        item = {
            "case": name,
            "started_at": started,
            "finished_at": datetime.now(UTC).isoformat(),
            "status": report["status"],
            "reason": report["reason"],
            "passed": not failures,
            "failures": failures,
        }
        manifest["cases"].append(item)
        write_json(args.output_dir / "manifest.json", manifest)
        print(json.dumps(item, ensure_ascii=False), flush=True)
    return int(any(not item["passed"] for item in manifest["cases"]))


if __name__ == "__main__":
    raise SystemExit(main())
