"""STAGE SCRIPT — the eval gate's verdict as a scoreboard, live from Foundry.

Shows per-agent pass counts, per-metric results, and the statistical
comparison (effect / delta / p-value) that the gate decides on.

Usage: uv run python -m runbook.verdict [eval_id]   (default: latest eval)
"""

import json
import sys

from agent.agent import get_client

GR, RD, AM, CY, D, X = "\033[1;32m", "\033[1;31m", "\033[1;33m", "\033[1;36m", "\033[2m", "\033[0m"
W = 56


def main() -> None:
    project = get_client()
    client = project.get_openai_client()

    ev = client.evals.retrieve(sys.argv[1]) if len(sys.argv) > 1 else next(iter(client.evals.list(limit=1)))
    runs = list(client.evals.runs.list(eval_id=ev.id))

    # insight (statistical comparison) for this eval
    insight = None
    for ins in project.beta.insights.list():
        d = json.loads(json.dumps(ins.as_dict() if hasattr(ins, "as_dict") else vars(ins), default=str))
        if d.get("request", {}).get("evalId") == ev.id:
            insight = d
            break
    baseline_run = insight["request"]["baselineRunId"] if insight else None

    print(f"{D}eval {ev.id[:18]}…  ·  30 conversations each{X}")
    print(f"{D}{'─' * W}{X}")
    for run in sorted(runs, key=lambda r: r.id != baseline_run):
        role = "baseline " if run.id == baseline_run else "candidate"
        agent = run.name.replace("Agent ", "")
        rc = run.result_counts
        color = GR if run.id == baseline_run else RD
        print(f"{role}  {color}{agent:26s}{X} {rc.passed:2d}/{rc.total} passed")
        for c in run.per_testing_criteria_results or []:
            total = c.passed + c.failed
            print(f"{D}           {c.testing_criteria:24s} {c.passed:2d}/{total}{X}")
    print(f"{D}{'─' * W}{X}")

    degraded = []
    for comp in (insight or {}).get("result", {}).get("comparisons", []):
        metric = comp.get("metric") or comp.get("testingCriteria", "?")
        for item in comp.get("compareItems", []):
            eff, delta, p = item.get("treatmentEffect"), item.get("deltaEstimate"), item.get("pValue")
            color = RD if eff == "Degraded" else (GR if eff == "Improved" else AM)
            if isinstance(delta, float):
                print(f"{metric}: {color}{eff}{X}  Δ {delta:+.3f}  p={p:.4f}")
            else:
                print(f"{metric}: {color}{eff}{X}")
            if eff == "Degraded":
                degraded.append(metric)

    print(f"{D}{'─' * W}{X}")
    if degraded:
        print(f"{RD}GATE: FAIL — statistically significant regression{X}")
        sys.exit(1)
    print(f"{GR}GATE: PASS — no significant regression vs baseline{X}")


if __name__ == "__main__":
    main()
