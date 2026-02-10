from __future__ import annotations

from typing import Callable

import config.config as cfg

from .providers import DatabaseProvider, SupabaseProvider


ProviderFactory = Callable[[], DatabaseProvider]


_PROVIDER_FACTORIES: dict[str, ProviderFactory] = {
    "supabase": SupabaseProvider,
}

_cached_provider_name: str | None = None
_cached_provider: DatabaseProvider | None = None


def register_provider(name: str, factory: ProviderFactory) -> None:
    _PROVIDER_FACTORIES[name] = factory


def _resolve_provider_name() -> str:
    provider_name = cfg.get_config("database.provider")
    if not provider_name:
        return "supabase"
    return str(provider_name).strip().lower()


def get_database_provider(force_refresh: bool = False) -> DatabaseProvider:
    global _cached_provider_name, _cached_provider

    provider_name = _resolve_provider_name()
    if not force_refresh and _cached_provider_name == provider_name and _cached_provider is not None:
        return _cached_provider

    factory = _PROVIDER_FACTORIES.get(provider_name)
    if factory is None:
        available = ", ".join(sorted(_PROVIDER_FACTORIES.keys()))
        raise ValueError(f"Unsupported database provider '{provider_name}'. Available: {available}")

    _cached_provider_name = provider_name
    _cached_provider = factory()
    return _cached_provider
