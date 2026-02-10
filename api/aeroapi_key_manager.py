from __future__ import annotations

import asyncio
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import aiohttp
from loguru import logger

import config.config as cfg
from monitoring.api_usage import record_api_event


USAGE_ENDPOINT_URL = "https://aeroapi.flightaware.com/aeroapi/account/usage"
_DEFAULT_MONTHLY_BUDGET_USD = 5.0
_DEFAULT_USAGE_CACHE_TTL_SECONDS = 600


@dataclass(frozen=True)
class AeroApiCredential:
    alias: str
    key: str
    total_cost_usd: float | None = None


_USAGE_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_ROUND_ROBIN_INDEX = 0
_STATE_LOCK = asyncio.Lock()


def mask_key(api_key: str) -> str:
    if len(api_key) < 8:
        return "***"
    return f"{api_key[:4]}...{api_key[-4:]}"


def _split_tokens(raw: str) -> list[str]:
    tokens = [token.strip() for token in re.split(r"[,;\n]", raw) if token.strip()]
    return tokens


def _parse_key_token(token: str, default_alias: str) -> AeroApiCredential:
    for separator in (":", "="):
        if separator in token:
            left, right = token.split(separator, 1)
            alias = left.strip() or default_alias
            key = right.strip()
            if key:
                return AeroApiCredential(alias=alias, key=key)

    return AeroApiCredential(alias=default_alias, key=token.strip())


def _load_credentials() -> list[AeroApiCredential]:
    credentials: list[AeroApiCredential] = []

    raw_multiple = os.getenv("AEROAPI_KEYS", "")
    if raw_multiple.strip():
        tokens = _split_tokens(raw_multiple)
        for index, token in enumerate(tokens, start=1):
            credentials.append(_parse_key_token(token, default_alias=f"key{index}"))

    raw_single = os.getenv("AEROAPI_KEY", "").strip()
    if raw_single:
        credentials.append(AeroApiCredential(alias=f"key{len(credentials) + 1}", key=raw_single))

    deduped: list[AeroApiCredential] = []
    seen: set[str] = set()
    for credential in credentials:
        normalized_key = credential.key.strip()
        if not normalized_key or normalized_key in seen:
            continue
        seen.add(normalized_key)
        deduped.append(AeroApiCredential(alias=credential.alias, key=normalized_key))

    if not deduped and os.getenv("PYTEST_CURRENT_TEST"):
        return [AeroApiCredential(alias="test-key", key="test-key")]

    return deduped


def _as_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _monthly_budget_usd() -> float:
    env_value = os.getenv("AEROAPI_MONTHLY_BUDGET_USD")
    if env_value:
        return _as_float(env_value, _DEFAULT_MONTHLY_BUDGET_USD)

    config_value = cfg.get_config("api.aeroapi.monthly_budget_per_key_usd")
    return _as_float(config_value, _DEFAULT_MONTHLY_BUDGET_USD)


def _usage_cache_ttl_seconds() -> int:
    env_value = os.getenv("AEROAPI_USAGE_CACHE_TTL_SECONDS")
    if env_value:
        return int(_as_float(env_value, _DEFAULT_USAGE_CACHE_TTL_SECONDS))

    config_value = cfg.get_config("api.aeroapi.usage_cache_ttl_seconds")
    return int(_as_float(config_value, _DEFAULT_USAGE_CACHE_TTL_SECONDS))


def _default_usage_window() -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return month_start.strftime("%Y-%m-%dT%H:%M:%SZ"), now.strftime("%Y-%m-%dT%H:%M:%SZ")


async def _fetch_usage_for_key(
    credential: AeroApiCredential,
    *,
    force_refresh: bool = False,
) -> dict[str, Any] | None:
    ttl_seconds = _usage_cache_ttl_seconds()
    now_ts = time.time()
    cache_entry = _USAGE_CACHE.get(credential.key)
    if cache_entry and not force_refresh:
        cached_ts, cached_payload = cache_entry
        if (now_ts - cached_ts) <= ttl_seconds:
            return cached_payload

    start, end = _default_usage_window()
    params = {
        "start": start,
        "end": end,
        "all_keys": "false",
    }
    headers = {
        "Accept": "application/json; charset=UTF-8",
        "x-apikey": credential.key,
    }

    started = time.perf_counter()
    status_code: int | None = None

    try:
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(USAGE_ENDPOINT_URL, headers=headers, params=params) as response:
                status_code = response.status
                duration_ms = (time.perf_counter() - started) * 1000.0

                payload = await response.json()
                success = 200 <= response.status < 300
                total_cost = _as_float(payload.get("total_cost"), 0.0)
                total_calls = int(payload.get("total_calls", 0) or 0)

                record_api_event(
                    provider="aeroapi",
                    endpoint="GET /aeroapi/account/usage",
                    method="GET",
                    status_code=status_code,
                    success=success,
                    duration_ms=duration_ms,
                    estimated_cost_usd=0.0,
                    metadata={
                        "key_alias": credential.alias,
                        "key_mask": mask_key(credential.key),
                        "total_cost_usd": total_cost,
                        "total_calls": total_calls,
                        "window_start": start,
                        "window_end": end,
                    },
                    error=None if success else str(payload),
                )

                if not success:
                    logger.warning(
                        f"AeroAPI usage endpoint failed for {credential.alias} ({mask_key(credential.key)}): {payload}"
                    )
                    return None

                usage = {
                    "total_cost_usd": total_cost,
                    "total_calls": total_calls,
                    "raw": payload,
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                }
                _USAGE_CACHE[credential.key] = (now_ts, usage)
                return usage
    except Exception as exc:
        duration_ms = (time.perf_counter() - started) * 1000.0
        record_api_event(
            provider="aeroapi",
            endpoint="GET /aeroapi/account/usage",
            method="GET",
            status_code=status_code,
            success=False,
            duration_ms=duration_ms,
            estimated_cost_usd=0.0,
            metadata={
                "key_alias": credential.alias,
                "key_mask": mask_key(credential.key),
                "window_start": start,
                "window_end": end,
            },
            error=str(exc),
        )
        logger.warning(
            f"Unable to read AeroAPI usage for {credential.alias} ({mask_key(credential.key)}): {exc}"
        )
        return None


async def select_aeroapi_credential(
    *,
    excluded_keys: set[str] | None = None,
    force_usage_refresh: bool = False,
) -> AeroApiCredential:
    global _ROUND_ROBIN_INDEX

    credentials = _load_credentials()
    if not credentials:
        raise RuntimeError("Missing AeroAPI credentials. Set AEROAPI_KEY or AEROAPI_KEYS in .env")

    excluded = excluded_keys or set()
    budget_usd = _monthly_budget_usd()

    async with _STATE_LOCK:
        start_index = _ROUND_ROBIN_INDEX % len(credentials)
        exhausted: list[str] = []

        for offset in range(len(credentials)):
            idx = (start_index + offset) % len(credentials)
            credential = credentials[idx]
            if credential.key in excluded:
                continue

            usage = await _fetch_usage_for_key(credential, force_refresh=force_usage_refresh)
            if usage is None:
                _ROUND_ROBIN_INDEX = (idx + 1) % len(credentials)
                logger.info(
                    f"Selected AeroAPI key {credential.alias} ({mask_key(credential.key)}) without fresh usage data"
                )
                return AeroApiCredential(
                    alias=credential.alias,
                    key=credential.key,
                    total_cost_usd=None,
                )

            total_cost = _as_float(usage.get("total_cost_usd"), 0.0)
            if total_cost >= budget_usd:
                exhausted.append(f"{credential.alias}:{total_cost:.2f}")
                continue

            _ROUND_ROBIN_INDEX = (idx + 1) % len(credentials)
            logger.info(
                f"Selected AeroAPI key {credential.alias} ({mask_key(credential.key)}), monthly cost ${total_cost:.2f}/${budget_usd:.2f}"
            )
            return AeroApiCredential(
                alias=credential.alias,
                key=credential.key,
                total_cost_usd=total_cost,
            )

    exhausted_text = ", ".join(exhausted) if exhausted else "no eligible key"
    raise RuntimeError(
        f"No AeroAPI keys available under monthly budget ${budget_usd:.2f}. Details: {exhausted_text}"
    )


async def get_aeroapi_usage_snapshot(force_refresh: bool = True) -> list[dict[str, Any]]:
    snapshots: list[dict[str, Any]] = []
    credentials = _load_credentials()
    for credential in credentials:
        usage = await _fetch_usage_for_key(credential, force_refresh=force_refresh)
        snapshots.append(
            {
                "alias": credential.alias,
                "key_mask": mask_key(credential.key),
                "total_cost_usd": None if usage is None else usage.get("total_cost_usd"),
                "total_calls": None if usage is None else usage.get("total_calls"),
                "fetched_at": None if usage is None else usage.get("fetched_at"),
            }
        )
    return snapshots
