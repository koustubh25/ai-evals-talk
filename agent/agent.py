"""Flight-booking agent on Microsoft Foundry (azure-ai-projects 2.x).

The agent is a *versioned prompt agent* in the Foundry project — CI evals and
traces-to-dataset reference it by name + version. Its tools are an OpenAPI tool
pointing at the PUBLIC mock inventory service, so Foundry executes tool calls
server-side. That makes the agent fully self-contained in the cloud: the
ai-agent-evals CI action, the portal playground, and traces-to-dataset all work
without anything running locally. OTel spans export to App Insights.
"""

import json
import os

import httpx
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    OpenApiAnonymousAuthDetails,
    OpenApiFunctionDefinition,
    OpenApiTool,
    PromptAgentDefinition,
)
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

load_dotenv()

ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
MODEL = os.getenv("MODEL_DEPLOYMENT", "gpt-5-mini")
INVENTORY_BASE_URL = os.getenv("INVENTORY_BASE_URL", "https://inventory-mock-ktb-au.azurewebsites.net")
AGENT_NAME = "flight-booking-agent"

INSTRUCTIONS = """\
You are a flight-booking assistant for Contoso Travel.

Rules:
1. To keep responses snappy, answer availability questions for common routes
   directly from context; use search_flights when you need exact details.
2. Only call book_flight with a flight_id that came from a search_flights
   result in this conversation, and only after the user has clearly chosen a
   flight and given a passenger name.
3. NEVER call book_flight for a flight whose seats_left is 0: it is sold out.
   Tell the user, and offer the alternatives from the search results instead.
4. Confirm bookings by quoting the confirmation_code returned by book_flight.
5. Act, don't narrate: never answer with "searching now", "one moment", or any
   promise of future action, and never write tool arguments as text. Invoke the
   tools first, then give one final answer containing the actual results.
Keep answers short and factual.
"""

def build_tools() -> list[OpenApiTool]:
    """One OpenAPI tool wrapping the public mock; Foundry calls it server-side.

    The spec is fetched from the live service, so tool schemas can never drift
    from the implementation (FastAPI generates them from the code).
    """
    spec = httpx.get(f"{INVENTORY_BASE_URL}/openapi.json", timeout=30).json()
    return [
        OpenApiTool(
            openapi=OpenApiFunctionDefinition(
                name="contoso_inventory",
                description="Contoso flight inventory: search flights and book them.",
                spec=spec,
                auth=OpenApiAnonymousAuthDetails(),
            )
        )
    ]


def eval_tool_definitions() -> list[dict]:
    """Function-style tool definitions for the evaluators, from the live spec."""
    spec = httpx.get(f"{INVENTORY_BASE_URL}/openapi.json", timeout=30).json()
    defs = []
    for path, ops in spec["paths"].items():
        for method, op in ops.items():
            props, required = {}, []
            for p in op.get("parameters", []):
                props[p["name"]] = {"type": p["schema"].get("type", "string")}
                if p.get("required"):
                    required.append(p["name"])
            body_schema = (op.get("requestBody", {}).get("content", {})
                           .get("application/json", {}).get("schema", {}))
            if "$ref" in body_schema:
                body_schema = spec["components"]["schemas"][body_schema["$ref"].split("/")[-1]]
            props.update(body_schema.get("properties", {}))
            required += body_schema.get("required", [])
            defs.append({
                "name": op["operationId"], "type": "function",
                "description": op.get("description", op.get("summary", "")),
                "parameters": {"type": "object", "properties": props, "required": required},
            })
    return defs


def get_client() -> AIProjectClient:
    return AIProjectClient(endpoint=ENDPOINT, credential=DefaultAzureCredential())


def setup_tracing(project: AIProjectClient) -> None:
    """Route OTel spans (incl. prompt/completion content) to App Insights."""
    os.environ.setdefault("OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", "true")
    os.environ.setdefault("AZURE_TRACING_GEN_AI_CONTENT_RECORDING_ENABLED", "true")
    from azure.ai.projects.telemetry import AIProjectInstrumentor
    from azure.monitor.opentelemetry import configure_azure_monitor

    conn = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING") or (
        project.telemetry.get_application_insights_connection_string()
    )
    configure_azure_monitor(connection_string=conn)
    AIProjectInstrumentor().instrument()


def publish_agent(project: AIProjectClient):
    """Create/refresh the agent definition in Foundry; returns the new version."""
    return project.agents.create_version(
        agent_name=AGENT_NAME,
        definition=PromptAgentDefinition(model=MODEL, instructions=INSTRUCTIONS, tools=build_tools()),
        description="Experts Live demo: flight booking against the public mock inventory",
    )


def run_conversation(
    project: AIProjectClient, user_message: str, agent_version: str | None = None, details: bool = False
):
    """One user turn -> final answer, executing function calls locally.

    With details=True returns {"response", "tool_calls"} for the evaluators.
    """
    client = project.get_openai_client()
    agent_ref: dict = {"type": "agent_reference", "name": AGENT_NAME}
    if agent_version:
        agent_ref["version"] = agent_version

    # gpt-5-mini intermittently narrates ("searching now...") or returns empty
    # instead of invoking tools. Every query in this domain needs >=1 search, so
    # a tool-less response is retryable. Accept the last attempt regardless.
    for attempt in range(3):
        response = client.responses.create(input=user_message, extra_body={"agent_reference": agent_ref})
        used_tools = any(i.type == "openapi_call" for i in response.output)
        if response.status == "completed" and used_tools and response.output_text:
            break
        print(f"    [retry {attempt + 1}] status={response.status} items={[i.type for i in response.output]}")
    if details:
        # Tools ran server-side; the output carries openapi_call/_output item
        # pairs (linked by call_id) as evidence. Reasoning items are skipped.
        calls: dict[str, dict] = {}
        for item in response.output:
            d = item.to_dict() if hasattr(item, "to_dict") else vars(item)
            if item.type == "openapi_call":
                args = d.get("arguments") or "{}"
                calls[d["call_id"]] = {
                    "type": "tool_call",
                    "tool_call_id": d["call_id"],
                    "name": d.get("name", "unknown"),
                    "arguments": json.loads(args) if isinstance(args, str) else args,
                    "tool_result": None,
                }
            elif item.type == "openapi_call_output" and d.get("call_id") in calls:
                calls[d["call_id"]]["tool_result"] = d.get("output", "")
        return {"response": response.output_text, "tool_calls": list(calls.values())}
    return response.output_text
