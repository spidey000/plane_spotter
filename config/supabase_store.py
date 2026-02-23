from __future__ import annotations

import copy
import os
import time
from pathlib import Path
from typing import Any, Iterable

import requests
from dotenv import load_dotenv
from loguru import logger

__all__ = [
    "is_enabled",
    "load_remote_config",
    "set_remote_value",
    "replace_remote_config",
    "invalidate_cache",
    "flatten_config",
    "expand_rows",
]


class SupabaseConfigError(RuntimeError):
    """Raised when Supabase configuration operations fail."""


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


_CACHE_SECONDS = _int_env("SUPABASE_CONFIG_CACHE_SECONDS", 60)
_TIMEOUT_SECONDS = _int_env("SUPABASE_CONFIG_TIMEOUT_SECONDS", 20)

_STORE: "SupabaseConfigStore | None" = None
_STORE_FAILED = False
_CACHE: dict[str, Any] | None = None
_CACHE_EXPIRATION = 0.0


def is_enabled() -> bool:
    """Return True when Supabase-backed config is enabled."""

    return _bool_env("SUPABASE_CONFIG_ENABLED", False)


class SupabaseConfigStore:
    """Lightweight PostgREST client for configuration table."""

    def __init__(self) -> None:
        self._load_environment()
        self.base_url = self._resolve_supabase_url()
        self.api_key = self._resolve_supabase_key()
        schema = os.getenv("SUPABASE_CONFIG_SCHEMA")
        self.schema = schema or os.getenv("SUPABASE_SCHEMA", "public")
        self.table = os.getenv("SUPABASE_CONFIG_TABLE", "app_config")
        self.session = requests.Session()

    @staticmethod
    def _load_environment() -> None:
        project_root = Path(__file__).resolve().parent.parent
        load_dotenv(project_root / ".env")
        load_dotenv(project_root / "config" / ".env")

    @staticmethod
    def _resolve_supabase_url() -> str:
        raw_url = (
            os.getenv("SUPABASE_URL")
            or os.getenv("SUPABASE_API_URL")
            or os.getenv("SUPABASE_PROJECT_URL")
            or ""
        ).strip()
        if not raw_url:
            raise SupabaseConfigError(
                "Missing Supabase URL. Set SUPABASE_URL or SUPABASE_PROJECT_URL"
            )

        dashboard_prefix = "https://supabase.com/dashboard/project/"
        if raw_url.startswith(dashboard_prefix):
            project_ref = raw_url.rstrip("/").split("/")[-1]
            return f"https://{project_ref}.supabase.co"
        return raw_url

    @staticmethod
    def _resolve_supabase_key() -> str:
        key = (
            os.getenv("SUPABASE_SERVICE_ROLE_KEY")
            or os.getenv("SUPABASE_PRIV")
            or os.getenv("SUPABASE_KEY")
            or os.getenv("SUPABASE_ANON_KEY")
            or os.getenv("SUPABASE_PUB")
            or ""
        ).strip()
        if not key:
            raise SupabaseConfigError(
                "Missing Supabase API key. Set SUPABASE_SERVICE_ROLE_KEY"
            )
        return key

    def _headers(self, prefer: str | None = None) -> dict[str, str]:
        headers = {
            "apikey": self.api_key,
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
            "Accept-Profile": self.schema,
            "Content-Profile": self.schema,
            "Content-Type": "application/json",
        }
        if prefer:
            headers["Prefer"] = prefer
        return headers

    @property
    def _rest_endpoint(self) -> str:
        base = self.base_url.rstrip("/")
        return f"{base}/rest/v1/{self.table}"

    def _request(
        self,
        method: str,
        *,
        params: dict[str, str] | None = None,
        payload: Any | None = None,
        prefer: str | None = None,
    ) -> requests.Response:
        response = self.session.request(
            method=method.upper(),
            url=self._rest_endpoint,
            params=params,
            headers=self._headers(prefer=prefer),
            json=payload,
            timeout=_TIMEOUT_SECONDS,
        )
        if response.status_code >= 400:
            raise SupabaseConfigError(
                f"Supabase request failed ({response.status_code}): {response.text}"
            )
        return response

    def fetch_config(self) -> dict[str, Any]:
        response = self._request("GET", params={"select": "key_path,value"})
        try:
            rows = response.json()
        except ValueError as exc:
            raise SupabaseConfigError(f"Invalid Supabase response: {response.text}") from exc
        return expand_rows(rows)

    def upsert_value(self, key_path: str, value: Any) -> None:
        payload = {"key_path": key_path, "value": value}
        self._request(
            "POST",
            params={"on_conflict": "key_path"},
            payload=[payload],
            prefer="resolution=merge-duplicates,return=minimal",
        )

    def replace_all(self, flattened: dict[str, Any]) -> None:
        self._request("DELETE")
        if not flattened:
            return
        payload = [
            {"key_path": key, "value": value} for key, value in flattened.items()
        ]
        self._request(
            "POST",
            params={"on_conflict": "key_path"},
            payload=payload,
            prefer="resolution=merge-duplicates,return=minimal",
        )


def _ensure_store() -> SupabaseConfigStore:
    global _STORE, _STORE_FAILED
    if _STORE_FAILED:
        raise SupabaseConfigError("Supabase config store is not available")

    if _STORE is None:
        try:
            _STORE = SupabaseConfigStore()
        except Exception as exc:  # pragma: no cover - init failure
            _STORE_FAILED = True
            raise SupabaseConfigError("Unable to initialize Supabase config store") from exc
    return _STORE


def _assign_path(target: dict[str, Any], key_path: str, value: Any) -> None:
    segments = [segment for segment in key_path.split(".") if segment]
    if not segments:
        raise SupabaseConfigError("Empty config key path")

    current = target
    for segment in segments[:-1]:
        next_value = current.get(segment)
        if not isinstance(next_value, dict):
            next_value = {}
            current[segment] = next_value
        current = next_value
    current[segments[-1]] = value


def expand_rows(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    config: dict[str, Any] = {}
    for row in rows or []:
        key_path = row.get("key_path")
        if not key_path:
            continue
        _assign_path(config, key_path, row.get("value"))
    return config


def flatten_config(config: dict[str, Any]) -> dict[str, Any]:
    flattened: dict[str, Any] = {}

    def _walk(prefix: str, value: Any) -> None:
        if isinstance(value, dict):
            for child_key, child_value in value.items():
                new_prefix = f"{prefix}.{child_key}" if prefix else child_key
                _walk(new_prefix, child_value)
            return
        flattened[prefix] = value

    for top_key, top_value in (config or {}).items():
        _walk(top_key, top_value)
    return flattened


def load_remote_config(force_refresh: bool = False) -> dict[str, Any] | None:
    global _CACHE, _CACHE_EXPIRATION
    if not is_enabled():
        return None

    now = time.monotonic()
    if not force_refresh and _CACHE is not None and now < _CACHE_EXPIRATION:
        return copy.deepcopy(_CACHE)

    try:
        store = _ensure_store()
        data = store.fetch_config()
    except Exception as exc:  # pragma: no cover - network failure path
        logger.warning(f"Unable to fetch Supabase config: {exc}")
        return None

    _CACHE = data
    _CACHE_EXPIRATION = now + max(5, _CACHE_SECONDS)
    return copy.deepcopy(data)


def set_remote_value(key_path: str, value: Any) -> None:
    if not is_enabled():
        raise SupabaseConfigError("Supabase config editing is disabled")

    store = _ensure_store()
    store.upsert_value(key_path, value)
    invalidate_cache()


def replace_remote_config(config: dict[str, Any]) -> None:
    if not is_enabled():
        raise SupabaseConfigError("Supabase config editing is disabled")

    store = _ensure_store()
    flattened = flatten_config(config)
    store.replace_all(flattened)
    invalidate_cache()


def invalidate_cache() -> None:
    global _CACHE, _CACHE_EXPIRATION
    _CACHE = None
    _CACHE_EXPIRATION = 0.0
