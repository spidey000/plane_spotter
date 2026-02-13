from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import config.config as cfg

from socials.message_builder import (
    MessageContext,
    PROFILE_LONG,
    PROFILE_MEDIUM,
    PROFILE_SHORT,
    VALID_PROFILES,
)


SUPPORTED_PLATFORMS = (
    "telegram",
    "bluesky",
    "twitter",
    "threads",
    "instagram",
    "linkedin",
)

DEFAULT_MESSAGE_POLICY = {
    "defaults": {
        "preferred_profile": PROFILE_LONG,
        "fallback_order": [PROFILE_LONG, PROFILE_MEDIUM, PROFILE_SHORT],
        "overflow_action": "block",
    },
    "platform_limits": {
        "twitter": 280,
        "bluesky": 300,
        "threads": 500,
        "instagram": 2200,
        "linkedin": 3000,
        "telegram_text": 4096,
        "telegram_caption": 1024,
    },
    "platforms": {
        "twitter": {"preferred_profile": PROFILE_SHORT},
        "bluesky": {"preferred_profile": PROFILE_SHORT},
        "threads": {"preferred_profile": PROFILE_MEDIUM},
        "instagram": {"preferred_profile": PROFILE_MEDIUM},
        "linkedin": {"preferred_profile": PROFILE_MEDIUM},
        "telegram": {"preferred_profile": PROFILE_LONG},
    },
}


@dataclass(frozen=True)
class PlatformMessageDecision:
    platform: str
    preferred_profile: str
    selected_profile: str | None
    text: str | None
    limit: int | None
    blocked: bool
    reason: str | None
    used_fallback: bool
    lengths_by_profile: dict[str, int]


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _normalize_profile(value: str | None, default: str = PROFILE_LONG) -> str:
    if not value:
        return default
    candidate = str(value).strip().lower()
    if candidate in VALID_PROFILES:
        return candidate
    return default


def _normalize_overflow_action(value: str | None) -> str:
    candidate = str(value or "block").strip().lower()
    if candidate in ("truncate", "block"):
        return candidate
    return "block"


def load_message_policy(policy_override: dict[str, Any] | None = None) -> dict[str, Any]:
    loaded = cfg.get_config("message_policy")
    merged = _deep_merge(DEFAULT_MESSAGE_POLICY, loaded if isinstance(loaded, dict) else {})
    if policy_override:
        merged = _deep_merge(merged, policy_override)
    return merged


def validate_platform(platform: str) -> str:
    candidate = str(platform).strip().lower()
    if candidate not in SUPPORTED_PLATFORMS:
        supported = ", ".join(SUPPORTED_PLATFORMS)
        raise ValueError(f"Unsupported platform '{candidate}'. Supported: {supported}")
    return candidate


def validate_profile(profile: str) -> str:
    candidate = str(profile).strip().lower()
    if candidate not in VALID_PROFILES:
        supported = ", ".join(VALID_PROFILES)
        raise ValueError(f"Invalid profile '{candidate}'. Supported: {supported}")
    return candidate


def get_platform_profile_map(policy_override: dict[str, Any] | None = None) -> dict[str, str]:
    policy = load_message_policy(policy_override)
    default_profile = _normalize_profile(policy.get("defaults", {}).get("preferred_profile"), PROFILE_LONG)

    result: dict[str, str] = {}
    for platform in SUPPORTED_PLATFORMS:
        platform_cfg = policy.get("platforms", {}).get(platform, {})
        result[platform] = _normalize_profile(platform_cfg.get("preferred_profile"), default_profile)

    return result


def _get_limit(platform: str, has_image: bool, policy: dict[str, Any]) -> int | None:
    limits = policy.get("platform_limits", {})
    if platform == "telegram":
        key = "telegram_caption" if has_image else "telegram_text"
    else:
        key = platform

    raw_limit = limits.get(key)
    if raw_limit in (None, "", "null"):
        return None

    try:
        limit = int(raw_limit)
    except (TypeError, ValueError):
        return None

    if limit <= 0:
        return None
    return limit


def _build_profile_sequence(preferred_profile: str, policy: dict[str, Any]) -> list[str]:
    fallback_order = policy.get("defaults", {}).get("fallback_order", [])

    sequence: list[str] = []

    def add(candidate: str | None) -> None:
        normalized = _normalize_profile(candidate, default="")
        if normalized and normalized in VALID_PROFILES and normalized not in sequence:
            sequence.append(normalized)

    add(preferred_profile)
    if isinstance(fallback_order, list):
        for profile in fallback_order:
            add(profile)

    for profile in VALID_PROFILES:
        add(profile)

    return sequence


def _profile_lengths(context: MessageContext) -> dict[str, int]:
    lengths: dict[str, int] = {}
    for profile in VALID_PROFILES:
        text = context.texts_by_profile.get(profile, "")
        lengths[profile] = len(text)
    return lengths


def resolve_message_for_platform(
    platform: str,
    context: MessageContext,
    *,
    has_image: bool = False,
    policy_override: dict[str, Any] | None = None,
) -> PlatformMessageDecision:
    platform_name = validate_platform(platform)
    policy = load_message_policy(policy_override)

    default_profile = _normalize_profile(policy.get("defaults", {}).get("preferred_profile"), PROFILE_LONG)
    platform_cfg = policy.get("platforms", {}).get(platform_name, {})
    preferred_profile = _normalize_profile(platform_cfg.get("preferred_profile"), default_profile)

    limit = _get_limit(platform_name, has_image, policy)
    sequence = _build_profile_sequence(preferred_profile, policy)
    lengths = _profile_lengths(context)

    for profile in sequence:
        text = context.texts_by_profile.get(profile, "")
        if limit is None or len(text) <= limit:
            return PlatformMessageDecision(
                platform=platform_name,
                preferred_profile=preferred_profile,
                selected_profile=profile,
                text=text,
                limit=limit,
                blocked=False,
                reason=None,
                used_fallback=profile != preferred_profile,
                lengths_by_profile=lengths,
            )

    overflow_action = _normalize_overflow_action(policy.get("defaults", {}).get("overflow_action"))

    if overflow_action == "truncate" and limit is not None and sequence:
        selected_profile = sequence[-1]
        source_text = context.texts_by_profile.get(selected_profile, "")
        truncated_text = source_text[:limit]
        return PlatformMessageDecision(
            platform=platform_name,
            preferred_profile=preferred_profile,
            selected_profile=selected_profile,
            text=truncated_text,
            limit=limit,
            blocked=False,
            reason=f"Truncated message to {limit} chars for {platform_name}",
            used_fallback=True,
            lengths_by_profile=lengths,
        )

    reason = (
        f"No message profile fits {platform_name} limit ({limit}). "
        f"Profile lengths: {lengths}"
    )
    return PlatformMessageDecision(
        platform=platform_name,
        preferred_profile=preferred_profile,
        selected_profile=None,
        text=None,
        limit=limit,
        blocked=True,
        reason=reason,
        used_fallback=False,
        lengths_by_profile=lengths,
    )
