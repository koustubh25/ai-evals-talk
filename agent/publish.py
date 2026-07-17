"""Publish the agent definition from this checkout and print its name:version.

Used by CI: the PR's code becomes a new (immutable) agent version, which the
eval gate then compares against the baseline version. Warm-up matters — fresh
versions take seconds to propagate; measuring before that hits a config with
no tools and produces garbage scores.
"""

import os
import sys
import time

from .agent import get_client, publish_agent, run_conversation


def main() -> None:
    project = get_client()
    version = publish_agent(project)
    ref = f"{version.name}:{version.version}"

    # Propagation check only: a stale config returns EMPTY output. Whether the
    # agent uses tools correctly is the eval gate's judgment, not ours — a
    # candidate that skips tools must fail the GATE, not the publish step.
    for attempt in range(8):
        canary = run_conversation(
            project, "Find a flight MEL to BNE on 2026-08-10",
            agent_version=version.version, details=True,
        )
        if canary["response"]:
            print(f"published {ref} (responsive after attempt {attempt + 1})")
            break
        time.sleep(10)
    else:
        sys.exit(f"{ref} never propagated")

    if os.getenv("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"agent_ref={ref}\n")


if __name__ == "__main__":
    main()
