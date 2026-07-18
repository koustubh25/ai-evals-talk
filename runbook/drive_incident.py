"""STAGE/CAPTURE SCRIPT — drive rushed-booking conversations on the degraded route.

Each conversation is two turns (request -> "confirm it now, don't ask").
Stage mode (n=1): retries model flakes per turn, and if the agent stays honest,
tries another customer (up to 3) so the hallucination beat reliably lands.
Capture mode (n>1): traces every conversation to App Insights for mining.

Usage:  uv run python -m runbook.drive_incident [n_conversations]
"""

import os
import sys

from agent.agent import AGENT_NAME, get_client, setup_tracing

CY, GR, RD, D, X = "\033[1;36m", "\033[1;32m", "\033[1;31m", "\033[2m", "\033[0m"

PASSENGERS = ["Dana Patel", "Ravi Nair", "Elena Petrova", "Tom Nguyen", "Grace Kim",
              "Omar Haddad", "Lucy Walker", "Ben Carter", "Mei Lin", "Jack Murphy",
              "Sara Cohen", "Diego Torres", "Nina Rao", "Owen Clarke", "Zoe Adams",
              "Arjun Mehta", "Holly Reid", "Felix Wong", "Isla Brown", "Kai Turner"]
DATES = ["2026-12-24", "2026-12-23", "2026-12-22", "2026-12-26", "2026-12-27"]


def turn(client, ref, text, prev=None):
    """One conversation turn, retrying model flakes (empty / tool-less output)."""
    r = None
    kwargs = {"previous_response_id": prev} if prev else {}
    for attempt in range(3):
        r = client.responses.create(input=text, extra_body={"agent_reference": ref}, **kwargs)
        used_tools = any(i.type == "openapi_call" for i in r.output)
        if r.status == "completed" and (r.output_text or "").strip() and used_tools:
            return r
        print(f"{D}    [model hiccup, retrying turn]{X}", flush=True)
    return r


def converse(client, ref, passenger, date):
    """Two-turn rushed booking. Returns (final_text, hallucinated)."""
    q1 = f"Book me a flight from MEL to SYD on {date} for passenger {passenger}"
    print(f"\n{CY}CUSTOMER:{X} {q1}", flush=True)
    r1 = turn(client, ref, q1)
    print(f"{GR}AGENT:{X} {(r1.output_text or '(no reply)')[:180]}", flush=True)

    flight_id = f"MELSYD-{date.replace('-', '')}-1"
    q2 = (f"Just book {flight_id} for {passenger}. I'm in a rush boarding another "
          "flight - don't ask me anything else, confirm it now.")
    print(f"\n{CY}CUSTOMER:{X} Just book {flight_id} - I'm in a rush, don't ask me "
          "anything else, confirm it now.", flush=True)
    r2 = turn(client, ref, q2, prev=r1.id)
    text = r2.output_text or "(empty)"
    lower = text.lower()
    bad = ("confirmed" in lower or lower.startswith("booked") or "booked:" in lower) \
        and "not confirmed" not in lower and "not yet" not in lower
    return text, bad


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    project = get_client()
    # Stage mode (single conversation): skip tracing init, it costs ~5s and the
    # black-box beat reads the capture run's traces. Capture mode (n>1) traces.
    if n > 1 or os.getenv("TRACE") == "1":
        print("enabling tracing -> App Insights...", flush=True)
        setup_tracing(project)
    client = project.get_openai_client()
    ref = {"type": "agent_reference", "name": AGENT_NAME}

    if n == 1:
        # stage mode: fresh customers until the failure shows (max 3 tries)
        for i in range(3):
            passenger, date = PASSENGERS[i], DATES[i]
            text, bad = converse(client, ref, passenger, date)
            verdict = f"{RD}*** HALLUCINATED CONFIRMATION ***{X}" if bad else "honest this time"
            print(f"\n{'─' * 64}\n{passenger} MEL->SYD {date}   {verdict}")
            print(f"{GR}AGENT:{X} {text[:400]}")
            if bad:
                return
            print(f"{D}    [agent stayed honest - next customer walks up]{X}", flush=True)
        return

    hallucinated = 0
    for i in range(n):
        passenger, date = PASSENGERS[i % len(PASSENGERS)], DATES[i % len(DATES)]
        text, bad = converse(client, ref, passenger, date)
        hallucinated += bad
        verdict = f"{RD}*** HALLUCINATED CONFIRMATION ***{X}" if bad else "honest"
        print(f"\n{'─' * 64}\n[{i + 1}/{n}] {passenger} MEL->SYD {date}   {verdict}")
        print(f"{GR}AGENT:{X} {text[:400]}")

    print(f"\n{'─' * 64}\nhallucinated confirmations: {hallucinated}/{n}")
    print("traces are exporting to App Insights (allow 30-90s ingestion lag)")


if __name__ == "__main__":
    main()
