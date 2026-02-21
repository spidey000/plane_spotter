"""Flight processing and DB enrichment utilities."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from loguru import logger


def _is_nullish(value: Any) -> bool:
    return value in (None, "", "null", "None")


def _normalize_registration(value: Any) -> str | None:
    if _is_nullish(value):
        return None
    return str(value).strip().upper()


def _normalize_model(value: Any) -> str | None:
    if _is_nullish(value):
        return None
    return str(value).strip().upper()


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value

    if isinstance(value, str) and value.strip():
        normalized = value.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
            if parsed.tzinfo is None:
                return parsed
            return parsed.astimezone(timezone.utc)
        except ValueError:
            pass

        for fmt in (
            "%Y-%m-%d %H:%M",
            "%Y-%m-%dT%H:%M",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
        ):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue

    return datetime.now()

def process_flight_data_adb(flight, movement):
    # Extract flight information
    try:
        registration = flight['aircraft']['reg']
    except Exception as e:
        logger.debug(f"Failed to get registration: {e}")
        registration = 'null'


    flight_name = flight.get('callSign', 'null')
    flight_name_iata = flight.get('number', 'null')


    aircraft_name = flight['aircraft'].get('model', 'null')
    airline = flight['airline'].get('icao', 'null')
    airline_name = flight['airline'].get('name', 'null')

    if movement == 'departures':
        destination_icao = flight['arrival']['airport']['icao']
        destination_name = flight['arrival']['airport']['name']
        origin_icao = "LEMD"
        origin_name = "Madrid"
    else:
        origin_icao = flight['departure']['airport']['icao']
        origin_name = flight['departure']['airport']['name']
        destination_icao = "LEMD"
        destination_name = "Madrid"

    terminal = flight[movement.removesuffix('s')].get('terminal', 'null')
    diverted = 'null'
    
    # Get scheduled time and convert to datetime object
    try:
        scheduled_time_str = flight[movement.removesuffix("s")]["revisedTime"]["local"][:-6]
        scheduled_time = datetime.strptime(scheduled_time_str, "%Y-%m-%d %H:%M")
    except Exception as e:
        logger.error(f"Failed to parse scheduled time: {e}")
        scheduled_time = datetime.now()
    
    # Get last update time (use revised time if available, otherwise scheduled time)
    last_update = datetime.now().strftime("%Y-%m-%d %H:%M")

    single_flight_data = {
        "flight_name": "".join(flight_name.split()),
        "flight_name_iata": flight_name_iata,
        "registration": registration,
        "aircraft_name": aircraft_name.strip(),
        "aircraft_icao": None,
        "airline": airline,
        "airline_name": airline_name,
        "origin_icao": origin_icao,
        "origin_name": origin_name,
        "destination_icao": destination_icao,
        "destination_name": destination_name,
        "terminal": terminal,
        "scheduled_time": scheduled_time,
        "last_update": last_update,
        "diverted": diverted,
    }

    logger.debug(f"Processed ADB flight data: {single_flight_data}")
    return single_flight_data

def get_valid_value(flight, keys, default="null"):
    """Returns the first non-null and non-'null' value from the flight dictionary."""
    return next((flight.get(k) for k in keys if flight.get(k) not in [None, "null"]), default)


def _select_best_event_time(flight: dict[str, Any], keys: list[str]) -> Any:
    """Select the best available event timestamp using ordered AeroAPI fallbacks."""
    return get_valid_value(flight, keys)


def process_flight_data_aeroapi(flight):
    try:
        registration = flight["registration"]
    except Exception as e:
        logger.warning(f"Failed to get registration: {e}")
        return None
    
    is_departure = flight.get("origin", {}).get("code_icao") == "LEMD"
    
    if is_departure:
        scheduled_time = _select_best_event_time(
            flight,
            [
                "actual_out",
                "estimated_out",
                "scheduled_out",
                "actual_off",
                "estimated_off",
                "scheduled_off",
            ],
        )
        terminal = flight.get("terminal_origin", "null")
        origin_icao, origin_name = "LEMD", "Madrid"
        destination_icao = flight.get("destination", {}).get("code_icao", "null")
        destination_name = flight.get("destination", {}).get("name", "null")
    else:
        scheduled_time = _select_best_event_time(
            flight,
            [
                "actual_in",
                "estimated_in",
                "scheduled_in",
                "actual_on",
                "estimated_on",
                "scheduled_on",
            ],
        )
        terminal = flight.get("terminal_destination", "null")
        origin_icao = flight.get("origin", {}).get("code_icao", "null")
        origin_name = flight.get("origin", {}).get("name", "null")
        destination_icao, destination_name = "LEMD", "Madrid"
    
    flight_name = get_valid_value(flight, ["atc_ident", "ident_icao"])
    flight_name_iata = get_valid_value(flight, ["ident_iata", "null"])
    aircraft = flight.get("aircraft_type", "null")
    airline = flight.get("operator_icao", "null")
    airline_name = flight.get("operator", "null")
    diverted = flight.get("diverted", "null")

    # Get last update time
    last_update = datetime.now().strftime("%Y-%m-%d %H:%M")

    single_flight_data = {
        "flight_name": "".join(flight_name.split()),
        "flight_name_iata": flight_name_iata,
        "registration": registration,
        "aircraft_name": None,
        "aircraft_icao": (aircraft or "null").strip(),
        "airline": airline,
        "airline_name": airline_name,
        "origin_icao": origin_icao,
        "origin_name": origin_name,
        "destination_icao": destination_icao,
        "destination_name": destination_name,
        "terminal": terminal,
        "scheduled_time": _parse_datetime(scheduled_time),
        "last_update": last_update,
        "diverted": diverted,
    }

    logger.debug(f"Processed AeroAPI flight data: {single_flight_data}")
    return single_flight_data

def _is_interesting_model(
    flight: dict[str, Any],
    model_db: dict[str, dict[str, Any]],
) -> bool:
    aircraft_icao = _normalize_model(flight.get("aircraft_icao"))
    if aircraft_icao and aircraft_icao in model_db:
        return True

    aircraft_name = str(flight.get("aircraft_name") or "").lower()
    if not aircraft_name:
        return False

    for model_entry in model_db.values():
        model_name = str(model_entry.get("name") or "").strip().lower()
        if model_name and model_name in aircraft_name:
            return True

    return False


async def check_flight(
    flight,
    reg_db,
    interesting_reg_db,
    model_db,
    db_provider,
    airport_icao="LEMD",
):
    interesting_registration = False
    interesting_model = False
    first_seen = False

    # Convert scheduled_time to string if needed
    if not isinstance(flight["scheduled_time"], str):
        flight["scheduled_time"] = _parse_datetime(flight["scheduled_time"]).strftime("%Y-%m-%d %H:%M")
        logger.debug(f"Converted scheduled_time to string format")

    registration = _normalize_registration(flight.get("registration"))
    if registration:
        if registration in reg_db:
            logger.debug(f"Flight {registration} has been seen before")

        interesting_registration = registration in interesting_reg_db and bool(
            interesting_reg_db[registration].get("is_active", True)
        )
        if interesting_registration:
            logger.info(f"Flight {registration} is in interesting registrations table")

        try:
            db_row, created = await db_provider.upsert_registration_sighting(
                flight,
                airport_icao=airport_icao,
            )
            first_seen = bool(created)
            if db_row is not None:
                reg_db[registration] = db_row
            if created:
                logger.success(f"Created new registration row for {registration}")
        except Exception as e:
            logger.error(f"Failed to upsert registration {registration}: {e}")

    interesting_model = _is_interesting_model(flight, model_db)
    if interesting_model:
        logger.info(
            f"Flight {flight.get('flight_name_iata') or flight.get('flight_name')} matches interesting model"
        )

    return flight, interesting_registration, interesting_model, first_seen

# If flight already exists, merge data
def check_existing(all_flights, processed_data):
    if not processed_data:
        return

    iata_key = processed_data.get("flight_name_iata")
    fallback_key = processed_data.get("flight_name")

    existing_key = None
    if iata_key not in [None, "null"] and iata_key in all_flights:
        existing_key = iata_key
    elif fallback_key not in [None, "null"] and fallback_key in all_flights:
        existing_key = fallback_key

    if existing_key is None:
        new_key = iata_key if iata_key not in [None, "null"] else fallback_key
        if new_key in [None, "null"]:
            return
        all_flights[new_key] = processed_data
        return

    for key, value in processed_data.items():
        if all_flights[existing_key].get(key) in [None, "null"] and value not in [None, "null"]:
            all_flights[existing_key][key] = value
            logger.debug(f"Updated {key} for {existing_key}")
