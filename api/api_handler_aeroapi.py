from __future__ import annotations

import asyncio
import json
import time

import aiohttp
from loguru import logger

from api.aeroapi_key_manager import AeroApiCredential, mask_key, select_aeroapi_credential
from monitoring.api_usage import record_api_event


async def fetch_aeroapi_scheduled(move, start_time, end_time, airport_icao="LEMD"):
    airport_icao = (airport_icao or "LEMD").upper()
    move = "scheduled_" + move
    endpoint = f"GET /aeroapi/airports/{airport_icao.lower()}/flights/{move}"

    base_url = f"https://aeroapi.flightaware.com/aeroapi/airports/{airport_icao.lower()}/flights/{move}"
    params = {
        "start": start_time,
        "end": end_time,
        "max_pages": 10,
    }

    active_credential = await select_aeroapi_credential(force_usage_refresh=False)
    logger.info(
        f"Using AeroAPI key {active_credential.alias} ({mask_key(active_credential.key)}) for airport {airport_icao}"
    )

    async def fetch_page(session, url, credential: AeroApiCredential):
        retry_count = 0
        max_retries = 5
        base_delay = 20
        excluded_keys: set[str] = set()

        while retry_count < max_retries:
            headers = {
                "Accept": "application/json; charset=UTF-8",
                "x-apikey": credential.key,
            }

            started = time.perf_counter()
            try:
                async with session.get(url, headers=headers, params=params) as response:
                    duration_ms = (time.perf_counter() - started) * 1000.0

                    if response.status in (401, 403):
                        body = await response.text()
                        record_api_event(
                            provider="aeroapi",
                            endpoint=endpoint,
                            method="GET",
                            status_code=response.status,
                            success=False,
                            duration_ms=duration_ms,
                            estimated_cost_usd=0.0,
                            metadata={
                                "key_alias": credential.alias,
                                "key_mask": mask_key(credential.key),
                            },
                            error=f"auth_error: {body}",
                        )

                        excluded_keys.add(credential.key)
                        try:
                            rotated = await select_aeroapi_credential(
                                excluded_keys=excluded_keys,
                                force_usage_refresh=True,
                            )
                            logger.warning(
                                f"AeroAPI auth error with {credential.alias}. Switching to {rotated.alias} ({mask_key(rotated.key)})"
                            )
                            credential = rotated
                            continue
                        except Exception as exc:
                            logger.error(f"No replacement AeroAPI key available after auth error: {exc}")
                            return None, credential

                    if response.status == 429:
                        record_api_event(
                            provider="aeroapi",
                            endpoint=endpoint,
                            method="GET",
                            status_code=response.status,
                            success=False,
                            duration_ms=duration_ms,
                            estimated_cost_usd=0.0,
                            metadata={
                                "key_alias": credential.alias,
                                "key_mask": mask_key(credential.key),
                            },
                            error="rate_limited",
                        )

                        excluded_keys.add(credential.key)
                        try:
                            rotated = await select_aeroapi_credential(
                                excluded_keys=excluded_keys,
                                force_usage_refresh=False,
                            )
                            if rotated.key != credential.key:
                                logger.warning(
                                    f"AeroAPI key {credential.alias} hit rate limit. Rotating to {rotated.alias} ({mask_key(rotated.key)})"
                                )
                                credential = rotated
                                continue
                        except Exception:
                            pass

                        retry_after = int(response.headers.get("Retry-After", base_delay))
                        wait_time = min(retry_after * (2**retry_count), 60)
                        logger.warning(
                            f"AeroAPI rate limited for {credential.alias}. Retrying in {wait_time}s "
                            f"(attempt {retry_count + 1}/{max_retries})"
                        )
                        await asyncio.sleep(wait_time)
                        retry_count += 1
                        continue

                    data = await response.json()
                    success = 200 <= response.status < 300
                    record_api_event(
                        provider="aeroapi",
                        endpoint=endpoint,
                        method="GET",
                        status_code=response.status,
                        success=success,
                        duration_ms=duration_ms,
                        estimated_cost_usd=0.0,
                        metadata={
                            "key_alias": credential.alias,
                            "key_mask": mask_key(credential.key),
                        },
                        error=None if success else str(data),
                    )

                    if not success:
                        retry_count += 1
                        wait_time = min(base_delay * (2**retry_count), 60)
                        logger.warning(
                            f"AeroAPI request failed with status {response.status}. Retrying in {wait_time}s "
                            f"(attempt {retry_count}/{max_retries})"
                        )
                        await asyncio.sleep(wait_time)
                        continue

                    await asyncio.sleep(base_delay)
                    return data, credential

            except aiohttp.ClientError as exc:
                duration_ms = (time.perf_counter() - started) * 1000.0
                record_api_event(
                    provider="aeroapi",
                    endpoint=endpoint,
                    method="GET",
                    status_code=None,
                    success=False,
                    duration_ms=duration_ms,
                    estimated_cost_usd=0.0,
                    metadata={
                        "key_alias": credential.alias,
                        "key_mask": mask_key(credential.key),
                    },
                    error=str(exc),
                )
                retry_count += 1
                wait_time = min(10 * (2**retry_count), 60)
                logger.warning(
                    f"AeroAPI client error ({exc}). Retrying in {wait_time}s "
                    f"(attempt {retry_count}/{max_retries})"
                )
                await asyncio.sleep(wait_time)
            except Exception as exc:
                duration_ms = (time.perf_counter() - started) * 1000.0
                record_api_event(
                    provider="aeroapi",
                    endpoint=endpoint,
                    method="GET",
                    status_code=None,
                    success=False,
                    duration_ms=duration_ms,
                    estimated_cost_usd=0.0,
                    metadata={
                        "key_alias": credential.alias,
                        "key_mask": mask_key(credential.key),
                    },
                    error=str(exc),
                )
                logger.error(f"Unexpected AeroAPI error: {exc}")
                return None, credential

        logger.error(f"Max retries ({max_retries}) reached for URL: {url}")
        return None, credential

    async with aiohttp.ClientSession() as session:
        all_data = {move: []}
        url = base_url
        logger.debug(f"Starting AeroAPI data fetch from {url}")

        while url:
            logger.debug(f"Fetching AeroAPI page from {url}")
            data, active_credential = await fetch_page(session, url, active_credential)
            if not data:
                logger.warning("No data fetched from AeroAPI page")
                break

            params = None
            batch = data.get(move, [])
            if batch:
                logger.success(f"Received {len(batch)} flights in this AeroAPI batch")
                all_data[move].extend(batch)
                links = data.get("links") or {}
                next_url = links.get("next") if isinstance(links, dict) else None
                if next_url:
                    url = f"https://aeroapi.flightaware.com/aeroapi{next_url}"
                    logger.debug(f"Proceeding to AeroAPI next page: {url}")
                else:
                    if links is None:
                        logger.debug("AeroAPI response omitted 'links', ending pagination")
                    url = None
            else:
                logger.warning("AeroAPI returned empty batch, stopping pagination")
                break

        logger.success(f"Total AeroAPI flights collected: {len(all_data[move])}")
        output_path = f"api/data/{airport_icao.lower()}_aeroapi_data_{move}.json"
        with open(output_path, "w", encoding="utf-8") as file_handle:
            json.dump(all_data, file_handle, indent=4)
            logger.debug(f"AeroAPI data saved to {output_path}")
        return all_data
