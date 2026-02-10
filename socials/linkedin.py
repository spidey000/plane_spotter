from __future__ import annotations

from loguru import logger

from socials.message_builder import MessageContext, render_flight_message


def generate_flight_message(flight_data, interesting=None):
    return render_flight_message(flight_data, interesting=interesting)


async def post_to_linkedin(flight_data, image_path=None, message_text=None):
    logger.info(
        "LinkedIn sender placeholder: implement provider-specific publishing before enabling this platform"
    )
    logger.debug(
        f"LinkedIn payload prepared for {flight_data.get('flight_name_iata') or flight_data.get('flight_name')}"
    )


async def send_message(context: MessageContext, image_path: str | None = None):
    await post_to_linkedin(context.flight_data, image_path=image_path, message_text=context.text)
