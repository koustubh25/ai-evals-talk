"""Local eval baseline (Phase 3): run the agent over dataset-v1 and score it.

Usage:  uv run python -m evals.run_local [path-to-dataset.jsonl]

Evaluators: Task Adherence (GA) + Tool Output Utilization (experimental in the
SDK, falls back to Tool Call Accuracy if unavailable). The judge is our own
gpt-5-mini deployment. This is the same pair the CI gate uses in Phase 4 —
run here first so we know the baseline scores are sane before wiring thresholds.
"""

import json
import os
import statistics
import subprocess
import sys
import time

from azure.ai.evaluation import AzureOpenAIModelConfiguration, TaskAdherenceEvaluator, ToolCallAccuracyEvaluator
from dotenv import load_dotenv

from agent.agent import eval_tool_definitions, get_client, publish_agent, run_conversation

load_dotenv()


def judge_config() -> AzureOpenAIModelConfiguration:
    key = subprocess.run(
        ["az", "cognitiveservices", "account", "keys", "list",
         "-g", os.environ["AZURE_RESOURCE_GROUP"], "-n", os.environ["FOUNDRY_ACCOUNT"],
         "--query", "key1", "-o", "tsv"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return AzureOpenAIModelConfiguration(
        azure_endpoint=f"https://{os.environ['FOUNDRY_ACCOUNT']}.cognitiveservices.azure.com/",
        api_key=key,
        azure_deployment=os.environ["MODEL_DEPLOYMENT"],
        api_version="2024-10-21",
    )


def tool_definitions_for_eval() -> list[dict]:
    return eval_tool_definitions()


def to_agent_messages(query: str, out: dict) -> tuple[list, list]:
    """Convert a run into the agent message protocol the evaluators parse."""
    from agent.agent import INSTRUCTIONS

    eval_query = [
        {"role": "system", "content": INSTRUCTIONS},
        {"role": "user", "content": [{"type": "text", "text": query}]},
    ]
    eval_response: list[dict] = []
    for c in out["tool_calls"]:
        eval_response.append(
            {"role": "assistant", "content": [
                {"type": "tool_call", "tool_call_id": c["tool_call_id"], "name": c["name"],
                 "arguments": c["arguments"]}]}
        )
        eval_response.append(
            {"role": "tool", "tool_call_id": c["tool_call_id"],
             "content": [{"type": "tool_result", "tool_result": c["tool_result"]}]}
        )
    eval_response.append({"role": "assistant", "content": [{"type": "text", "text": out["response"]}]})
    return eval_query, eval_response


def main() -> None:
    dataset_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "dataset-v1.jsonl")
    rows = [json.loads(line) for line in open(dataset_path) if line.strip()]

    project = get_client()
    version = publish_agent(project)
    print(f"agent: {version.name} v{version.version} | dataset: {os.path.basename(dataset_path)} ({len(rows)} rows)")

    # A freshly published version takes a few seconds to propagate; until then
    # requests can hit a stale config with NO TOOLS. Warm up before measuring.
    for attempt in range(6):
        canary = run_conversation(project, "Find a flight MEL to BNE on 2026-08-10",
                                  agent_version=version.version, details=True)
        if canary["tool_calls"]:
            print(f"warm-up ok (attempt {attempt + 1})\n")
            break
        time.sleep(10)
    else:
        sys.exit("agent version never propagated with tools; aborting")

    cfg = judge_config()
    task_adherence = TaskAdherenceEvaluator(model_config=cfg, is_reasoning_model=True)
    try:
        from azure.ai.evaluation import _ToolOutputUtilizationEvaluator

        tool_eval = _ToolOutputUtilizationEvaluator(model_config=cfg, is_reasoning_model=True)
        tool_eval_name = "tool_output_utilization"
    except ImportError:
        tool_eval = ToolCallAccuracyEvaluator(model_config=cfg, is_reasoning_model=True)
        tool_eval_name = "tool_call_accuracy"

    tool_defs = tool_definitions_for_eval()
    results = []
    for row in rows:
        out = run_conversation(project, row["query"], agent_version=version.version, details=True)
        eval_query, eval_response = to_agent_messages(row["query"], out)
        scores = {}
        ta = task_adherence(query=eval_query, response=eval_response, tool_definitions=tool_defs)
        scores["task_adherence"] = ta.get("task_adherence")
        try:
            tu = tool_eval(query=eval_query, response=eval_response, tool_definitions=tool_defs)
            scores[tool_eval_name] = next((v for k, v in tu.items() if not k.startswith("_") and isinstance(v, (int, float))), None)
        except Exception as e:  # some rows legitimately have no tool calls
            scores[tool_eval_name] = None
            scores[f"{tool_eval_name}_note"] = str(e)[:80]
        results.append({"id": row["id"], "tools_used": [c["name"] for c in out["tool_calls"]], **scores,
                        "response_preview": out["response"][:100].replace("\n", " ")})
        print(f"  {row['id']:26s} task_adherence={scores['task_adherence']} {tool_eval_name}={scores[tool_eval_name]} tools={[c['name'] for c in out['tool_calls']]}")

    ta_scores = [r["task_adherence"] for r in results if isinstance(r.get("task_adherence"), (int, float))]
    tu_scores = [r[tool_eval_name] for r in results if isinstance(r.get(tool_eval_name), (int, float))]
    print(f"\nBASELINE  task_adherence: mean={statistics.mean(ta_scores):.2f} min={min(ta_scores)}"
          f" | {tool_eval_name}: mean={statistics.mean(tu_scores):.2f} min={min(tu_scores)}" if tu_scores else "")

    out_path = os.path.join(os.path.dirname(__file__), "baseline-results.json")
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"full results -> {out_path}")


if __name__ == "__main__":
    main()
