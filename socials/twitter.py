from __future__ import annotations

import asyncio
import base64
import os
import time
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from loguru import logger

try:
    from xdk import Client
except ModuleNotFoundError:  # pragma: no cover - runtime fallback
    Client = None  # type: ignore[assignment]

from monitoring.api_usage import (
    XBudgetExceededError,
    enforce_budget_or_raise,
    get_endpoint_cost,
    record_api_event,
)
from socials.message_builder import MessageContext, render_flight_message


def _resolve_access_token() -> str | None:
    raw_token = os.getenv("X_ACCESS_TOKEN") or os.getenv("X_USER_ACCESS_TOKEN")
    if not raw_token:
        return None
    return unquote(raw_token.strip())


def _resolve_bearer_token() -> str | None:
    raw_token = os.getenv("X_BEARER_TOKEN") or os.getenv("BEARER_TOKEN")
    if not raw_token:
        return None

    normalized = unquote(raw_token.strip())
    return normalized


def _create_write_client() -> Client | None:
    if Client is None:
        logger.warning("xdk package is not installed; X sender is disabled")
        return None

    access_token = _resolve_access_token()
    if not access_token:
        return None
    return Client(access_token=access_token)


def _create_usage_client() -> Client | None:
    if Client is None:
        logger.warning("xdk package is not installed; X usage sync is disabled")
        return None

    bearer_token = _resolve_bearer_token()
    if not bearer_token:
        return None
    return Client(bearer_token=bearer_token)


def generate_flight_message(flight_data: dict[str, Any], interesting: dict[str, bool] | None = None) -> str:
    return render_flight_message(flight_data, interesting=interesting)


def _record_x_event(
    *,
    endpoint: str,
    status_code: int | None,
    success: bool,
    duration_ms: float,
    estimated_cost_usd: float,
    error: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    record_api_event(
        provider="x",
        endpoint=endpoint,
        method=endpoint.split(" ", 1)[0],
        status_code=status_code,
        success=success,
        duration_ms=duration_ms,
        estimated_cost_usd=estimated_cost_usd,
        error=error,
        metadata=metadata,
    )


def _upload_media(client: Client, image_path: str) -> str | None:
    endpoint = "POST /1.1/media/upload.json"
    decision = enforce_budget_or_raise("x", endpoint)
    started = time.perf_counter()

    try:
        with open(image_path, "rb") as file_handle:
            media_data = base64.b64encode(file_handle.read()).decode("utf-8")

        response = client.media.upload_media(body={"media_data": media_data})
        duration_ms = (time.perf_counter() - started) * 1000.0
        data = getattr(response, "data", {}) or {}
        media_id = data.get("media_id_string") or data.get("media_id")

        _record_x_event(
            endpoint=endpoint,
            status_code=200,
            success=bool(media_id),
            duration_ms=duration_ms,
            estimated_cost_usd=decision.estimated_cost_usd,
            metadata={"has_media_id": bool(media_id)},
        )

        if not media_id:
            logger.warning("X media upload succeeded without media_id in response")
            return None

        return str(media_id)
    except Exception as exc:
        duration_ms = (time.perf_counter() - started) * 1000.0
        _record_x_event(
            endpoint=endpoint,
            status_code=None,
            success=False,
            duration_ms=duration_ms,
            estimated_cost_usd=decision.estimated_cost_usd,
            error=str(exc),
        )
        raise


def _create_post(
    client: Client,
    message: str,
    media_id: str | None,
) -> dict[str, Any] | None:
    endpoint = "POST /2/tweets"
    decision = enforce_budget_or_raise("x", endpoint)
    payload: dict[str, Any] = {"text": message}
    if media_id:
        payload["media"] = {"media_ids": [media_id]}

    started = time.perf_counter()
    try:
        response = client.posts.create(body=payload)
        duration_ms = (time.perf_counter() - started) * 1000.0
        data = getattr(response, "data", None)
        _record_x_event(
            endpoint=endpoint,
            status_code=201,
            success=True,
            duration_ms=duration_ms,
            estimated_cost_usd=decision.estimated_cost_usd,
            metadata={"has_response_data": bool(data)},
        )
        return data if isinstance(data, dict) else None
    except Exception as exc:
        duration_ms = (time.perf_counter() - started) * 1000.0
        _record_x_event(
            endpoint=endpoint,
            status_code=None,
            success=False,
            duration_ms=duration_ms,
            estimated_cost_usd=decision.estimated_cost_usd,
            error=str(exc),
        )
        raise


def sync_usage(days: int = 7) -> dict[str, Any] | None:
    endpoint = "GET /2/usage/tweets"
    client = _create_usage_client()
    if client is None:
        logger.debug("X usage sync skipped: X_BEARER_TOKEN/BEARER_TOKEN is not configured")
        return None

    cost = get_endpoint_cost("x", endpoint)
    started = time.perf_counter()
    try:
        response = client.usage.get(days=days)
        duration_ms = (time.perf_counter() - started) * 1000.0
        data = getattr(response, "data", None)
        _record_x_event(
            endpoint=endpoint,
            status_code=200,
            success=True,
            duration_ms=duration_ms,
            estimated_cost_usd=cost,
            metadata={"days": days},
        )
        return data if isinstance(data, dict) else None
    except Exception as exc:
        duration_ms = (time.perf_counter() - started) * 1000.0
        _record_x_event(
            endpoint=endpoint,
            status_code=None,
            success=False,
            duration_ms=duration_ms,
            estimated_cost_usd=cost,
            error=str(exc),
            metadata={"days": days},
        )
        logger.warning(f"Unable to sync X usage endpoint: {exc}")
        return None


def post_to_twitter(
    flight_data: dict[str, Any],
    image_path: str | None = None,
    message_text: str | None = None,
) -> dict[str, Any] | None:
    client = _create_write_client()
    if client is None:
        logger.warning("X posting skipped: X_ACCESS_TOKEN is not configured")
        return None

    message = message_text or generate_flight_message(flight_data)
    media_id: str | None = None

    try:
        if image_path and Path(image_path).exists() and flight_data.get("registration") not in (None, "null"):
            media_id = _upload_media(client, image_path)

        response_data = _create_post(client, message, media_id)
        logger.success(
            f"Successfully posted flight {flight_data.get('flight_name_iata') or flight_data.get('flight_name')} to X"
        )

        if os.getenv("X_USAGE_SYNC_ENABLED", "true").strip().lower() == "true":
            sync_usage(days=int(os.getenv("X_USAGE_SYNC_DAYS", "7")))

        return response_data
    except XBudgetExceededError as exc:
        logger.warning(f"Skipping X post due to budget guard: {exc}")
        return None


async def send_message(context: MessageContext, image_path: str | None = None) -> None:
    await asyncio.to_thread(
        post_to_twitter,
        context.flight_data,
        image_path,
        context.text,
    )
