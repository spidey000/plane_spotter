import sys
import time
from pathlib import Path
from typing import Awaitable, Callable
from urllib.parse import urlparse

import config.config as cfg
import requests
from loguru import logger

# Add project root to Python path
sys.path.append(str(Path(__file__).parent.parent))

import socials.bluesky as bs
import socials.linkedin as li
import socials.instagram as ig
import socials.telegram as tg
import socials.threads as th
import socials.twitter as tw
from monitoring.api_usage import record_api_event
from socials.message_builder import MessageContext, build_message_context
from utils.image_finder import get_first_image_url_jp, get_first_image_url_pp
import os


PlatformSender = Callable[[MessageContext, str | None], Awaitable[None]]


def _build_sender_registry() -> dict[str, PlatformSender]:
    return {
        "telegram": tg.send_message,
        "bluesky": bs.send_message,
        "twitter": tw.send_message,
        "threads": th.send_message,
        "instagram": ig.send_message,
        "linkedin": li.send_message,
    }


def _download_image(image_url: str, temp_image_path: str) -> str | None:
    endpoint = f"GET {urlparse(image_url).path}"
    started = time.perf_counter()
    try:
        response = requests.get(image_url, timeout=30)
        duration_ms = (time.perf_counter() - started) * 1000.0
        record_api_event(
            provider="image-cdn",
            endpoint=endpoint,
            method="GET",
            status_code=response.status_code,
            success=response.status_code == 200,
            duration_ms=duration_ms,
            estimated_cost_usd=0.0,
        )
        if response.status_code != 200:
            return None

        with open(temp_image_path, "wb+") as file_handle:
            file_handle.write(response.content)
        return temp_image_path
    except Exception as exc:
        duration_ms = (time.perf_counter() - started) * 1000.0
        record_api_event(
            provider="image-cdn",
            endpoint=endpoint,
            method="GET",
            status_code=None,
            success=False,
            duration_ms=duration_ms,
            estimated_cost_usd=0.0,
            error=str(exc),
        )
        logger.warning(f"Unable to download image from {image_url}: {exc}")
        return None


async def call_socials(flight_data, interesting):
    logger.debug(f"Starting socials processing for flight {flight_data['flight_name']}")
    context = build_message_context(flight_data, interesting=interesting)
    sender_registry = _build_sender_registry()

    temp_image_path = None

    try:
        logger.debug(f"Fetching image for registration {flight_data['registration']} from JetPhotos")
        image_url = None
        if flight_data["registration"] not in [None, "null"]:
            image_url = get_first_image_url_jp(flight_data["registration"])
            if not image_url:
                logger.debug("No image found on JetPhotos, trying Planespotters")
                image_url = get_first_image_url_pp(flight_data["registration"])

        if image_url:
            logger.debug(f"Found image at {image_url}, downloading...")
            temp_image_path = _download_image(image_url, "socials/temp_image.jpg")
            if temp_image_path:
                logger.debug(f"Image saved to {temp_image_path}")

        social_config = cfg.get_config("social_networks") or {}
        for platform_name, sender in sender_registry.items():
            if not social_config.get(platform_name, False):
                logger.debug(f"Skipping disabled platform '{platform_name}'")
                continue

            try:
                await sender(context, image_path=temp_image_path)
            except Exception as exc:
                logger.error(f"Failed while sending message to {platform_name}: {exc}")

    finally:
        # Clean up temporary image
        if temp_image_path and os.path.exists(temp_image_path):
            os.remove(temp_image_path)
            logger.debug(f"Removed temporary image {temp_image_path}")
