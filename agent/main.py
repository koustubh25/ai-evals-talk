"""CLI: uv run python -m agent.main "Find me a flight MEL to SYD on 2026-12-24"."""

import sys

from .agent import get_client, publish_agent, run_conversation, setup_tracing


def main() -> None:
    query = " ".join(sys.argv[1:]) or "Find me a flight from MEL to BNE on 2026-08-10"
    project = get_client()
    setup_tracing(project)
    version = publish_agent(project)
    print(f"[{version.name} v{version.version}] user: {query}\n")
    print(run_conversation(project, query, agent_version=version.version))


if __name__ == "__main__":
    main()
