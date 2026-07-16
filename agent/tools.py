"""Tool functions for the flight-booking agent.

Plain Python functions calling the mock inventory service; the Foundry agent
invokes them via function calling and we execute them locally.
"""

import json
import os

import httpx

BASE_URL = os.getenv("INVENTORY_BASE_URL", "http://localhost:8787")


def search_flights(origin: str, dest: str, date: str) -> str:
    """Search available flights.

    :param origin: IATA airport code of the origin, e.g. MEL.
    :param dest: IATA airport code of the destination, e.g. SYD.
    :param date: Travel date in YYYY-MM-DD format.
    :return: JSON string with a list of flights (id, airline, time, price, seats).
    """
    try:
        r = httpx.get(f"{BASE_URL}/flights", params={"origin": origin, "dest": dest, "date": date}, timeout=10)
        if r.status_code != 200:
            return json.dumps({"tool_error": f"inventory service returned HTTP {r.status_code}", "body": r.text[:200]})
        return r.text
    except httpx.HTTPError as e:
        return json.dumps({"tool_error": f"inventory service unreachable: {e}"})


def book_flight(flight_id: str, passenger: str) -> str:
    """Book a specific flight for a passenger.

    :param flight_id: The flight_id returned by search_flights.
    :param passenger: Full name of the passenger.
    :return: JSON string with booking status and confirmation code.
    """
    try:
        r = httpx.post(f"{BASE_URL}/book", json={"flight_id": flight_id, "passenger": passenger}, timeout=10)
        if r.status_code != 200:
            return json.dumps({"tool_error": f"booking failed with HTTP {r.status_code}", "body": r.text[:200]})
        return r.text
    except httpx.HTTPError as e:
        return json.dumps({"tool_error": f"booking service unreachable: {e}"})
