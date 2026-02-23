import asyncio

from socials import telegram as tg
from socials.message_builder import MessageContext


def _build_context():
    flight_data = {
        'flight_name_iata': 'AB123',
        'flight_name': 'AB123',
        'scheduled_time': '2000-01-01 00:00',
        'registration': 'EC-ABC',
    }
    return MessageContext(
        flight_data=flight_data,
        text='hello world',
        texts_by_profile={'short': 'hello world'},
        flight_slug='ab123',
        flight_url='https://example.com',
        interesting={},
    )


def test_send_message_calls_flight_update_immediately(monkeypatch, tmp_path):
    called = {}

    async def fake_send_flight_update(**kwargs):
        called['kwargs'] = kwargs

    monkeypatch.setenv('TELEGRAM_CHAT_ID', '12345')
    monkeypatch.setattr(tg, 'send_flight_update', fake_send_flight_update)

    image_path = tmp_path / 'flight.jpg'
    image_path.write_bytes(b'image-bytes')
    context = _build_context()

    asyncio.run(tg.send_message(context, image_path=str(image_path)))

    sent_kwargs = called['kwargs']
    assert sent_kwargs['chat_id'] == '12345'
    assert sent_kwargs['flight_data'] == context.flight_data
    assert sent_kwargs['image_path'] == str(image_path)
    assert sent_kwargs['message_text'] == context.text
    assert sent_kwargs['flight_url'] == context.flight_url
    assert sent_kwargs['registration_url'] == context.registration_url
    assert sent_kwargs['image_bytes'] is None
