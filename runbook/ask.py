"""STAGE SCRIPT — one live conversation with the production agent (no publish).

Usage: uv run python -m runbook.ask "Book the cheapest MEL to BNE flight ..."
"""

import sys

from agent.agent import get_client, run_conversation

query = " ".join(sys.argv[1:]) or "Book the cheapest flight from MEL to BNE on 2026-08-10 for passenger Alex Chen"
print(f"\033[1;36mCUSTOMER:\033[0m {query}", flush=True)
out = run_conversation(get_client(), query, details=True)
tools = [c["name"].split("_", 2)[-1] for c in out["tool_calls"]]
print(f"\033[33m  ⚙ tools used: {', '.join(dict.fromkeys(tools)) or 'none'}\033[0m", flush=True)
print(f"\033[1;32mAGENT:\033[0m {out['response']}")
