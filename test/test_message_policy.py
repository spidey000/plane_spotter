from __future__ import annotations

from datetime import datetime

from socials.message_builder import (
    PROFILE_LONG,
    PROFILE_MEDIUM,
    PROFILE_SHORT,
    build_message_context,
)
from socials.message_policy import resolve_message_for_platform


def _sample_flight_data() -> dict:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    return {
        "flight_name": "LONGTEST9001",
        "flight_name_iata": "LT9001",
        "registration": "EC-TST",
        "aircraft_name": "Airbus A321-271NX",
        "aircraft_icao": "A21N",
        "airline": "IBE",
        "airline_name": "Iberia",
        "origin_icao": "LEBL",
        "origin_name": "Barcelona",
        "destination_icao": "LEMD",
        "destination_name": "Madrid",
        "terminal": "T4",
        "scheduled_time": now,
        "last_update": now,
        "diverted": False,
    }


def test_builder_generates_all_profiles() -> None:
    context = build_message_context(_sample_flight_data(), interesting={"FIRST_SEEN": True})

    assert PROFILE_SHORT in context.texts_by_profile
    assert PROFILE_MEDIUM in context.texts_by_profile
    assert PROFILE_LONG in context.texts_by_profile

    short_len = len(context.texts_by_profile[PROFILE_SHORT])
    medium_len = len(context.texts_by_profile[PROFILE_MEDIUM])
    long_len = len(context.texts_by_profile[PROFILE_LONG])

    assert short_len <= medium_len <= long_len


def test_message_policy_fallbacks_to_short() -> None:
    context = build_message_context(_sample_flight_data(), interesting={"FIRST_SEEN": True, "MODEL": True})
    short_len = len(context.texts_by_profile[PROFILE_SHORT])

    decision = resolve_message_for_platform(
        "twitter",
        context,
        policy_override={
            "defaults": {
                "fallback_order": ["long", "medium", "short"],
                "overflow_action": "block",
            },
            "platforms": {"twitter": {"preferred_profile": "long"}},
            "platform_limits": {
                "twitter": short_len,
            },
        },
    )

    assert not decision.blocked
    assert decision.selected_profile == PROFILE_SHORT
    assert decision.used_fallback


def test_message_policy_blocks_when_nothing_fits() -> None:
    context = build_message_context(_sample_flight_data(), interesting={"FIRST_SEEN": True})

    decision = resolve_message_for_platform(
        "twitter",
        context,
        policy_override={
            "defaults": {"overflow_action": "block"},
            "platform_limits": {"twitter": 10},
            "platforms": {"twitter": {"preferred_profile": "short"}},
        },
    )

    assert decision.blocked
    assert decision.text is None
    assert decision.selected_profile is None
