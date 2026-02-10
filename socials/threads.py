from __future__ import annotations

from loguru import logger

from socials.message_builder import MessageContext, render_flight_message


def generate_flight_message(flight_data, interesting=None):
    return render_flight_message(flight_data, interesting=interesting)


async def post_to_threads(flight_data, image_path=None, message_text=None):
    logger.info(
        "Threads sender placeholder: implement API credentials and endpoint wiring before enabling this platform"
    )
    logger.debug(
        f"Threads payload prepared for {flight_data.get('flight_name_iata') or flight_data.get('flight_name')}"
    )


async def send_message(context: MessageContext, image_path: str | None = None):
    await post_to_threads(context.flight_data, image_path=image_path, message_text=context.text)
