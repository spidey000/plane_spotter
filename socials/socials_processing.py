import asyncio
import sys
import time
import tempfile
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
from socials.message_builder import MessageContext, build_message_context, build_platform_context
from socials.message_policy import resolve_message_for_platform
from utils.image_finder import get_first_image_url_jp, get_first_image_url_pp
import os


PlatformSender = Callable[[MessageContext, str | None], Awaitable[None]]

_DEFAULT_IMAGE_PROVIDER_ORDER = ("jetphotos", "planespotters")


def _build_sender_registry() -> dict[str, PlatformSender]:
    return {
        "telegram": tg.send_message,
        "bluesky": bs.send_message,
        "twitter": tw.send_message,
        "threads": th.send_message,
        "instagram": ig.send_message,
        "linkedin": li.send_message,
    }


def _as_int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _load_image_download_config() -> dict[str, object]:
    raw = cfg.get_config("image_finder") or {}
    if not isinstance(raw, dict):
        raw = {}

    allowed_hosts_raw = raw.get(
        "allowed_image_hosts",
        [
            "jetphotos.com",
            "cdn.jetphotos.com",
            "planespotters.net",
            "plnspttrs.net",
            "t.plnspttrs.net",
        ],
    )
    allowed_hosts = []
    if isinstance(allowed_hosts_raw, list):
        for item in allowed_hosts_raw:
            host = str(item).strip().lower()
            if host:
                allowed_hosts.append(host)

    return {
        "timeout_seconds": max(1.0, _as_float(raw.get("download_timeout_seconds"), 30.0)),
        "max_bytes": max(256 * 1024, _as_int(raw.get("download_max_bytes"), 5 * 1024 * 1024)),
        "allowed_hosts": allowed_hosts,
    }


def _is_allowed_image_host(image_url: str, allowed_hosts: list[str]) -> bool:
    parsed = urlparse(image_url)
    if parsed.scheme not in ("http", "https"):
        return False

    host = parsed.netloc.lower().split(":", 1)[0]
    if not host:
        return False

    for allowed in allowed_hosts:
        if host == allowed or host.endswith(f".{allowed}"):
            return True
    return False


def _is_valid_registration(value: object) -> bool:
    if value is None:
        return False
    normalized = str(value).strip()
    if not normalized:
        return False
    return normalized.lower() not in {"null", "none"}


def _resolve_image_provider_order() -> list[str]:
    providers = cfg.get_config("image_finder.providers")
    if not isinstance(providers, list):
        return list(_DEFAULT_IMAGE_PROVIDER_ORDER)

    normalized: list[str] = []
    for provider in providers:
        candidate = str(provider).strip().lower()
        if candidate and candidate not in normalized:
            normalized.append(candidate)

    if not normalized:
        return list(_DEFAULT_IMAGE_PROVIDER_ORDER)
    return normalized


def _download_image(image_url: str, temp_dir: str = "socials") -> str | None:
    parsed = urlparse(image_url)
    endpoint = f"GET {parsed.netloc}{parsed.path}"
    config = _load_image_download_config()

    allowed_hosts = config["allowed_hosts"]
    if isinstance(allowed_hosts, list) and allowed_hosts and not _is_allowed_image_host(image_url, allowed_hosts):
        record_api_event(
            provider="image-cdn",
            endpoint=endpoint,
            method="GET",
            status_code=None,
            success=False,
            duration_ms=0.0,
            estimated_cost_usd=0.0,
            error="disallowed_image_host",
            metadata={"host": parsed.netloc.lower()},
        )
        logger.warning(f"Skipping image download from disallowed host: {parsed.netloc}")
        return None

    started = time.perf_counter()
    temp_image_path = None

    try:
        with requests.get(
            image_url,
            timeout=float(config["timeout_seconds"]),
            stream=True,
        ) as response:
            duration_ms = (time.perf_counter() - started) * 1000.0
            if response.status_code != 200:
                record_api_event(
                    provider="image-cdn",
                    endpoint=endpoint,
                    method="GET",
                    status_code=response.status_code,
                    success=False,
                    duration_ms=duration_ms,
                    estimated_cost_usd=0.0,
                )
                return None

            content_type = str(response.headers.get("Content-Type", "")).lower()
            if not content_type.startswith("image/"):
                record_api_event(
                    provider="image-cdn",
                    endpoint=endpoint,
                    method="GET",
                    status_code=response.status_code,
                    success=False,
                    duration_ms=duration_ms,
                    estimated_cost_usd=0.0,
                    error="invalid_content_type",
                    metadata={"content_type": content_type},
                )
                logger.warning(f"Rejected non-image content from {image_url}: {content_type}")
                return None

            os.makedirs(temp_dir, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="wb",
                suffix=".jpg",
                prefix="temp_image_",
                dir=temp_dir,
                delete=False,
            ) as temp_file:
                temp_image_path = temp_file.name
                bytes_written = 0
                max_bytes = int(config["max_bytes"])
                for chunk in response.iter_content(chunk_size=64 * 1024):
                    if not chunk:
                        continue
                    bytes_written += len(chunk)
                    if bytes_written > max_bytes:
                        temp_file.close()
                        Path(temp_image_path).unlink(missing_ok=True)
                        record_api_event(
                            provider="image-cdn",
                            endpoint=endpoint,
                            method="GET",
                            status_code=response.status_code,
                            success=False,
                            duration_ms=duration_ms,
                            estimated_cost_usd=0.0,
                            error="image_too_large",
                            metadata={"max_bytes": max_bytes, "bytes_written": bytes_written},
                        )
                        logger.warning(
                            f"Rejected oversized image ({bytes_written} bytes > {max_bytes}) from {image_url}"
                        )
                        return None
                    temp_file.write(chunk)

            record_api_event(
                provider="image-cdn",
                endpoint=endpoint,
                method="GET",
                status_code=response.status_code,
                success=True,
                duration_ms=duration_ms,
                estimated_cost_usd=0.0,
                metadata={"content_type": content_type, "bytes": bytes_written},
            )
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
        if temp_image_path:
            Path(temp_image_path).unlink(missing_ok=True)
        logger.warning(f"Unable to download image from {image_url}: {exc}")
        return None


async def call_socials(flight_data, interesting):
    logger.debug(f"Starting socials processing for flight {flight_data['flight_name']}")
    context = build_message_context(flight_data, interesting=interesting)
    sender_registry = _build_sender_registry()

    temp_image_path = None
    image_provider = None

    try:
        registration = flight_data.get("registration")
        image_url = None
        if _is_valid_registration(registration):
            provider_order = _resolve_image_provider_order()
            for provider in provider_order:
                if provider == "jetphotos":
                    logger.debug(f"Fetching image for registration {registration} from JetPhotos")
                    resolver = get_first_image_url_jp
                elif provider == "planespotters":
                    logger.debug(f"Fetching image for registration {registration} from Planespotters")
                    resolver = get_first_image_url_pp
                else:
                    logger.warning(f"Unsupported image provider '{provider}' in config, skipping")
                    continue

                image_url = await asyncio.to_thread(resolver, registration)
                if image_url:
                    image_provider = provider
                    break

                logger.debug(f"No image found on {provider}")

        if image_url:
            logger.debug(
                f"Found image at {image_url} from {image_provider or 'unknown-provider'}, downloading..."
            )
            temp_image_path = await asyncio.to_thread(_download_image, image_url, "socials")
            if temp_image_path:
                logger.debug(f"Image saved to {temp_image_path}")

        social_config = cfg.get_config("social_networks") or {}
        has_media_attachment = bool(
            temp_image_path
            and os.path.exists(temp_image_path)
            and _is_valid_registration(flight_data.get("registration"))
        )

        for platform_name, sender in sender_registry.items():
            if not social_config.get(platform_name, False):
                logger.debug(f"Skipping disabled platform '{platform_name}'")
                continue

            decision = resolve_message_for_platform(
                platform_name,
                context,
                has_image=platform_name == "telegram" and has_media_attachment,
            )
            if decision.blocked or not decision.text:
                logger.warning(
                    f"Skipping {platform_name}: message blocked by policy. reason={decision.reason}"
                )
                record_api_event(
                    provider="message-policy",
                    endpoint=f"SELECT /{platform_name}",
                    method="SELECT",
                    status_code=None,
                    success=False,
                    blocked=True,
                    duration_ms=0.0,
                    estimated_cost_usd=0.0,
                    error=decision.reason,
                    metadata={
                        "platform": platform_name,
                        "preferred_profile": decision.preferred_profile,
                        "selected_profile": decision.selected_profile,
                        "limit": decision.limit,
                        "lengths_by_profile": decision.lengths_by_profile,
                    },
                )
                continue

            if decision.used_fallback:
                logger.info(
                    f"Message fallback for {platform_name}: preferred={decision.preferred_profile}, "
                    f"selected={decision.selected_profile}, limit={decision.limit}"
                )

            platform_context = build_platform_context(
                context,
                platform=platform_name,
                profile=decision.selected_profile or decision.preferred_profile,
                text=decision.text,
            )

            try:
                await sender(platform_context, image_path=temp_image_path)
            except Exception as exc:
                logger.error(f"Failed while sending message to {platform_name}: {exc}")

    finally:
        # Clean up temporary image
        if temp_image_path and os.path.exists(temp_image_path):
            os.remove(temp_image_path)
            logger.debug(f"Removed temporary image {temp_image_path}")
