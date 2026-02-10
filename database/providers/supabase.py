from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import aiohttp
from dotenv import load_dotenv
from loguru import logger

from monitoring.api_usage import record_api_event

from .base import DatabaseProvider


def _normalize_registration(value: Any) -> str | None:
    if value in (None, "", "null", "None"):
        return None
    return str(value).strip().upper()


def _normalize_code(value: Any) -> str | None:
    if value in (None, "", "null", "None"):
        return None
    return str(value).strip().upper()


def _to_iso_datetime(value: Any) -> str:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"):
            try:
                dt = datetime.strptime(value, fmt)
                break
            except ValueError:
                dt = datetime.now(timezone.utc)
        else:
            dt = datetime.now(timezone.utc)
    else:
        dt = datetime.now(timezone.utc)

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


class SupabaseProvider(DatabaseProvider):
    def __init__(self) -> None:
        self._load_environment()
        self.project_url = self._resolve_supabase_url()
        self.api_key = self._resolve_supabase_key()
        self.schema = os.getenv("SUPABASE_SCHEMA", "public")
        self.timeout_seconds = int(os.getenv("SUPABASE_TIMEOUT_SECONDS", "30"))
        self.rest_base = f"{self.project_url.rstrip('/')}/rest/v1"

    @staticmethod
    def _load_environment() -> None:
        project_root = Path(__file__).resolve().parent.parent.parent
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
            raise RuntimeError("Missing Supabase URL. Set SUPABASE_URL in .env")

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
            raise RuntimeError("Missing Supabase API key. Set SUPABASE_SERVICE_ROLE_KEY or SUPABASE_PRIV")
        return key

    def _headers(self, prefer: str | None = None) -> dict[str, str]:
        headers = {
            "apikey": self.api_key,
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Accept-Profile": self.schema,
        }
        if prefer:
            headers["Prefer"] = prefer
        return headers

    async def _request_json(
        self,
        *,
        method: str,
        table: str,
        params: dict[str, str] | None = None,
        payload: dict[str, Any] | list[dict[str, Any]] | None = None,
        prefer: str | None = None,
        endpoint_key: str | None = None,
    ) -> Any:
        endpoint = endpoint_key or f"{method.upper()} /rest/v1/{table}"
        url = f"{self.rest_base}/{table}"
        timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)

        status_code: int | None = None
        recorded = False
        started = time.perf_counter()

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.request(
                    method.upper(),
                    url,
                    headers=self._headers(prefer=prefer),
                    params=params,
                    json=payload,
                ) as response:
                    status_code = response.status
                    raw_body = await response.text()
                    duration_ms = (time.perf_counter() - started) * 1000.0

                    body: Any = None
                    if raw_body:
                        try:
                            body = json.loads(raw_body)
                        except json.JSONDecodeError:
                            body = raw_body

                    success = 200 <= status_code < 300
                    record_api_event(
                        provider="supabase",
                        endpoint=endpoint,
                        method=method.upper(),
                        status_code=status_code,
                        success=success,
                        duration_ms=duration_ms,
                        estimated_cost_usd=0.0,
                        metadata={"table": table},
                        error=None if success else str(body),
                    )
                    recorded = True

                    if not success:
                        raise RuntimeError(f"Supabase request failed ({status_code}): {body}")

                    return body
        except Exception as exc:
            if not recorded:
                duration_ms = (time.perf_counter() - started) * 1000.0
                record_api_event(
                    provider="supabase",
                    endpoint=endpoint,
                    method=method.upper(),
                    status_code=status_code,
                    success=False,
                    duration_ms=duration_ms,
                    estimated_cost_usd=0.0,
                    error=str(exc),
                    metadata={"table": table},
                )
            raise

    @staticmethod
    def _filter_expr(value: Any) -> str:
        if isinstance(value, bool):
            return f"eq.{str(value).lower()}"
        if value is None:
            return "is.null"
        return f"eq.{value}"

    async def select_rows(
        self,
        table: str,
        *,
        filters: dict[str, Any] | None = None,
        select: str = "*",
    ) -> list[dict[str, Any]]:
        params: dict[str, str] = {"select": select}
        for field, value in (filters or {}).items():
            params[field] = self._filter_expr(value)

        result = await self._request_json(method="GET", table=table, params=params)
        if isinstance(result, list):
            return result
        return []

    async def insert_row(self, table: str, data: dict[str, Any]) -> dict[str, Any] | None:
        result = await self._request_json(
            method="POST",
            table=table,
            payload=data,
            prefer="return=representation",
        )
        if isinstance(result, list) and result:
            return result[0]
        if isinstance(result, dict):
            return result
        return None

    async def update_row_by_id(
        self,
        table: str,
        row_id: str,
        data: dict[str, Any],
    ) -> dict[str, Any] | None:
        result = await self._request_json(
            method="PATCH",
            table=table,
            params={"id": f"eq.{row_id}"},
            payload=data,
            prefer="return=representation",
        )
        if isinstance(result, list) and result:
            return result[0]
        if isinstance(result, dict):
            return result
        return None

    async def get_registrations_index(self, airport_icao: str) -> dict[str, dict[str, Any]]:
        rows = await self.select_rows("registrations", filters={"airport_icao": airport_icao})
        indexed: dict[str, dict[str, Any]] = {}
        for row in rows:
            registration = _normalize_registration(row.get("registration"))
            if registration:
                indexed[registration] = row
        return indexed

    async def get_interesting_registrations_index(
        self,
        airport_icao: str,
    ) -> dict[str, dict[str, Any]]:
        rows = await self.select_rows(
            "interesting_registrations",
            filters={"airport_icao": airport_icao, "is_active": True},
        )
        indexed: dict[str, dict[str, Any]] = {}
        for row in rows:
            registration = _normalize_registration(row.get("registration"))
            if registration:
                indexed[registration] = row
        return indexed

    async def get_interesting_models_index(self, airport_icao: str) -> dict[str, dict[str, Any]]:
        interesting_rows = await self.select_rows(
            "interesting_models",
            filters={"airport_icao": airport_icao, "is_active": True},
        )
        model_rows = await self.select_rows("aircraft_models")

        names_by_icao: dict[str, str] = {}
        for row in model_rows:
            code = _normalize_code(row.get("icao_code"))
            if code:
                names_by_icao[code] = str(row.get("name") or "")

        indexed: dict[str, dict[str, Any]] = {}
        for row in interesting_rows:
            code = _normalize_code(row.get("icao_code"))
            if not code:
                continue
            indexed[code] = {
                **row,
                "icao_code": code,
                "name": names_by_icao.get(code),
            }

        return indexed

    async def upsert_registration_sighting(
        self,
        flight_data: Mapping[str, Any],
        airport_icao: str,
    ) -> tuple[dict[str, Any] | None, bool]:
        registration = _normalize_registration(flight_data.get("registration"))
        if not registration:
            return None, False

        aircraft_type_icao = _normalize_code(flight_data.get("aircraft_icao"))
        airline_icao = _normalize_code(flight_data.get("airline"))
        timestamp = _to_iso_datetime(flight_data.get("scheduled_time"))

        existing_rows = await self.select_rows(
            "registrations",
            filters={"registration": registration, "airport_icao": airport_icao},
        )

        if existing_rows:
            existing = existing_rows[0]
            update_payload: dict[str, Any] = {
                "last_seen_at": timestamp,
            }
            if aircraft_type_icao:
                update_payload["aircraft_type_icao"] = aircraft_type_icao
            if airline_icao:
                update_payload["airline_icao"] = airline_icao

            updated = await self.update_row_by_id("registrations", existing["id"], update_payload)
            return (updated or existing), False

        create_payload: dict[str, Any] = {
            "registration": registration,
            "aircraft_type_icao": aircraft_type_icao,
            "airline_icao": airline_icao,
            "first_seen_at": timestamp,
            "last_seen_at": timestamp,
            "airport_icao": airport_icao,
        }
        created = await self.insert_row("registrations", create_payload)
        return created, True

    async def record_flight_history(
        self,
        flight_data: Mapping[str, Any],
        airport_icao: str,
    ) -> dict[str, Any] | None:
        external_id = (
            flight_data.get("flight_name_iata")
            or flight_data.get("flight_name")
            or flight_data.get("registration")
            or "unknown-flight"
        )

        payload = {
            "flight_id_external": str(external_id),
            "registration": _normalize_registration(flight_data.get("registration")),
            "flight_number": flight_data.get("flight_name_iata") or flight_data.get("flight_name"),
            "processed_at": datetime.now(timezone.utc).isoformat(),
            "airport_icao": airport_icao,
        }

        try:
            return await self.insert_row("flight_history", payload)
        except Exception as exc:
            logger.warning(f"Failed to record flight history for {external_id}: {exc}")
            return None
