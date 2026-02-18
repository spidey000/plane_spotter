from __future__ import annotations

import argparse
import asyncio
import io
import os
from pathlib import Path
from typing import Any
import config.config as cfg

from loguru import logger
from PIL import Image

from socials.message_builder import MessageContext, render_flight_message
from utils.create_bsky_post import create_post

_NULLISH_REG_VALUES = {"", "null", "none"}
_TRUE_BOOL_VALUES = {"1", "true", "yes", "y", "on"}
_FALSE_BOOL_VALUES = {"0", "false", "no", "n", "off"}


def _build_registration_facets(
    text: str,
    registration_value: Any,
    registration_url: str | None,
) -> list[dict[str, Any]] | None:
    if not registration_url:
        return None

    if registration_value is None:
        return None

    registration_text = str(registration_value).strip()
    if not registration_text:
        return None

    if registration_text.lower() in _NULLISH_REG_VALUES:
        return None

    start_index = text.find(registration_text)
    if start_index == -1:
        return None

    end_index = start_index + len(registration_text)
    byte_start = len(text[:start_index].encode("utf-8"))
    byte_end = len(text[:end_index].encode("utf-8"))
    return [
        {
            "index": {
                "byteStart": byte_start,
                "byteEnd": byte_end,
            },
            "features": [
                {
                    "$type": "app.bsky.richtext.facet#link",
                    "uri": registration_url,
                }
            ],
        }
    ]


def _bluesky_registration_links_enabled() -> bool:
    platform_config = cfg.get_config("platform_settings.bluesky")
    if not isinstance(platform_config, dict):
        return True

    registration_value = platform_config.get("registration_link_enabled")
    if isinstance(registration_value, bool):
        return registration_value

    if isinstance(registration_value, str):
        normalized = registration_value.strip().lower()
        if normalized in _TRUE_BOOL_VALUES:
            return True
        if normalized in _FALSE_BOOL_VALUES:
            return False
        return True

    if isinstance(registration_value, (int, float)):
        return bool(registration_value)

    return True

def generate_flight_message(flight_data: dict[str, Any], interesting: dict[str, bool] | None = None) -> str:
    return render_flight_message(flight_data, interesting=interesting)


def _compress_if_needed(image_path: str) -> str:
    if not Path(image_path).exists() or os.path.getsize(image_path) <= 1_000_000:
        return image_path

    with Image.open(image_path) as img:
        output = io.BytesIO()
        img.convert("RGB").save(output, format="JPEG", quality=85, optimize=True)

        if output.tell() > 1_000_000:
            new_size = (max(1, img.width // 2), max(1, img.height // 2))
            resized = img.resize(new_size, Image.Resampling.LANCZOS)
            quality = 80
            while quality >= 50:
                output.seek(0)
                output.truncate(0)
                resized.convert("RGB").save(output, format="JPEG", quality=quality, optimize=True)
                if output.tell() <= 1_000_000:
                    break
                quality -= 5

        compressed_path = f"{image_path}_compressed.jpg"
        with open(compressed_path, "wb") as file_handle:
            file_handle.write(output.getbuffer())

    logger.debug(f"Compressed image for Bluesky: {compressed_path} ({Path(compressed_path).stat().st_size} bytes)")
    return compressed_path


def _post_flight_to_bluesky_sync(
    flight_data: dict[str, Any],
    image_path: str | None = None,
    message_text: str | None = None,
    flight_url: str | None = None,
    registration_url: str | None = None,
) -> None:
    handle = os.getenv("BLUESKY_HANDLE")
    password = os.getenv("BLUESKY_PASSWORD")
    if not handle or not password:
        logger.warning("BLUESKY_HANDLE/BLUESKY_PASSWORD are missing; skipping Bluesky publish")
        return

    message = message_text or generate_flight_message(flight_data)
    registration_facets = None
    if _bluesky_registration_links_enabled():
        registration_facets = _build_registration_facets(
            message,
            flight_data.get("registration"),
            registration_url,
        )
    embed_url = flight_url
    if not embed_url:
        flight_slug = flight_data.get("flight_name_iata") or flight_data.get("flight_name") or "unknown-flight"
        embed_url = f"https://www.flightradar24.com/data/flights/{str(flight_slug).replace(' ', '').lower()}"

    upload_image_path = None
    if image_path and flight_data.get("registration") not in (None, "null"):
        try:
            upload_image_path = _compress_if_needed(image_path)
        except Exception as exc:
            logger.warning(f"Unable to compress image for Bluesky, posting text only: {exc}")

    created_temp = bool(upload_image_path and image_path and upload_image_path != image_path)
    try:
        args = argparse.Namespace(
            pds_url="https://bsky.social",
            handle=handle,
            password=password,
            text=message,
            image=[upload_image_path] if upload_image_path else None,
            alt_text=f"Aircraft photo of {flight_data.get('registration', 'unknown registration')}",
            lang=None,
            reply_to=None,
            embed_url=embed_url,
            embed_ref=None,
            extra_facets=registration_facets,
        )

        create_post(args)
        logger.success(
            f"Successfully posted flight {flight_data.get('flight_name_iata') or flight_data.get('flight_name')} to Bluesky"
        )
    finally:
        if created_temp and upload_image_path and Path(upload_image_path).exists():
            Path(upload_image_path).unlink(missing_ok=True)


async def post_flight_to_bluesky(
    flight_data: dict[str, Any],
    image_path: str | None = None,
    message_text: str | None = None,
    flight_url: str | None = None,
    registration_url: str | None = None,
) -> None:
    await asyncio.to_thread(
        _post_flight_to_bluesky_sync,
        flight_data,
        image_path,
        message_text,
        flight_url,
        registration_url,
    )


async def send_message(context: MessageContext, image_path: str | None = None) -> None:
    await post_flight_to_bluesky(
        context.flight_data,
        image_path,
        context.text,
        context.flight_url,
        context.registration_url,
    )
