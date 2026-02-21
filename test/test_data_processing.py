from utils.data_processing import process_flight_data_aeroapi


def test_aeroapi_arrival_uses_arrival_eta_fields_instead_of_origin_schedule():
    flight = {
        "registration": "EC-XYZ",
        "origin": {"code_icao": "LFPG", "name": "Paris"},
        "destination": {"code_icao": "LEMD", "name": "Madrid"},
        "scheduled_out": "2025-02-12T10:00:00Z",
        "estimated_in": "2025-02-12T12:30:00Z",
    }

    result = process_flight_data_aeroapi(flight)

    assert result is not None
    assert result["scheduled_time"].strftime("%Y-%m-%d %H:%M") == "2025-02-12 13:30"


def test_aeroapi_departure_prefers_actual_then_estimated_then_scheduled():
    flight = {
        "registration": "EC-ABC",
        "origin": {"code_icao": "LEMD", "name": "Madrid"},
        "destination": {"code_icao": "LEBL", "name": "Barcelona"},
        "scheduled_out": "2025-02-12T10:00:00Z",
        "estimated_out": "2025-02-12T10:30:00Z",
        "actual_out": "2025-02-12T10:40:00Z",
    }

    result = process_flight_data_aeroapi(flight)

    assert result is not None
    assert result["scheduled_time"].strftime("%Y-%m-%d %H:%M") == "2025-02-12 11:40"


def test_aeroapi_arrival_falls_back_to_scheduled_in_when_no_estimated_or_actual():
    flight = {
        "registration": "EC-DEF",
        "origin": {"code_icao": "EGLL", "name": "London"},
        "destination": {"code_icao": "LEMD", "name": "Madrid"},
        "scheduled_in": "2025-02-12T21:00:00Z",
    }

    result = process_flight_data_aeroapi(flight)

    assert result is not None
    assert result["scheduled_time"].strftime("%Y-%m-%d %H:%M") == "2025-02-12 22:00"
