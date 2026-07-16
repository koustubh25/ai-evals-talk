"""Mock flight inventory service for the evals demo.

Two endpoints the agent's tools call:
  GET  /flights?origin=MEL&dest=SYD&date=2026-12-24   -> search results
  POST /book {"flight_id": "...", "passenger": "..."} -> booking confirmation

Degraded mode (the villain of Act 2): when enabled, requests touching the
DEGRADED_ROUTE return a 503 half-baked JSON error instead of results.
Toggle it live without restarting:
  POST /admin/degrade {"enabled": true}
or start with DEGRADED=1 in the environment.
"""

import os
import random
from datetime import date

from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel

app = FastAPI(
    title="Contoso Flight Inventory (mock)",
    # servers: required for the Foundry OpenAPI tool to know the base URL.
    servers=[{"url": os.getenv("PUBLIC_BASE_URL", "http://localhost:8787")}],
)

DEGRADED_ROUTE = ("MEL", "SYD")
state = {"degraded": os.getenv("DEGRADED", "0") == "1"}

AIRLINES = ["Contoso Air", "Fabrikam Jet", "Tailwind"]

# Deterministic per (route, date) so eval runs are reproducible.
def _flights_for(origin: str, dest: str, day: str) -> list[dict]:
    rng = random.Random(f"{origin}-{dest}-{day}")
    flights = []
    for i in range(rng.randint(2, 4)):
        dep_hour = rng.choice([6, 8, 11, 14, 17, 20])
        flights.append(
            {
                "flight_id": f"{origin}{dest}-{day.replace('-', '')}-{i}",
                "airline": rng.choice(AIRLINES),
                "origin": origin,
                "dest": dest,
                "date": day,
                "departs": f"{dep_hour:02d}:00",
                "price_aud": 89 + rng.randint(0, 40) * 10,
                "seats_left": rng.choice([0, 3, 9, 25]) if i == 0 else rng.choice([3, 9, 25]),
            }
        )
    return flights


class BookRequest(BaseModel):
    flight_id: str
    passenger: str


class DegradeRequest(BaseModel):
    enabled: bool


@app.get("/flights", operation_id="search_flights",
         description="Search available flights for a route and date. Returns flight_id, airline, departure time, price, and seats_left for each option.")
def search_flights(origin: str, dest: str, date: str):
    origin, dest = origin.upper(), dest.upper()
    if state["degraded"] and (origin, dest) == DEGRADED_ROUTE:
        # Truncated/ambiguous payload on purpose: what a flaky upstream looks like.
        return Response(
            content='{"error": "upstream inventory timeout", "partial": true, "flights": [',
            status_code=503,
            media_type="application/json",
        )
    return {"flights": _flights_for(origin, dest, date)}


@app.post("/book", operation_id="book_flight",
          description="Book a specific flight for a passenger. flight_id must come from a search_flights result. Returns a confirmation_code.")
def book_flight(req: BookRequest):
    # flight_id encodes route+date; reject bookings for degraded-route while degraded
    if state["degraded"] and req.flight_id.startswith("".join(DEGRADED_ROUTE)):
        return Response(
            content='{"error": "booking backend unavailable"}',
            status_code=503,
            media_type="application/json",
        )
    if not req.flight_id or "-" not in req.flight_id:
        raise HTTPException(status_code=404, detail="unknown flight_id")
    return {
        "status": "confirmed",
        "confirmation_code": f"CONF-{abs(hash(req.flight_id + req.passenger)) % 10**6:06d}",
        "flight_id": req.flight_id,
        "passenger": req.passenger,
    }


# include_in_schema=False: callable, but invisible in openapi.json — the agent
# must never discover the degrade switch or treat health checks as tools.
@app.post("/admin/degrade", include_in_schema=False)
def set_degraded(req: DegradeRequest):
    state["degraded"] = req.enabled
    return {"degraded": state["degraded"]}


@app.get("/healthz", include_in_schema=False)
def healthz():
    return {"ok": True, "degraded": state["degraded"], "today": str(date.today())}
