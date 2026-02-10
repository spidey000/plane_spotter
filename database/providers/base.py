from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Mapping


class DatabaseProvider(ABC):
    @abstractmethod
    async def get_registrations_index(self, airport_icao: str) -> dict[str, dict[str, Any]]:
        """Return registrations indexed by normalized registration string."""

    @abstractmethod
    async def get_interesting_registrations_index(
        self, airport_icao: str
    ) -> dict[str, dict[str, Any]]:
        """Return active interesting registrations indexed by registration."""

    @abstractmethod
    async def get_interesting_models_index(self, airport_icao: str) -> dict[str, dict[str, Any]]:
        """Return active interesting models indexed by ICAO code."""

    @abstractmethod
    async def upsert_registration_sighting(
        self,
        flight_data: Mapping[str, Any],
        airport_icao: str,
    ) -> tuple[dict[str, Any] | None, bool]:
        """Insert or update a registration sighting. Returns (row, created)."""

    @abstractmethod
    async def record_flight_history(
        self,
        flight_data: Mapping[str, Any],
        airport_icao: str,
    ) -> dict[str, Any] | None:
        """Store a processed flight event for audit/history."""
