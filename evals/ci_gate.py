"""CI gate: fail on a statistically significant regression vs baseline.

Reads the comparison insight the ai-agent-evals action just generated in
Foundry (machine-readable), instead of grepping the rendered job summary
(icons/wording are not a stable contract). Effect values come from the
service's own statistical test: Improved / Degraded / Changed / Inconclusive.
"""

import json
import sys

from agent.agent import get_client


def main() -> None:
    project = get_client()
    client = project.get_openai_client()

    if len(sys.argv) > 1:  # pin a specific eval (rehearsal/deck use)
        latest_eval = client.evals.retrieve(sys.argv[1])
    else:
        latest_eval = next(iter(client.evals.list(limit=1)), None)
    if latest_eval is None:
        sys.exit("gate: no evaluation found")
    run_ids = {r.id for r in client.evals.runs.list(eval_id=latest_eval.id)}

    # Find the comparison insight belonging to this eval.
    insight = None
    for ins in project.beta.insights.list():
        d = json.loads(json.dumps(ins.as_dict() if hasattr(ins, "as_dict") else vars(ins), default=str))
        req = d.get("request", {})
        if req.get("evalId") == latest_eval.id or set(req.get("treatmentRunIds", []) or []) & run_ids:
            insight = d
            break
    if insight is None:
        sys.exit(f"gate: no comparison insight found for eval {latest_eval.id}")

    degraded = []
    for comp in insight["result"].get("comparisons", []):
        metric = comp.get("metric") or comp.get("testingCriteria") or comp.get("name", "?")
        for item in comp.get("compareItems", []):
            effect = item.get("treatmentEffect")
            delta = item.get("deltaEstimate")
            p = item.get("pValue")
            print(f"  {metric}: effect={effect} delta={delta:+.3f} p={p:.4f}"
                  if isinstance(delta, float) and isinstance(p, float)
                  else f"  {metric}: effect={effect}")
            if effect == "Degraded":
                degraded.append(metric)

    if degraded:
        print(f"::error::Eval gate FAILED - statistically significant regression in: {', '.join(degraded)}")
        sys.exit(1)
    print("Eval gate passed: no statistically significant regression.")


if __name__ == "__main__":
    main()
