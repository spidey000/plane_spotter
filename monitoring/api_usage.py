from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger

import config.config as cfg


@dataclass(frozen=True)
class BudgetDecision:
    allowed: bool
    provider: str
    endpoint: str
    month_cost_usd: float
    estimated_cost_usd: float
    projected_cost_usd: float
    budget_usd: float
    reason: str | None = None


class XBudgetExceededError(RuntimeError):
    pass


_DB_LOCK = threading.Lock()


def _load_usage_config() -> dict[str, Any]:
    config = cfg.load_config()
    usage_cfg = config.get("usage_monitoring", {}) if isinstance(config, dict) else {}

    x_cfg = usage_cfg.get("x", {}) if isinstance(usage_cfg, dict) else {}

    return {
        "enabled": bool(usage_cfg.get("enabled", True)),
        "db_path": str(usage_cfg.get("db_path", "database/usage_metrics.db")),
        "x": {
            "enforce_budget": bool(x_cfg.get("enforce_budget", True)),
            "monthly_budget_usd": float(x_cfg.get("monthly_budget_usd", 10.0)),
            "default_cost_per_call_usd": float(x_cfg.get("default_cost_per_call_usd", 0.01)),
            "endpoint_costs_usd": dict(x_cfg.get("endpoint_costs_usd", {})),
        },
    }


def _resolve_db_path() -> Path:
    config = _load_usage_config()
    raw_path = Path(config["db_path"])
    if raw_path.is_absolute():
        return raw_path

    project_root = Path(__file__).resolve().parent.parent
    return project_root / raw_path


def _ensure_schema() -> None:
    db_path = _resolve_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with _DB_LOCK:
        conn = sqlite3.connect(db_path)
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS api_usage_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider TEXT NOT NULL,
                    endpoint TEXT NOT NULL,
                    method TEXT NOT NULL,
                    status_code INTEGER,
                    success INTEGER NOT NULL,
                    blocked INTEGER NOT NULL DEFAULT 0,
                    duration_ms REAL,
                    estimated_cost_usd REAL NOT NULL DEFAULT 0,
                    error TEXT,
                    metadata_json TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_api_usage_provider_month
                ON api_usage_events(provider, created_at)
                """
            )
            conn.commit()
        finally:
            conn.close()


def _current_month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def get_endpoint_cost(provider: str, endpoint: str, fallback_cost: float | None = None) -> float:
    usage_cfg = _load_usage_config()
    provider_cfg = usage_cfg.get(provider, {}) if provider == "x" else {}

    if provider == "x":
        endpoint_map = provider_cfg.get("endpoint_costs_usd", {})
        if endpoint in endpoint_map:
            return _as_float(endpoint_map.get(endpoint), 0.0)
        if fallback_cost is not None:
            return _as_float(fallback_cost, 0.0)
        return _as_float(provider_cfg.get("default_cost_per_call_usd"), 0.01)

    if fallback_cost is None:
        return 0.0
    return _as_float(fallback_cost, 0.0)


def record_api_event(
    *,
    provider: str,
    endpoint: str,
    method: str,
    status_code: int | None,
    success: bool,
    duration_ms: float | None,
    estimated_cost_usd: float = 0.0,
    blocked: bool = False,
    error: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    usage_cfg = _load_usage_config()
    if not usage_cfg.get("enabled", True):
        return

    _ensure_schema()
    db_path = _resolve_db_path()

    with _DB_LOCK:
        conn = sqlite3.connect(db_path)
        try:
            conn.execute(
                """
                INSERT INTO api_usage_events (
                    provider,
                    endpoint,
                    method,
                    status_code,
                    success,
                    blocked,
                    duration_ms,
                    estimated_cost_usd,
                    error,
                    metadata_json,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    provider,
                    endpoint,
                    method,
                    status_code,
                    1 if success else 0,
                    1 if blocked else 0,
                    duration_ms,
                    _as_float(estimated_cost_usd, 0.0),
                    error,
                    json.dumps(metadata or {}),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            conn.commit()
        finally:
            conn.close()


def get_monthly_cost(provider: str, year_month: str | None = None) -> float:
    _ensure_schema()
    month = year_month or _current_month()
    db_path = _resolve_db_path()

    with _DB_LOCK:
        conn = sqlite3.connect(db_path)
        try:
            cursor = conn.execute(
                """
                SELECT COALESCE(SUM(estimated_cost_usd), 0)
                FROM api_usage_events
                WHERE provider = ? AND blocked = 0 AND substr(created_at, 1, 7) = ?
                """,
                (provider, month),
            )
            row = cursor.fetchone()
            return _as_float(row[0] if row else 0.0, 0.0)
        finally:
            conn.close()


def check_budget(
    provider: str,
    endpoint: str,
    estimated_cost_usd: float | None = None,
) -> BudgetDecision:
    if provider != "x":
        cost = _as_float(estimated_cost_usd, 0.0)
        return BudgetDecision(
            allowed=True,
            provider=provider,
            endpoint=endpoint,
            month_cost_usd=0.0,
            estimated_cost_usd=cost,
            projected_cost_usd=cost,
            budget_usd=float("inf"),
        )

    usage_cfg = _load_usage_config()
    x_cfg = usage_cfg["x"]
    cost = get_endpoint_cost("x", endpoint, fallback_cost=estimated_cost_usd)

    month_cost = get_monthly_cost("x")
    projected = month_cost + cost
    budget = _as_float(x_cfg.get("monthly_budget_usd"), 10.0)

    if not x_cfg.get("enforce_budget", True):
        return BudgetDecision(
            allowed=True,
            provider=provider,
            endpoint=endpoint,
            month_cost_usd=month_cost,
            estimated_cost_usd=cost,
            projected_cost_usd=projected,
            budget_usd=budget,
        )

    allowed = projected <= budget
    reason = None
    if not allowed:
        reason = (
            f"X budget exceeded for month: current=${month_cost:.4f}, "
            f"cost=${cost:.4f}, projected=${projected:.4f}, budget=${budget:.4f}"
        )

    return BudgetDecision(
        allowed=allowed,
        provider=provider,
        endpoint=endpoint,
        month_cost_usd=month_cost,
        estimated_cost_usd=cost,
        projected_cost_usd=projected,
        budget_usd=budget,
        reason=reason,
    )


def enforce_budget_or_raise(
    provider: str,
    endpoint: str,
    estimated_cost_usd: float | None = None,
) -> BudgetDecision:
    decision = check_budget(provider, endpoint, estimated_cost_usd=estimated_cost_usd)
    if decision.allowed:
        return decision

    record_api_event(
        provider=provider,
        endpoint=endpoint,
        method="BUDGET",
        status_code=None,
        success=False,
        blocked=True,
        duration_ms=0.0,
        estimated_cost_usd=decision.estimated_cost_usd,
        error=decision.reason,
    )
    raise XBudgetExceededError(decision.reason or "X budget exceeded")


def get_monthly_usage_summary(year_month: str | None = None) -> dict[str, dict[str, float | int]]:
    _ensure_schema()
    month = year_month or _current_month()
    db_path = _resolve_db_path()

    with _DB_LOCK:
        conn = sqlite3.connect(db_path)
        try:
            cursor = conn.execute(
                """
                SELECT
                    provider,
                    COUNT(*) AS total_calls,
                    COALESCE(SUM(success), 0) AS successful_calls,
                    COALESCE(SUM(blocked), 0) AS blocked_calls,
                    COALESCE(SUM(estimated_cost_usd), 0) AS total_cost
                FROM api_usage_events
                WHERE substr(created_at, 1, 7) = ?
                GROUP BY provider
                ORDER BY provider
                """,
                (month,),
            )
            summary: dict[str, dict[str, float | int]] = {}
            for provider, total_calls, successful_calls, blocked_calls, total_cost in cursor.fetchall():
                summary[provider] = {
                    "total_calls": int(total_calls),
                    "successful_calls": int(successful_calls),
                    "blocked_calls": int(blocked_calls),
                    "total_cost_usd": _as_float(total_cost, 0.0),
                }

            if "x" not in summary:
                summary["x"] = {
                    "total_calls": 0,
                    "successful_calls": 0,
                    "blocked_calls": 0,
                    "total_cost_usd": 0.0,
                }

            return summary
        finally:
            conn.close()


def log_monthly_usage_summary() -> None:
    try:
        summary = get_monthly_usage_summary()
        logger.info(f"API monthly usage summary: {summary}")
    except Exception as exc:  # pragma: no cover - logging fallback
        logger.warning(f"Unable to compute API usage summary: {exc}")
