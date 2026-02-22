import asyncio
from pathlib import Path

from socials import telegram as tg


def test_schedule_telegram_caches_image_bytes_for_background_send(tmp_path, monkeypatch):
    image_path = tmp_path / "flight.jpg"
    payload = b"test-image-bytes"
    image_path.write_bytes(payload)

    called = {}

    async def fake_send_flight_update(**kwargs):
        called.update(kwargs)

    monkeypatch.setattr(tg, "send_flight_update", fake_send_flight_update)

    flight_data = {
        "flight_name_iata": "AB123",
        "scheduled_time": "2000-01-01 00:00",
        "registration": "EC-ABC",
    }

    async def run_test():
        task = await tg.schedule_telegram(flight_data, image_path=str(image_path), message_text="hello")
        image_path.unlink()
        await task

    asyncio.run(run_test())

    assert called["image_path"] == str(image_path)
    assert called["image_bytes"] == payload
