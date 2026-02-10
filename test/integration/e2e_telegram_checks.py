from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(PROJECT_ROOT / "config" / ".env")


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _now_local_with_tz() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M") + "+00:00"


async def adapter_send_test() -> dict[str, Any]:
    from socials.message_builder import build_message_context
    import socials.telegram as tg

    flight_data = {
        "flight_name": "E2EADAPTER",
        "flight_name_iata": "E2A001",
        "registration": "EC-E2A",
        "aircraft_name": "Airbus A320",
        "aircraft_icao": "A320",
        "airline": "TST",
        "airline_name": "Integration Test Airline",
        "origin_icao": "LEBL",
        "origin_name": "Barcelona",
        "destination_icao": "LEMD",
        "destination_name": "Madrid",
        "terminal": "T4",
        "scheduled_time": _now_str(),
        "last_update": _now_str(),
        "diverted": False,
    }

    context = build_message_context(flight_data, interesting={"E2E_ADAPTER": True})
    await tg.send_message(context, image_path=None)

    return {
        "phase": "adapter",
        "status": "ok",
        "flight_name": flight_data["flight_name_iata"],
    }


class FakeProvider:
    async def get_registrations_index(self, airport_icao: str):
        return {}

    async def get_interesting_registrations_index(self, airport_icao: str):
        return {}

    async def get_interesting_models_index(self, airport_icao: str):
        return {}

    async def upsert_registration_sighting(self, flight_data, airport_icao: str):
        return ({"id": "mock-reg", "registration": flight_data.get("registration")}, True)

    async def record_flight_history(self, flight_data, airport_icao: str):
        return {"id": "mock-history"}


async def pipeline_e2e_mock_test() -> dict[str, Any]:
    import main as app_main

    orig_get_config = app_main.cfg.get_config
    orig_aero = app_main.api_handler_aeroapi.fetch_aeroapi_scheduled
    orig_adb = app_main.api_handler_aerodatabox.fetch_adb_data
    orig_provider = app_main.get_database_provider
    orig_jp = app_main.sp.get_first_image_url_jp
    orig_pp = app_main.sp.get_first_image_url_pp
    orig_usage_snapshot = app_main.get_aeroapi_usage_snapshot

    def patched_get_config(key: str):
        if key == "api.preloaded_data":
            return False
        if key == "api.time_range_hours":
            return 1
        if key == "social_networks":
            return {
                "telegram": True,
                "bluesky": False,
                "twitter": False,
                "threads": False,
                "instagram": False,
                "linkedin": False,
            }
        if key.startswith("social_networks."):
            return key == "social_networks.telegram"
        return orig_get_config(key)

    async def mock_fetch_aero(move, start_time, end_time, airport_icao="LEMD"):
        return {f"scheduled_{move}": []}

    async def mock_fetch_adb(move, start_time, end_time, airport_icao="LEMD"):
        if move == "arrivals":
            return {
                "arrivals": [
                    {
                        "aircraft": {"reg": "EC-E2E", "model": "Airbus A320-232"},
                        "callSign": "E2E9001",
                        "number": "E29001",
                        "airline": {"icao": "IBE", "name": "Iberia"},
                        "departure": {"airport": {"icao": "LEBL", "name": "Barcelona"}},
                        "arrival": {
                            "airport": {"icao": "LEMD", "name": "Madrid"},
                            "terminal": "T4",
                            "revisedTime": {"local": _now_local_with_tz()},
                        },
                    }
                ],
                "departures": [],
            }

        return {"arrivals": [], "departures": []}

    async def mock_usage_snapshot(force_refresh=False):
        return [{"alias": "mock-key", "key_mask": "mock...key", "total_cost_usd": 0.0, "total_calls": 0}]

    try:
        app_main.cfg.get_config = patched_get_config
        app_main.api_handler_aeroapi.fetch_aeroapi_scheduled = mock_fetch_aero
        app_main.api_handler_aerodatabox.fetch_adb_data = mock_fetch_adb
        app_main.get_database_provider = lambda: FakeProvider()
        app_main.sp.get_first_image_url_jp = lambda reg: None
        app_main.sp.get_first_image_url_pp = lambda reg: None
        app_main.get_aeroapi_usage_snapshot = mock_usage_snapshot

        await app_main.main({})
    finally:
        app_main.cfg.get_config = orig_get_config
        app_main.api_handler_aeroapi.fetch_aeroapi_scheduled = orig_aero
        app_main.api_handler_aerodatabox.fetch_adb_data = orig_adb
        app_main.get_database_provider = orig_provider
        app_main.sp.get_first_image_url_jp = orig_jp
        app_main.sp.get_first_image_url_pp = orig_pp
        app_main.get_aeroapi_usage_snapshot = orig_usage_snapshot

    return {
        "phase": "pipeline",
        "status": "ok",
        "flight_name": "E29001",
    }


async def _run_with_timeout(coro, timeout_seconds: int):
    return await asyncio.wait_for(coro, timeout=timeout_seconds)


async def run(phase: str, timeout_seconds: int):
    results: list[dict[str, Any]] = []

    if phase in ("adapter", "all"):
        results.append(await _run_with_timeout(adapter_send_test(), timeout_seconds))

    if phase in ("pipeline", "all"):
        results.append(await _run_with_timeout(pipeline_e2e_mock_test(), timeout_seconds))

    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="E2E Telegram checks for Plane Spotter")
    parser.add_argument(
        "--phase",
        choices=["adapter", "pipeline", "all"],
        default="all",
        help="Which phase to run",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="Timeout in seconds per phase",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        results = asyncio.run(run(args.phase, args.timeout))
        print(json.dumps({"ok": True, "results": results}, ensure_ascii=True, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=True, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
