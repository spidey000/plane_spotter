from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from string import Formatter
from typing import Any, Mapping

import config.config as cfg
from loguru import logger


PROFILE_SHORT = "short"
PROFILE_MEDIUM = "medium"
PROFILE_LONG = "long"
VALID_PROFILES = (PROFILE_SHORT, PROFILE_MEDIUM, PROFILE_LONG)

ALLOWED_TEMPLATE_FIELDS = {
    "flight_label",
    "flight_slug",
    "flight_url",
    "registration",
    "aircraft",
    "airline_name",
    "airline_code",
    "origin_name",
    "origin_icao",
    "destination_name",
    "destination_icao",
    "scheduled_time",
    "terminal",
    "interesting_text",
    "diverted_text",
    "short_interesting",
    "short_diverted",
    "medium_interesting",
    "medium_diverted",
    "long_interesting",
    "long_diverted",
}

DEFAULT_PROFILE_TEMPLATES = {
    PROFILE_SHORT: (
        "{flight_label} | Reg {registration} | {origin_icao}->{destination_icao} | "
        "{scheduled_time}{short_diverted}{short_interesting}\nFR24: {flight_url}"
    ),
    PROFILE_MEDIUM: (
        "Flight: {flight_label}\n"
        "Reg: {registration} | Aircraft: {aircraft}\n"
        "Route: {origin_icao}->{destination_icao} ({origin_name} to {destination_name})\n"
        "Time: {scheduled_time} | Terminal: {terminal}\n"
        "Airline: {airline_name} ({airline_code}){medium_interesting}{medium_diverted}\n"
        "FR24: {flight_url}"
    ),
    PROFILE_LONG: (
        "Flight Information:\n\n"
        "Flight: {flight_label}\n"
        "Registration: {registration}\n"
        "Aircraft: {aircraft}\n"
        "Airline: {airline_name} ({airline_code})\n"
        "Route: {origin_name} ({origin_icao}) -> {destination_name} ({destination_icao})\n"
        "Scheduled Time: {scheduled_time}\n"
        "Terminal: {terminal}{long_interesting}{long_diverted}\n\n"
        "Check all our socials in https://linktr.ee/ctrl_plataforma"
    ),
}

DEFAULT_PROFILE_MAX_CHARS = {
    PROFILE_SHORT: 275,
    PROFILE_MEDIUM: 1200,
    PROFILE_LONG: 2500,
}

DEFAULT_PLACEHOLDER_MAX_CHARS = {
    PROFILE_SHORT: {
        "flight_label": 24,
        "flight_slug": 40,
        "flight_url": 95,
        "registration": 12,
        "aircraft": 28,
        "airline_name": 30,
        "airline_code": 8,
        "origin_name": 24,
        "origin_icao": 4,
        "destination_name": 24,
        "destination_icao": 4,
        "scheduled_time": 16,
        "terminal": 8,
        "interesting_text": 64,
        "diverted_text": 11,
        "short_interesting": 87,
        "short_diverted": 11,
        "medium_interesting": 96,
        "medium_diverted": 32,
        "long_interesting": 120,
        "long_diverted": 48,
    },
    PROFILE_MEDIUM: {
        "flight_label": 32,
        "flight_slug": 48,
        "flight_url": 95,
        "registration": 12,
        "aircraft": 42,
        "airline_name": 40,
        "airline_code": 8,
        "origin_name": 32,
        "origin_icao": 4,
        "destination_name": 32,
        "destination_icao": 4,
        "scheduled_time": 16,
        "terminal": 10,
        "interesting_text": 90,
        "diverted_text": 24,
        "short_interesting": 100,
        "short_diverted": 11,
        "medium_interesting": 130,
        "medium_diverted": 40,
        "long_interesting": 160,
        "long_diverted": 64,
    },
    PROFILE_LONG: {
        "flight_label": 40,
        "flight_slug": 56,
        "flight_url": 95,
        "registration": 12,
        "aircraft": 60,
        "airline_name": 50,
        "airline_code": 8,
        "origin_name": 50,
        "origin_icao": 4,
        "destination_name": 50,
        "destination_icao": 4,
        "scheduled_time": 16,
        "terminal": 10,
        "interesting_text": 140,
        "diverted_text": 32,
        "short_interesting": 120,
        "short_diverted": 11,
        "medium_interesting": 170,
        "medium_diverted": 48,
        "long_interesting": 220,
        "long_diverted": 90,
    },
}


@dataclass(frozen=True)
class MessageContext:
    flight_data: dict[str, Any]
    text: str
    texts_by_profile: dict[str, str]
    flight_slug: str
    flight_url: str
    interesting: dict[str, bool]
    selected_profile: str | None = None
    selected_platform: str | None = None


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


def _normalize_profile(profile: str | None) -> str:
    if not profile:
        return PROFILE_LONG
    candidate = str(profile).strip().lower()
    if candidate in VALID_PROFILES:
        return candidate
    return PROFILE_LONG


def _normalize_positive_int(value: Any) -> int | None:
    if value in (None, "", "null"):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    if parsed <= 0:
        return None
    return parsed


def _extract_template_fields(template: str) -> list[str]:
    fields: list[str] = []
    try:
        for _literal_text, field_name, format_spec, conversion in Formatter().parse(template):
            if field_name is None:
                continue
            if not field_name:
                raise ValueError("Empty placeholder is not allowed")
            if format_spec:
                raise ValueError(f"Format specifiers are not supported ('{field_name}:{format_spec}')")
            if conversion:
                raise ValueError(f"Conversions are not supported ('{field_name}!{conversion}')")
            if not field_name.isidentifier():
                raise ValueError(f"Invalid placeholder '{field_name}'")
            fields.append(field_name)
    except ValueError as exc:
        raise ValueError(f"Invalid template format: {exc}") from exc

    return fields


def _template_static_length(template: str) -> int:
    return sum(len(literal_text) for literal_text, _field_name, _format_spec, _conversion in Formatter().parse(template))


def _truncate(value: str, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    if len(value) <= max_chars:
        return value
    if max_chars <= 3:
        return value[:max_chars]
    return value[: max_chars - 3] + "..."


def _build_template_configuration(
    loaded: Mapping[str, Any] | None,
) -> tuple[dict[str, str], dict[str, int], dict[str, dict[str, int]]]:
    templates = dict(DEFAULT_PROFILE_TEMPLATES)
    profile_max_chars = dict(DEFAULT_PROFILE_MAX_CHARS)
    placeholder_max_chars = {
        profile: dict(limits)
        for profile, limits in DEFAULT_PLACEHOLDER_MAX_CHARS.items()
    }

    if not isinstance(loaded, Mapping):
        return templates, profile_max_chars, placeholder_max_chars

    loaded_profiles = loaded.get("profiles")
    if isinstance(loaded_profiles, Mapping):
        for profile in VALID_PROFILES:
            candidate = loaded_profiles.get(profile)
            if candidate is None:
                continue
            if isinstance(candidate, str) and candidate.strip():
                templates[profile] = candidate
                continue
            logger.warning(
                f"Ignoring message_templates.profiles.{profile}: expected non-empty string"
            )

    loaded_validation = loaded.get("validation")
    if not isinstance(loaded_validation, Mapping):
        return templates, profile_max_chars, placeholder_max_chars

    loaded_profile_max = loaded_validation.get("profile_max_chars")
    if isinstance(loaded_profile_max, Mapping):
        for profile in VALID_PROFILES:
            candidate = _normalize_positive_int(loaded_profile_max.get(profile))
            if candidate is not None:
                profile_max_chars[profile] = candidate

    loaded_placeholder_max = loaded_validation.get("placeholder_max_chars")
    if isinstance(loaded_placeholder_max, Mapping):
        for profile in VALID_PROFILES:
            profile_limits = loaded_placeholder_max.get(profile)
            if not isinstance(profile_limits, Mapping):
                continue
            for field_name, raw_limit in profile_limits.items():
                if not isinstance(field_name, str):
                    continue
                parsed_limit = _normalize_positive_int(raw_limit)
                if parsed_limit is not None:
                    placeholder_max_chars[profile][field_name] = parsed_limit

    return templates, profile_max_chars, placeholder_max_chars


def _validate_profile_template(
    profile: str,
    template: str,
    profile_max_chars: int,
    placeholder_limits: Mapping[str, int],
) -> tuple[bool, str | None]:
    try:
        fields = _extract_template_fields(template)
    except ValueError as exc:
        return False, str(exc)

    unsupported = sorted({field for field in fields if field not in ALLOWED_TEMPLATE_FIELDS})
    if unsupported:
        return False, f"Unsupported placeholders: {unsupported}"

    missing_limits = sorted({field for field in fields if field not in placeholder_limits})
    if missing_limits:
        return False, f"Missing placeholder_max_chars for: {missing_limits}"

    static_length = _template_static_length(template)
    dynamic_budget = sum(placeholder_limits[field] for field in fields)
    total_budget = static_length + dynamic_budget
    if total_budget > profile_max_chars:
        return (
            False,
            (
                f"Template budget exceeds profile max chars "
                f"({total_budget} > {profile_max_chars})"
            ),
        )

    return True, None


def _resolve_templates() -> tuple[dict[str, str], dict[str, int], dict[str, dict[str, int]]]:
    loaded = cfg.get_config("message_templates")
    templates, profile_max_chars, placeholder_limits = _build_template_configuration(
        loaded if isinstance(loaded, Mapping) else None
    )

    for profile in VALID_PROFILES:
        valid, reason = _validate_profile_template(
            profile,
            templates[profile],
            profile_max_chars[profile],
            placeholder_limits[profile],
        )
        if valid:
            continue

        logger.warning(
            (
                f"Invalid template override for profile '{profile}': {reason}. "
                "Falling back to default template and default limits."
            )
        )
        templates[profile] = DEFAULT_PROFILE_TEMPLATES[profile]
        profile_max_chars[profile] = DEFAULT_PROFILE_MAX_CHARS[profile]
        placeholder_limits[profile] = dict(DEFAULT_PLACEHOLDER_MAX_CHARS[profile])

    return templates, profile_max_chars, placeholder_limits


def _render_profile_text(
    *,
    profile: str,
    template: str,
    profile_max_chars: int,
    placeholder_limits: Mapping[str, int],
    values: Mapping[str, str],
) -> str:
    bounded_values: dict[str, str] = {}
    for field_name, raw_value in values.items():
        value = "" if _is_nullish(raw_value) else str(raw_value)
        limit = placeholder_limits.get(field_name)
        if limit is not None:
            value = _truncate(value, limit)
        bounded_values[field_name] = value

    try:
        rendered = template.format_map(bounded_values)
    except Exception as exc:
        logger.warning(
            (
                f"Rendering template for profile '{profile}' failed: {exc}. "
                "Using default template."
            )
        )
        fallback_limits = DEFAULT_PLACEHOLDER_MAX_CHARS[profile]
        fallback_values: dict[str, str] = {}
        for field_name, raw_value in values.items():
            value = "" if _is_nullish(raw_value) else str(raw_value)
            fallback_values[field_name] = _truncate(value, fallback_limits[field_name])
        rendered = DEFAULT_PROFILE_TEMPLATES[profile].format_map(fallback_values)

    if len(rendered) > profile_max_chars:
        rendered = _truncate(rendered, profile_max_chars)
    return rendered


def _build_texts_by_profile(values: Mapping[str, str]) -> dict[str, str]:
    templates, profile_max_chars, placeholder_limits = _resolve_templates()

    return {
        profile: _render_profile_text(
            profile=profile,
            template=templates[profile],
            profile_max_chars=profile_max_chars[profile],
            placeholder_limits=placeholder_limits[profile],
            values=values,
        )
        for profile in VALID_PROFILES
    }


def build_message_context(
    flight_data: Mapping[str, Any],
    interesting: Mapping[str, bool] | None = None,
) -> MessageContext:
    serialized_flight_data = dict(flight_data)
    serialized_interesting = dict(interesting or {})

    flight_label = _resolve_flight_label(serialized_flight_data)
    flight_slug = _resolve_flight_slug(serialized_flight_data)
    flight_url = f"https://www.flightradar24.com/data/flights/{flight_slug}"

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
    interesting_line = _format_interesting_reasons(serialized_interesting)
    diverted = serialized_flight_data.get("diverted") not in (None, False, "null")

    interesting_text = interesting_line or ""
    short_interesting = f" | Interesting: {interesting_text}" if interesting_text else ""
    short_diverted = " | DIVERTED" if diverted else ""
    medium_interesting = f"\nInteresting: {interesting_text}" if interesting_text else ""
    medium_diverted = "\nWarning: Flight diverted" if diverted else ""
    long_interesting = f"\nInteresting: {interesting_text}" if interesting_text else ""
    long_diverted = "\nWarning: This flight has been diverted" if diverted else ""

    text_values = {
        "flight_label": flight_label,
        "flight_slug": flight_slug,
        "flight_url": flight_url,
        "registration": registration,
        "aircraft": aircraft,
        "airline_name": airline_name,
        "airline_code": airline_code,
        "origin_name": origin_name,
        "origin_icao": origin_icao,
        "destination_name": destination_name,
        "destination_icao": destination_icao,
        "scheduled_time": scheduled_time,
        "terminal": terminal,
        "interesting_text": interesting_text,
        "diverted_text": "DIVERTED" if diverted else "",
        "short_interesting": short_interesting,
        "short_diverted": short_diverted,
        "medium_interesting": medium_interesting,
        "medium_diverted": medium_diverted,
        "long_interesting": long_interesting,
        "long_diverted": long_diverted,
    }

    texts_by_profile = _build_texts_by_profile(text_values)

    return MessageContext(
        flight_data=serialized_flight_data,
        text=texts_by_profile[PROFILE_LONG],
        texts_by_profile=texts_by_profile,
        flight_slug=flight_slug,
        flight_url=flight_url,
        interesting=serialized_interesting,
    )


def build_platform_context(
    base_context: MessageContext,
    *,
    platform: str,
    profile: str,
    text: str,
) -> MessageContext:
    return replace(
        base_context,
        text=text,
        selected_profile=_normalize_profile(profile),
        selected_platform=platform,
    )


def render_flight_message(
    flight_data: Mapping[str, Any],
    interesting: Mapping[str, bool] | None = None,
    profile: str = PROFILE_LONG,
) -> str:
    context = build_message_context(flight_data, interesting=interesting)
    normalized_profile = _normalize_profile(profile)
    return context.texts_by_profile.get(normalized_profile, context.texts_by_profile[PROFILE_LONG])
