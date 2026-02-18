"""Helpers for mapping registrations to gallery URLs."""

from __future__ import annotations

from typing import Any


PROVIDER_JETPHOTOS = "jetphotos"
PROVIDER_PLANESPOTTERS = "planespotters"
DEFAULT_GALLERY_PROVIDER = PROVIDER_JETPHOTOS


_NULLISH_REGISTRATIONS = {"", "null", "none"}


_PROVIDER_GALLERY_URLS: dict[str, str] = {
    PROVIDER_JETPHOTOS: "https://www.jetphotos.com/registration/{registration}",
    PROVIDER_PLANESPOTTERS: "https://www.planespotters.net/registration/{registration}",
}


def normalize_registration(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().upper()
    if not normalized:
        return None
    if normalized.lower() in _NULLISH_REGISTRATIONS:
        return None
    return normalized


def resolve_registration_gallery_url(registration: object, provider: str | None = None) -> str | None:
    normalized = normalize_registration(registration)
    if not normalized:
        return None

    requested = (provider or "").strip().lower()
    provider_key = requested if requested in _PROVIDER_GALLERY_URLS else DEFAULT_GALLERY_PROVIDER
    template = _PROVIDER_GALLERY_URLS[provider_key]
    return template.format(registration=normalized)
