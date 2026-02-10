from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping


@dataclass(frozen=True)
class MessageContext:
    flight_data: dict[str, Any]
    text: str
    flight_slug: str
    flight_url: str
    interesting: dict[str, bool]


def _is_nullish(value: Any) -> bool:
    return value in (None, "", "null", "None")


def _value_or_default(value: Any, default: str = "Unknown") -> str:
    if _is_nullish(value):
        return default
    return str(value)


def _resolve_flight_slug(flight_data: Mapping[str, Any]) -> str:
    candidate = flight_data.get("flight_name_iata")
    if _is_nullish(candidate):
        candidate = flight_data.get("flight_name")
    if _is_nullish(candidate):
        return "unknown-flight"
    return str(candidate).replace(" ", "").lower()


def _resolve_flight_label(flight_data: Mapping[str, Any]) -> str:
    iata_name = flight_data.get("flight_name_iata")
    flight_name = flight_data.get("flight_name")

    if not _is_nullish(iata_name) and not _is_nullish(flight_name):
        return f"{iata_name}/{flight_name}"
    if not _is_nullish(iata_name):
        return str(iata_name)
    if not _is_nullish(flight_name):
        return str(flight_name)
    return "Unknown"


def _resolve_aircraft_label(flight_data: Mapping[str, Any]) -> str:
    aircraft_name = flight_data.get("aircraft_name")
    aircraft_icao = flight_data.get("aircraft_icao")
    if not _is_nullish(aircraft_name):
        return str(aircraft_name)
    if not _is_nullish(aircraft_icao):
        return str(aircraft_icao)
    return "Unknown"


def _format_scheduled_time(value: Any) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M")
    return _value_or_default(value)


def _format_interesting_reasons(interesting: Mapping[str, bool]) -> str | None:
    active_reasons = [name for name, enabled in interesting.items() if enabled]
    if not active_reasons:
        return None
    return ", ".join(active_reasons)


def build_message_context(
    flight_data: Mapping[str, Any],
    interesting: Mapping[str, bool] | None = None,
) -> MessageContext:
    serialized_flight_data = dict(flight_data)
    serialized_interesting = dict(interesting or {})

    flight_label = _resolve_flight_label(serialized_flight_data)
    flight_slug = _resolve_flight_slug(serialized_flight_data)
    registration = _value_or_default(serialized_flight_data.get("registration"))
    aircraft = _resolve_aircraft_label(serialized_flight_data)
    airline_name = _value_or_default(serialized_flight_data.get("airline_name"))
    airline_code = _value_or_default(serialized_flight_data.get("airline"))
    origin_name = _value_or_default(serialized_flight_data.get("origin_name"))
    origin_icao = _value_or_default(serialized_flight_data.get("origin_icao"))
    destination_name = _value_or_default(serialized_flight_data.get("destination_name"))
    destination_icao = _value_or_default(serialized_flight_data.get("destination_icao"))
    scheduled_time = _format_scheduled_time(serialized_flight_data.get("scheduled_time"))
    terminal = _value_or_default(serialized_flight_data.get("terminal"))

    lines = [
        "Flight Information:",
        "",
        f"Flight: {flight_label}",
        f"Registration: {registration}",
        f"Aircraft: {aircraft}",
        f"Airline: {airline_name} ({airline_code})",
        f"Route: {origin_name} ({origin_icao}) -> {destination_name} ({destination_icao})",
        f"Scheduled Time: {scheduled_time}",
        f"Terminal: {terminal}",
    ]

    interesting_line = _format_interesting_reasons(serialized_interesting)
    if interesting_line:
        lines.append(f"Interesting: {interesting_line}")

    if serialized_flight_data.get("diverted") not in (None, False, "null"):
        lines.append("Warning: This flight has been diverted")

    lines.append("")
    lines.append("Check all our socials in https://linktr.ee/ctrl_plataforma")

    message_text = "\n".join(lines)
    flight_url = f"https://www.flightradar24.com/data/flights/{flight_slug}"

    return MessageContext(
        flight_data=serialized_flight_data,
        text=message_text,
        flight_slug=flight_slug,
        flight_url=flight_url,
        interesting=serialized_interesting,
    )


def render_flight_message(
    flight_data: Mapping[str, Any],
    interesting: Mapping[str, bool] | None = None,
) -> str:
    return build_message_context(flight_data, interesting=interesting).text
