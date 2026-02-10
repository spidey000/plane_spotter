# Model Context Document

## System Purpose

- Monitor arrivals/departures at LEMD.
- Detect interesting flights based on registrations/models/first-seen/diversion.
- Generate one platform-agnostic message payload.
- Publish through modular social adapters.

## Core Technologies

- Python 3.x
- Async IO (`asyncio`, `aiohttp`)
- Supabase (REST API) as current persistence provider
- Provider abstraction in `database/providers/base.py` for future DB swaps
- XDK for X API integration
- Loguru for logging

## High-Level Modules

- `main.py`: pipeline orchestration and periodic scheduling.
- `api/`: flight data ingestion.
- `database/`: provider abstraction and Supabase provider implementation.
- `socials/`: adapter modules per platform and central dispatcher.
- `monitoring/`: API usage telemetry and X budget enforcement.

## Operational Rules

- All outbound API calls should be recorded in usage monitoring.
- X budget is enforced at provider level only; other providers are monitored but not blocked.
- Message generation must remain independent from platform send logic.
