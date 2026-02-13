from __future__ import annotations

from datetime import datetime

import socials.message_builder as mb


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


def _patch_templates(monkeypatch, templates_config):
    def fake_get_config(key: str):
        if key == "message_templates":
            return templates_config
        return None

    monkeypatch.setattr(mb.cfg, "get_config", fake_get_config)


def test_template_override_is_applied(monkeypatch) -> None:
    _patch_templates(
        monkeypatch,
        {
            "profiles": {
                "short": "OVR {flight_label} [{registration}]\\nURL {flight_url}",
            }
        },
    )

    text = mb.render_flight_message(
        _sample_flight_data(),
        interesting={"FIRST_SEEN": True},
        profile=mb.PROFILE_SHORT,
    )

    assert text.startswith("OVR LT9001/LONGTEST9001 [EC-TST]")
    assert "URL https://www.flightradar24.com/data/flights/lt9001" in text


def test_unknown_placeholder_falls_back_to_default(monkeypatch) -> None:
    _patch_templates(monkeypatch, None)
    expected = mb.render_flight_message(
        _sample_flight_data(),
        interesting={"FIRST_SEEN": True},
        profile=mb.PROFILE_SHORT,
    )

    _patch_templates(
        monkeypatch,
        {
            "profiles": {
                "short": "BROKEN {unknown_placeholder}",
            }
        },
    )
    actual = mb.render_flight_message(
        _sample_flight_data(),
        interesting={"FIRST_SEEN": True},
        profile=mb.PROFILE_SHORT,
    )

    assert actual == expected


def test_short_template_budget_violation_falls_back(monkeypatch) -> None:
    _patch_templates(monkeypatch, None)
    expected = mb.render_flight_message(
        _sample_flight_data(),
        interesting={"FIRST_SEEN": True},
        profile=mb.PROFILE_SHORT,
    )

    oversized = " ".join(["{flight_label}"] * 12)
    _patch_templates(
        monkeypatch,
        {
            "profiles": {
                "short": oversized,
            }
        },
    )
    actual = mb.render_flight_message(
        _sample_flight_data(),
        interesting={"FIRST_SEEN": True},
        profile=mb.PROFILE_SHORT,
    )

    assert actual == expected


def test_placeholder_limits_truncate_values(monkeypatch) -> None:
    _patch_templates(
        monkeypatch,
        {
            "profiles": {
                "short": "F:{flight_label}|R:{registration}|I:{short_interesting}|U:{flight_url}",
            },
            "validation": {
                "placeholder_max_chars": {
                    "short": {
                        "flight_label": 8,
                        "registration": 6,
                        "short_interesting": 18,
                        "flight_url": 25,
                    }
                }
            },
        },
    )

    flight = _sample_flight_data()
    flight["flight_name"] = "VERYVERYLONGCALLSIGN9999"
    flight["flight_name_iata"] = "VERYLONG9999"
    flight["registration"] = "EC-VERYLONGREG"

    text = mb.render_flight_message(
        flight,
        interesting={
            "FIRST_SEEN": True,
            "MODEL": True,
            "REGISTRATION": True,
            "DIVERTED": True,
        },
        profile=mb.PROFILE_SHORT,
    )

    assert text.startswith("F:")
    assert text.count("...") >= 2
    assert len(text) <= 275


def test_default_short_profile_is_capped_to_275(monkeypatch) -> None:
    _patch_templates(monkeypatch, None)

    flight = _sample_flight_data()
    flight["flight_name"] = "ULTRALONGFLIGHTNAMEFORSHORTPROFILECHECK"
    flight["flight_name_iata"] = "ULTRA1234567890"
    flight["registration"] = "EC-SUPERLONGREGISTRATION"

    text = mb.render_flight_message(
        flight,
        interesting={
            "FIRST_SEEN": True,
            "MODEL": True,
            "REGISTRATION": True,
            "DIVERTED": True,
            "OPS_SPECIAL_CASE": True,
            "NIGHT_OPERATION": True,
        },
        profile=mb.PROFILE_SHORT,
    )

    assert len(text) <= 275
