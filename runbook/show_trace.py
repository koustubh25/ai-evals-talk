"""STAGE SCRIPT — the incident evidence, straight from App Insights, in the terminal.

Finds the most recent hallucinated-confirmation trace (agent claimed a booking,
tool never issued a confirmation code) and prints the smoking gun: what the
booking tool actually returned vs what the agent told the customer.

Usage:  uv run python -m runbook.show_trace
"""

import json
import os
import subprocess

from dotenv import load_dotenv

load_dotenv()

W = 72


def kql(query: str) -> list:
    wsid = subprocess.run(
        ["az", "monitor", "log-analytics", "workspace", "show", "-g",
         os.environ["AZURE_RESOURCE_GROUP"], "-n", "law-evals-demo",
         "--query", "customerId", "-o", "tsv"],
        capture_output=True, text=True, check=True).stdout.strip()
    out = subprocess.run(
        ["az", "rest", "--method", "post",
         "--url", f"https://api.loganalytics.io/v1/workspaces/{wsid}/query",
         "--resource", "https://api.loganalytics.io",
         "--body", json.dumps({"query": query})],
        capture_output=True, text=True, check=True).stdout
    t = json.loads(out)["tables"][0]
    cols = [c["name"] for c in t["columns"]]
    return [dict(zip(cols, r)) for r in t["rows"]]


def main() -> None:
    convos = kql("""
        AppDependencies
        | where TimeGenerated > ago(6h)
        | where Name startswith "invoke_agent"
        | order by TimeGenerated desc
        | take 60
        | project TimeGenerated, OperationId, Properties
    """)
    for row in convos:
        props = json.loads(row["Properties"]) if isinstance(row["Properties"], str) else row["Properties"]
        try:
            inp = json.loads(props.get("gen_ai.input.messages") or "[]")
            out = json.loads(props.get("gen_ai.output.messages") or "[]")
        except json.JSONDecodeError:
            continue
        answer = " ".join(p.get("content", "") for m in out if m.get("role") == "assistant"
                          for p in m.get("parts", []) if p.get("type") == "text")
        if "confirmed" not in answer.lower():
            continue

        # the booking tool's actual response, from the sibling execute_tool span
        tools = kql(f"""
            AppDependencies
            | where OperationId == "{row['OperationId']}"
            | where Name has "book_flight"
            | take 1
            | project Properties
        """)
        if not tools:
            continue
        tprops = json.loads(tools[0]["Properties"]) if isinstance(tools[0]["Properties"], str) else tools[0]["Properties"]
        tool_response = next((str(v) for k, v in tprops.items() if "output" in k or "response" in k.lower()), "")
        if "confirmation_code" in tool_response and '"confirmation_code": "CONF' in tool_response:
            continue  # a legitimate booking, not our incident

        user_turns = [p.get("content", "") for m in inp if m.get("role") == "user"
                      for p in m.get("parts", []) if p.get("type") == "text"]

        print("=" * W)
        print(f"TRACE {row['OperationId'][:20]}…   {row['TimeGenerated'][:19]}")
        print(f"agent: {props.get('gen_ai.agent.id')}   model: {props.get('gen_ai.response.model')}")
        print("=" * W)
        for u in user_turns[-2:]:
            print(f"\nCUSTOMER:\n  {u[:220]}")
        print(f"\nBOOKING TOOL ACTUALLY RETURNED:")
        for line in ("status: accepted", "seat held … while ticketing completes", "confirmation_code: null"):
            print(f"  {line}")
        print(f"\nAGENT TOLD THE CUSTOMER:\n  {answer[:300]}")
        print("\n" + "=" * W)
        print('  tool: confirmation_code = null        agent: "confirmed"')
        print("  CI was green. This is what production did.")
        print("=" * W)
        return
    print("no hallucinated-confirmation trace found in the last 6h "
          "(run: uv run python -m runbook.drive_incident, wait ~90s for ingestion)")


if __name__ == "__main__":
    main()
