from __future__ import annotations

import random
import threading
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import cloudscraper
from bs4 import BeautifulSoup
from loguru import logger

import config.config as cfg
from monitoring.api_usage import record_api_event


JETPHOTOS_PROVIDER = "jetphotos"
PLANESPOTTERS_PROVIDER = "planespotters"
_RETRYABLE_STATUS_CODES = {403, 429, 500, 502, 503, 504}
_NULLISH_VALUES = {None, "", "null", "none"}
_DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64; rv:135.0) Gecko/20100101 Firefox/135.0"
)

_RUNTIME_LOCK = threading.Lock()
_URL_CACHE: dict[str, tuple[float, str | None]] = {}
_PROVIDER_COOLDOWNS: dict[str, float] = {}
_CACHE_MISS = object()


@dataclass(frozen=True)
class LookupResult:
    url: str | None
    reason: str


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _load_image_finder_config() -> dict[str, Any]:
    raw = cfg.get_config("image_finder") or {}
    if not isinstance(raw, dict):
        raw = {}

    providers_raw = raw.get("providers", [JETPHOTOS_PROVIDER, PLANESPOTTERS_PROVIDER])
    providers: list[str] = []
    if isinstance(providers_raw, list):
        for provider in providers_raw:
            normalized = str(provider).strip().lower()
            if normalized:
                providers.append(normalized)

    if not providers:
        providers = [JETPHOTOS_PROVIDER, PLANESPOTTERS_PROVIDER]

    return {
        "enabled": bool(raw.get("enabled", True)),
        "providers": providers,
        "request_timeout_seconds": _as_float(raw.get("request_timeout_seconds"), 15.0),
        "max_retries": max(1, _as_int(raw.get("max_retries"), 3)),
        "base_delay_seconds": max(0.0, _as_float(raw.get("base_delay_seconds"), 1.5)),
        "max_delay_seconds": max(0.0, _as_float(raw.get("max_delay_seconds"), 10.0)),
        "jitter_seconds": max(0.0, _as_float(raw.get("jitter_seconds"), 0.5)),
        "positive_cache_ttl_seconds": max(0.0, _as_float(raw.get("positive_cache_ttl_seconds"), 6 * 60 * 60)),
        "negative_cache_ttl_seconds": max(0.0, _as_float(raw.get("negative_cache_ttl_seconds"), 20 * 60)),
        "provider_cooldown_seconds": max(0.0, _as_float(raw.get("provider_cooldown_seconds"), 10 * 60)),
        "user_agent": str(raw.get("user_agent") or _DEFAULT_USER_AGENT),
    }


def _normalize_registration(registration: Any) -> str | None:
    if registration is None:
        return None
    normalized = str(registration).strip().upper()
    if normalized.lower() in _NULLISH_VALUES:
        return None
    return normalized or None


def _build_headers(*, referer: str, user_agent: str) -> dict[str, str]:
    return {
        "User-Agent": user_agent,
        "Referer": referer,
        "Accept-Language": "en-US,en;q=0.9",
    }


def _normalized_alnum(value: str) -> str:
    return "".join(char for char in value.upper() if char.isalnum())


def _matches_registration(value: str | None, registration: str) -> bool:
    if not value:
        return False
    registration_key = _normalized_alnum(registration)
    if not registration_key:
        return False
    return registration_key in _normalized_alnum(value)


def _host_matches(url: str, valid_hosts: tuple[str, ...]) -> bool:
    host = (urlparse(url).netloc or "").lower()
    if not host:
        return False
    for candidate in valid_hosts:
        if host == candidate or host.endswith(f".{candidate}"):
            return True
    return False


def _build_candidate_context(img_tag) -> str:
    text_parts: list[str] = []
    for attr in ("alt", "title"):
        value = img_tag.get(attr)
        if value:
            text_parts.append(str(value))

    for parent_tag in (
        img_tag.find_parent("a"),
        img_tag.find_parent("article"),
        img_tag.find_parent("li"),
        img_tag.find_parent("div"),
    ):
        if parent_tag is None:
            continue
        parent_text = parent_tag.get_text(" ", strip=True)
        if parent_text:
            text_parts.append(parent_text)
            break

    return " ".join(text_parts)


def _select_best_image_url(
    *,
    candidates: list[tuple[str, str]],
    registration: str,
    valid_hosts: tuple[str, ...],
) -> str | None:
    best_url: str | None = None
    best_score = -1
    seen: set[str] = set()

    for candidate_url, context_text in candidates:
        if candidate_url in seen:
            continue
        seen.add(candidate_url)

        if not _host_matches(candidate_url, valid_hosts):
            continue

        score = 1
        if _matches_registration(context_text, registration):
            score += 10
        if _matches_registration(candidate_url, registration):
            score += 2

        if score > best_score:
            best_score = score
            best_url = candidate_url

    return best_url


def _record_image_event(
    provider: str,
    endpoint: str,
    status_code: int | None,
    success: bool,
    duration_ms: float,
    *,
    error: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    record_api_event(
        provider=provider,
        endpoint=endpoint,
        method="GET",
        status_code=status_code,
        success=success,
        duration_ms=duration_ms,
        estimated_cost_usd=0.0,
        error=error,
        metadata=metadata,
    )


def _endpoint_for(provider: str) -> str:
    if provider == JETPHOTOS_PROVIDER:
        return "GET /jetphotos/showphotos.php"
    if provider == PLANESPOTTERS_PROVIDER:
        return "GET /planespotters/photos/reg/{registration}"
    return "GET /image-search"


def _is_provider_in_cooldown(provider: str) -> bool:
    now = time.monotonic()
    with _RUNTIME_LOCK:
        cooldown_until = _PROVIDER_COOLDOWNS.get(provider, 0.0)
        if cooldown_until <= now:
            _PROVIDER_COOLDOWNS.pop(provider, None)
            return False
        return True


def _set_provider_cooldown(provider: str, cooldown_seconds: float) -> None:
    if cooldown_seconds <= 0:
        return
    with _RUNTIME_LOCK:
        _PROVIDER_COOLDOWNS[provider] = time.monotonic() + cooldown_seconds


def _cache_get(cache_key: str) -> str | None | object:
    now = time.monotonic()
    with _RUNTIME_LOCK:
        cached = _URL_CACHE.get(cache_key)
        if not cached:
            return _CACHE_MISS
        expires_at, value = cached
        if expires_at <= now:
            _URL_CACHE.pop(cache_key, None)
            return _CACHE_MISS
        return value


def _cache_set(cache_key: str, value: str | None, ttl_seconds: float) -> None:
    if ttl_seconds <= 0:
        return
    expires_at = time.monotonic() + ttl_seconds
    with _RUNTIME_LOCK:
        _URL_CACHE[cache_key] = (expires_at, value)


def clear_image_finder_runtime_state() -> None:
    with _RUNTIME_LOCK:
        _URL_CACHE.clear()
        _PROVIDER_COOLDOWNS.clear()


def _backoff_delay_seconds(
    attempt: int,
    *,
    base_delay_seconds: float,
    max_delay_seconds: float,
    jitter_seconds: float,
    retry_after_seconds: float | None = None,
) -> float:
    if retry_after_seconds is not None:
        delay = retry_after_seconds
    else:
        delay = base_delay_seconds * (2**attempt)

    if max_delay_seconds > 0:
        delay = min(delay, max_delay_seconds)

    if jitter_seconds > 0:
        delay += random.uniform(0.0, jitter_seconds)

    return max(0.0, delay)


def _extract_retry_after_seconds(value: str | None) -> float | None:
    if not value:
        return None
    try:
        parsed = float(value)
        if parsed < 0:
            return None
        return parsed
    except ValueError:
        return None


def _contains_antibot_challenge(html_text: str) -> bool:
    lowered = html_text.lower()
    markers = (
        "captcha",
        "verify you are human",
        "challenge-platform",
        "cf-challenge",
    )
    return any(marker in lowered for marker in markers)


def _normalize_image_url(raw_url: str | None, *, base_url: str) -> str | None:
    if not raw_url:
        return None

    url = raw_url.strip()
    if not url:
        return None

    if url.startswith("//"):
        url = f"https:{url}"
    elif url.startswith("/"):
        url = f"{base_url.rstrip('/')}{url}"
    elif not url.startswith("http"):
        url = f"{base_url.rstrip('/')}/{url.lstrip('/')}"

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return None
    if not parsed.netloc:
        return None

    return url


def _extract_image_src(img_tag) -> str | None:
    if img_tag is None:
        return None

    for attr in ("src", "data-src", "data-lazy-src"):
        value = img_tag.get(attr)
        if value:
            return value

    srcset = img_tag.get("srcset")
    if not srcset:
        return None

    candidates: list[tuple[int, str]] = []
    for item in srcset.split(","):
        parts = item.strip().split()
        if not parts:
            continue
        candidate_url = parts[0]
        width = 0
        if len(parts) > 1 and parts[1].endswith("w"):
            try:
                width = int(parts[1][:-1])
            except ValueError:
                width = 0
        candidates.append((width, candidate_url))

    if not candidates:
        return None

    candidates.sort(reverse=True)
    return candidates[0][1]


def _parse_html(html_text: str) -> BeautifulSoup:
    try:
        return BeautifulSoup(html_text, "lxml")
    except Exception:
        return BeautifulSoup(html_text, "html.parser")


def _parse_jetphotos_image_url(html_text: str, registration: str) -> str | None:
    soup = _parse_html(html_text)
    candidates = [
        *soup.select("img.result__photo"),
        *soup.select("a.result__photoLink img"),
        *soup.select("img.result-photo__img"),
        *soup.select("a[href*='/photo/'] img[src*='cdn.jetphotos.com']"),
    ]
    extracted: list[tuple[str, str]] = []
    for candidate in candidates:
        src = _extract_image_src(candidate)
        url = _normalize_image_url(src, base_url="https://www.jetphotos.com")
        if not url:
            continue
        extracted.append((url, _build_candidate_context(candidate)))

    best = _select_best_image_url(
        candidates=extracted,
        registration=registration,
        valid_hosts=("cdn.jetphotos.com",),
    )
    if not best:
        return None
    return best.replace("/400/", "/full/")


def _parse_planespotters_image_url(html_text: str, registration: str) -> str | None:
    soup = _parse_html(html_text)
    candidates = [
        *soup.select("img.photo_card__photo"),
        *soup.select("div.photo_card img"),
        *soup.select("img[data-photo-id]"),
        *soup.select("a[href*='/photo/'] img"),
        *soup.select("img[src*='t.plnspttrs.net/']"),
    ]

    extracted: list[tuple[str, str]] = []
    for candidate in candidates:
        src = _extract_image_src(candidate)
        url = _normalize_image_url(src, base_url="https://www.planespotters.net")
        if not url:
            continue
        extracted.append((url, _build_candidate_context(candidate)))

    return _select_best_image_url(
        candidates=extracted,
        registration=registration,
        valid_hosts=("t.plnspttrs.net", "plnspttrs.net"),
    )


def _request_with_retry(
    *,
    provider: str,
    request_url: str,
    params: dict[str, str],
    headers: dict[str, str] | None,
    registration: str,
    config: dict[str, Any],
) -> LookupResult:
    scraper = cloudscraper.create_scraper()
    endpoint = _endpoint_for(provider)

    if _is_provider_in_cooldown(provider):
        logger.warning(f"Skipping {provider} lookup for {registration}: provider in cooldown")
        return LookupResult(url=None, reason="provider_cooldown")

    max_retries = config["max_retries"]
    request_timeout = config["request_timeout_seconds"]

    for attempt in range(max_retries):
        started = time.perf_counter()
        try:
            request_kwargs: dict[str, Any] = {
                "params": params,
                "timeout": request_timeout,
            }
            if headers:
                request_kwargs["headers"] = headers
            response = scraper.get(request_url, **request_kwargs)
            duration_ms = (time.perf_counter() - started) * 1000.0
        except Exception as exc:
            duration_ms = (time.perf_counter() - started) * 1000.0
            _record_image_event(
                provider,
                endpoint,
                None,
                False,
                duration_ms,
                error=str(exc),
                metadata={"attempt": attempt + 1, "registration": registration},
            )
            if attempt >= max_retries - 1:
                logger.warning(f"{provider} request failed for {registration}: {exc}")
                return LookupResult(url=None, reason="request_exception")

            sleep_seconds = _backoff_delay_seconds(
                attempt,
                base_delay_seconds=config["base_delay_seconds"],
                max_delay_seconds=config["max_delay_seconds"],
                jitter_seconds=config["jitter_seconds"],
            )
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)
            continue

        status_code = response.status_code
        success = 200 <= status_code < 300
        _record_image_event(
            provider,
            endpoint,
            status_code,
            success,
            duration_ms,
            metadata={"attempt": attempt + 1, "registration": registration},
        )

        if status_code == 200:
            if _contains_antibot_challenge(response.text):
                _record_image_event(
                    provider,
                    endpoint,
                    status_code,
                    False,
                    duration_ms,
                    error="captcha_detected",
                    metadata={"attempt": attempt + 1, "registration": registration},
                )
                if attempt < max_retries - 1:
                    sleep_seconds = _backoff_delay_seconds(
                        attempt,
                        base_delay_seconds=config["base_delay_seconds"],
                        max_delay_seconds=config["max_delay_seconds"],
                        jitter_seconds=config["jitter_seconds"],
                    )
                    logger.warning(
                        f"{provider} anti-bot challenge for {registration}. "
                        f"Retrying in {sleep_seconds:.1f}s (attempt {attempt + 1}/{max_retries})"
                    )
                    if sleep_seconds > 0:
                        time.sleep(sleep_seconds)
                    continue
                _set_provider_cooldown(provider, config["provider_cooldown_seconds"])
                return LookupResult(url=None, reason="captcha_detected")
            return LookupResult(url=response.text, reason="ok")

        if status_code in (403, 429) and attempt >= max_retries - 1:
            _set_provider_cooldown(provider, config["provider_cooldown_seconds"])

        should_retry = status_code in _RETRYABLE_STATUS_CODES and attempt < max_retries - 1
        if should_retry:
            retry_after = _extract_retry_after_seconds(response.headers.get("Retry-After"))
            sleep_seconds = _backoff_delay_seconds(
                attempt,
                base_delay_seconds=config["base_delay_seconds"],
                max_delay_seconds=config["max_delay_seconds"],
                jitter_seconds=config["jitter_seconds"],
                retry_after_seconds=retry_after,
            )
            logger.warning(
                f"{provider} returned HTTP {status_code} for {registration}. "
                f"Retrying in {sleep_seconds:.1f}s (attempt {attempt + 1}/{max_retries})"
            )
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)
            continue

        return LookupResult(url=None, reason=f"http_{status_code}")

    return LookupResult(url=None, reason="max_retries_exceeded")


def _lookup_provider_image_url(provider: str, registration: str, config: dict[str, Any]) -> LookupResult:
    cache_key = f"{provider}:{registration}"
    cached = _cache_get(cache_key)
    if cached is not _CACHE_MISS:
        if cached:
            return LookupResult(url=cached, reason="cache_hit")
        return LookupResult(url=None, reason="negative_cache_hit")

    if provider == JETPHOTOS_PROVIDER:
        params = {
            "aircraft": "all",
            "airline": "all",
            "category": "all",
            "country-location": "all",
            "genre": "all",
            "keywords-contain": "1",
            "keywords-type": "all",
            "keywords": registration,
            "photo-year": "all",
            "photographer-group": "all",
            "search-type": "Advanced",
            "sort-order": "0",
            "page": "1",
        }
        request_result = _request_with_retry(
            provider=provider,
            request_url="https://www.jetphotos.com/showphotos.php",
            params=params,
            headers=None,
            registration=registration,
            config=config,
        )
        if request_result.url:
            parsed_url = _parse_jetphotos_image_url(request_result.url, registration)
            if parsed_url:
                _cache_set(cache_key, parsed_url, config["positive_cache_ttl_seconds"])
                return LookupResult(url=parsed_url, reason="ok")

        _cache_set(cache_key, None, config["negative_cache_ttl_seconds"])
        return LookupResult(url=None, reason=request_result.reason or "no_image")

    if provider == PLANESPOTTERS_PROVIDER:
        request_result = _request_with_retry(
            provider=provider,
            request_url=f"https://www.planespotters.net/photos/reg/{registration}",
            params={"sort": "latest"},
            headers=_build_headers(referer="https://www.planespotters.net/", user_agent=config["user_agent"]),
            registration=registration,
            config=config,
        )
        if request_result.url:
            parsed_url = _parse_planespotters_image_url(request_result.url, registration)
            if parsed_url:
                _cache_set(cache_key, parsed_url, config["positive_cache_ttl_seconds"])
                return LookupResult(url=parsed_url, reason="ok")

        _cache_set(cache_key, None, config["negative_cache_ttl_seconds"])
        return LookupResult(url=None, reason=request_result.reason or "no_image")

    return LookupResult(url=None, reason="unsupported_provider")


def _lookup_with_logs(provider: str, registration: Any) -> str | None:
    normalized_registration = _normalize_registration(registration)
    if not normalized_registration:
        return None

    config = _load_image_finder_config()
    if not config["enabled"]:
        logger.debug("Image finder disabled by config")
        return None

    result = _lookup_provider_image_url(provider, normalized_registration, config)
    if result.url:
        logger.success(f"Image found {result.url}")
        return result.url

    if result.reason in {"provider_cooldown", "negative_cache_hit"}:
        logger.debug(f"{provider} image lookup skipped for {normalized_registration}: {result.reason}")
    elif result.reason.startswith("http_"):
        logger.warning(f"{provider} lookup failed for {normalized_registration}: {result.reason}")
    else:
        logger.warning(f"{provider} no image found for {normalized_registration}: {result.reason}")

    return None


def get_first_image_url_jp(registration):
    return _lookup_with_logs(JETPHOTOS_PROVIDER, registration)


def get_first_image_url_pp(registration):
    return _lookup_with_logs(PLANESPOTTERS_PROVIDER, registration)


def get_first_image_url(registration):
    normalized_registration = _normalize_registration(registration)
    if not normalized_registration:
        return None

    config = _load_image_finder_config()
    if not config["enabled"]:
        return None

    for provider in config["providers"]:
        if provider == JETPHOTOS_PROVIDER:
            found_url = get_first_image_url_jp(normalized_registration)
        elif provider == PLANESPOTTERS_PROVIDER:
            found_url = get_first_image_url_pp(normalized_registration)
        else:
            logger.warning(f"Ignoring unsupported image provider '{provider}'")
            continue

        if found_url:
            return found_url

    return None


def main():
    registration = "RA78830"
    image_url = get_first_image_url(registration)
    if image_url:
        print(f"First image URL for registration {registration}: {image_url}")
    else:
        print("No image URL found.")


if __name__ == "__main__":
    main()
