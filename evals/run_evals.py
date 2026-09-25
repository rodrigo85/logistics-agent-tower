"""
LLM evaluation harness for the Dispatcher Copilot.

Runs every case in `evals/cases.jsonl` against one or more providers and scores:

* tool accuracy   - the expected tool(s) were called;
* entity accuracy - the tool resolved the expected customer / window / status;
* replan          - the plan was recomputed exactly when it should;
* latency         - wall-clock seconds per case.

Each case runs on a fresh temporary database (the canonical 40-order seed) so
mutations never leak between cases or into your local data.

Usage:
    python evals/run_evals.py --provider ollama
    python evals/run_evals.py --provider ollama --model llama3.2:3b --provider gemini
    python evals/run_evals.py --cases evals/cases.jsonl --out evals/results
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# The engine is created at import time: point it at a throw-away database first.
_TMP = Path(tempfile.mkdtemp(prefix="logistics-tower-evals-"))
os.environ["DATABASE_URL"] = f"sqlite:///{(_TMP / 'evals.db').as_posix()}"
os.environ.setdefault("GOOGLE_MAPS_API_KEY", "")  # keep routing deterministic and offline

from logistics_tower.agents.copilot import Copilot  # noqa: E402
from logistics_tower.config import settings  # noqa: E402
from logistics_tower.db.repository import get_repository  # noqa: E402
from logistics_tower.db.seed import seed_database  # noqa: E402
from logistics_tower.llm.provider import LLMNotConfiguredError, get_chat_model  # noqa: E402
from logistics_tower.mcp.tools import tool_skip_customer_today  # noqa: E402
from logistics_tower.services.dispatch_service import get_dispatch_planner  # noqa: E402

ROOT = Path(__file__).resolve().parent


def load_cases(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def score_case(case: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    tools = [a["tool"] for a in result["actions"]]
    expected = case["expected_tools"]
    tool_ok = any(t in tools for t in expected) if case.get("any_of_tools") else all(t in tools for t in expected)

    entity_ok = True
    relevant = [a["result"] for a in result["actions"] if a["tool"] in expected and isinstance(a["result"], dict)]
    if case.get("expect_customer"):
        entity_ok = any(case["expect_customer"].lower() in str(r.get("customer", "")).lower() for r in relevant)
    if case.get("expect_window"):
        entity_ok = entity_ok and any(r.get("window") == case["expect_window"] for r in relevant)
    if case.get("expect_status"):
        accepted = case["expect_status"] if isinstance(case["expect_status"], list) else [case["expect_status"]]
        entity_ok = entity_ok and any(r.get("status") in accepted for r in relevant)

    replan_ok = result["replanned"] == bool(case.get("expect_replan"))
    return {
        "tool_ok": tool_ok,
        "entity_ok": entity_ok,
        "replan_ok": replan_ok,
        "passed": tool_ok and entity_ok and replan_ok,
        "tools_called": tools,
    }


def run_provider(provider: str, model_name: str | None, cases: list[dict[str, Any]]) -> dict[str, Any]:
    if model_name and provider == "ollama":
        settings.ollama_model = model_name  # type: ignore[misc]
    elif model_name and provider == "gemini":
        settings.gemini_model = model_name  # type: ignore[misc]
    elif model_name and provider == "openai":
        settings.openai_model = model_name  # type: ignore[misc]
    get_chat_model.cache_clear()
    settings.llm_provider = provider  # type: ignore[assignment]

    model = get_chat_model(provider)
    label = f"{provider}/{getattr(model, 'model', getattr(model, 'model_name', model_name or '?'))}"
    rows: list[dict[str, Any]] = []
    for case in cases:
        seed_database(force_reseed=True)
        get_dispatch_planner().latest.clear()
        get_dispatch_planner().plan(settings.default_cd_id, auto_approve=True)  # questions need a plan to talk about
        if case.get("setup_skip"):
            tool_skip_customer_today(case["setup_skip"], "setup")
        copilot = Copilot(model=model)
        started = time.perf_counter()
        try:
            result = copilot.chat(case["message"], thread_id=f"eval-{case['id']}")
            error = ""
        except Exception as exc:
            result = {"actions": [], "replanned": False, "reply": ""}
            error = f"{type(exc).__name__}: {exc}"[:200]
        latency = round(time.perf_counter() - started, 1)
        scored = score_case(case, result)
        rows.append(
            {
                **scored,
                "id": case["id"],
                "category": case["category"],
                "latency_s": latency,
                "error": error,
                "reply": result.get("reply", "")[:300],
                "tool_results": [
                    {
                        "tool": a["tool"],
                        "result": {k: v for k, v in a["result"].items() if k != "routes"}
                        if isinstance(a["result"], dict)
                        else a["result"],
                    }
                    for a in result["actions"]
                ][:6],
            }
        )
        mark = "PASS" if scored["passed"] else "FAIL"
        print(f"[{label}] {case['id']:18} {mark}  {latency:5.1f}s  tools={scored['tools_called']} {error}")

    passed = sum(r["passed"] for r in rows)
    return {
        "label": label,
        "provider": provider,
        "cases": len(rows),
        "passed": passed,
        "accuracy": round(passed / len(rows), 3) if rows else 0.0,
        "tool_accuracy": round(sum(r["tool_ok"] for r in rows) / len(rows), 3) if rows else 0.0,
        "entity_accuracy": round(sum(r["entity_ok"] for r in rows) / len(rows), 3) if rows else 0.0,
        "replan_accuracy": round(sum(r["replan_ok"] for r in rows) / len(rows), 3) if rows else 0.0,
        "avg_latency_s": round(sum(r["latency_s"] for r in rows) / len(rows), 1) if rows else 0.0,
        "rows": rows,
    }


def to_markdown(reports: list[dict[str, Any]], repo_customers: int) -> str:
    lines = [
        f"# Copilot evaluation - {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        f"Cases: {reports[0]['cases'] if reports else 0} · customers in pool: {repo_customers} · routing: haversine (offline)",
        "",
        "| Provider / model | Pass | Tool acc. | Entity acc. | Replan acc. | Avg latency |",
        "|---|---|---|---|---|---|",
    ]
    lines.extend(
        f"| {r['label']} | {r['passed']}/{r['cases']} ({r['accuracy']:.0%}) | {r['tool_accuracy']:.0%} | "
        f"{r['entity_accuracy']:.0%} | {r['replan_accuracy']:.0%} | {r['avg_latency_s']} s |"
        for r in reports
    )
    for r in reports:
        lines += [
            "",
            f"## {r['label']}",
            "",
            "| Case | Result | Tools called | Latency | Error |",
            "|---|---|---|---|---|",
        ]
        for row in r["rows"]:
            lines.append(
                f"| {row['id']} | {'PASS' if row['passed'] else 'FAIL'} | {', '.join(row['tools_called']) or '-'} | "
                f"{row['latency_s']} s | {row['error'] or '-'} |"
            )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--provider", action="append", default=[], help="ollama | gemini | openai (repeatable)")
    parser.add_argument("--model", action="append", default=[], help="model override, positional to --provider")
    parser.add_argument("--cases", default=str(ROOT / "cases.jsonl"))
    parser.add_argument("--out", default=str(ROOT / "results"))
    parser.add_argument("--only", action="append", default=[], help="run only these case ids (repeatable)")
    args = parser.parse_args()

    providers = args.provider or [settings.llm_provider]
    cases = load_cases(Path(args.cases))
    if args.only:
        cases = [c for c in cases if c["id"] in set(args.only)]
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    reports = []
    for idx, provider in enumerate(providers):
        model_name = args.model[idx] if idx < len(args.model) else None
        try:
            reports.append(run_provider(provider, model_name, cases))
        except LLMNotConfiguredError as exc:
            print(f"[{provider}] skipped: {exc}", file=sys.stderr)

    if not reports:
        print("No provider could be evaluated.", file=sys.stderr)
        return 1

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    (out_dir / f"{stamp}.json").write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8")
    md = to_markdown(reports, len(get_repository().find_customers("a", limit=100)))
    (out_dir / f"{stamp}.md").write_text(md, encoding="utf-8")
    print("\n" + md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
