from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any

import yaml

from config import supabase_store

CONFIG_PATH = Path(__file__).parent / "config.yaml"

ENV_OVERRIDES = {
    "API_PRELOADED_DATA": ("api", "preloaded_data"),
}

# Default configuration
DEFAULT_CONFIG = {
    "logging": {
        "log_file": "logs/lemd_spotter.log",
        "warning_log_file": "logs/lemd_spotter_warning.log",
        "log_level": "DEBUG",
        "log_rotation": "10 MB",
    },
    "api": {
        "airport_icao": "LEMD",
        "time_range_hours": 2,
        "preloaded_data": True,
        "aeroapi": {
            "monthly_budget_per_key_usd": 5.0,
            "usage_cache_ttl_seconds": 600,
        },
    },
    "database": {
        "provider": "supabase",
        "airport_icao": "LEMD",
    },
    "social_networks": {
        "telegram": True,
        "bluesky": True,
        "twitter": False,
        "instagram": False,
        "linkedin": False,
        "threads": False,
    },
    "platform_settings": {
        "telegram": {
            "notifications_enabled": True,
            "registration_link_enabled": True,
        },
        "bluesky": {
            "registration_link_enabled": True,
        },
    },
    "execution": {
        "interval": (2 * 60 * 60) - 600,
    },
    "usage_monitoring": {
        "enabled": True,
        "db_path": "database/usage_metrics.db",
        "x": {
            "enforce_budget": True,
            "monthly_budget_usd": 10.0,
            "default_cost_per_call_usd": 0.01,
            "endpoint_costs_usd": {
                "POST /2/tweets": 0.01,
                "POST /1.1/media/upload.json": 0.01,
                "GET /2/usage/tweets": 0.01,
            },
        },
    },
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _apply_env_overrides(config: dict[str, Any]) -> dict[str, Any]:
    for env_key, key_path in ENV_OVERRIDES.items():
        raw_value = os.getenv(env_key)
        if raw_value is None:
            continue

        current = config
        for segment in key_path[:-1]:
            if segment not in current or not isinstance(current[segment], dict):
                current[segment] = {}
            current = current[segment]

        current[key_path[-1]] = _coerce_value(raw_value)

    return config


def _coerce_value(value: Any) -> Any:
    if not isinstance(value, str):
        return value

    lowered = value.strip().lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False

    try:
        return int(value)
    except ValueError:
        pass

    try:
        return float(value)
    except ValueError:
        return value


def _load_yaml_overrides() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        save_config(copy.deepcopy(DEFAULT_CONFIG))
        return {}

    with open(CONFIG_PATH, "r", encoding="utf-8") as file:
        loaded = yaml.safe_load(file)

    if not isinstance(loaded, dict):
        save_config(copy.deepcopy(DEFAULT_CONFIG))
        return {}

    return loaded


def _assign_path(target: dict[str, Any], key_path: list[str], value: Any) -> None:
    current = target
    for segment in key_path[:-1]:
        next_value = current.get(segment)
        if not isinstance(next_value, dict):
            next_value = {}
            current[segment] = next_value
        current = next_value
    current[key_path[-1]] = value


def _load_local_config() -> dict[str, Any]:
    overrides = _load_yaml_overrides()
    return _deep_merge(DEFAULT_CONFIG, overrides)


def load_config(force_refresh_remote: bool = False) -> dict[str, Any]:
    """Load configuration merging defaults, YAML overrides, Supabase, and env."""

    config = _load_local_config()
    remote = supabase_store.load_remote_config(force_refresh=force_refresh_remote)
    if remote:
        config = _deep_merge(config, remote)
    return _apply_env_overrides(config)


def save_config(config: dict[str, Any]) -> None:
    """Persist configuration overrides to the local YAML file."""

    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as file:
        yaml.safe_dump(config, file, sort_keys=False)


def _update_local_override(key_path: str, value: Any) -> None:
    overrides = _load_yaml_overrides()
    segments = [segment for segment in key_path.split(".") if segment]
    if not segments:
        raise ValueError("Config key path must not be empty")
    _assign_path(overrides, segments, value)
    save_config(overrides)


def update_config(key: str, value: Any) -> None:
    """Update a specific configuration value locally and, if enabled, remotely."""

    coerced = _coerce_value(value)
    if supabase_store.is_enabled():
        supabase_store.set_remote_value(key, coerced)
    _update_local_override(key, coerced)


def get_config(key: str) -> Any:
    """Get a specific configuration value."""

    config = load_config()
    keys = key.split(".")
    current = config

    for k in keys:
        if k not in current:
            return None
        current = current[k]

    return current


def reset_config_to_defaults() -> None:
    """Reset both YAML and Supabase configs back to DEFAULT_CONFIG."""

    defaults_copy = copy.deepcopy(DEFAULT_CONFIG)
    save_config(defaults_copy)
    if supabase_store.is_enabled():
        supabase_store.replace_remote_config(defaults_copy)


# Load initial configuration snapshot
config = load_config()
