# Plane Spotter

Automates flight detection for a configured airport (`api.airport_icao`), filters interesting flights, and publishes platform-specific posts from a single platform-agnostic message builder.

## Current Architecture

- `main.py`: orchestration loop, data ingestion, deduplication, DB enrichment, and social dispatch.
- `api/`: external flight data ingestion (`aeroapi`, `aerodatabox`).
- `database/`: provider-agnostic database contract and provider resolver.
  - `database/providers/base.py`: `DatabaseProvider` interface.
  - `database/providers/supabase.py`: Supabase implementation for your schema.
  - `database/db_manager.py`: runtime provider selection (`database.provider` in config).
- `socials/message_builder.py`: single source of truth for message text and links.
- `socials/socials_processing.py`: adapter registry + enabled/disabled dispatch.
- `monitoring/api_usage.py`: aggregated API telemetry + X budget guard.

## Database Provider Swapping

The project now uses a provider abstraction. To add a new DB backend, implement `DatabaseProvider` and register it:

1. Create `database/providers/<provider>.py` implementing methods from `DatabaseProvider`.
2. Register it in `database/db_manager.py` using `register_provider(...)`.
3. Set `database.provider` in `config/config.yaml`.

No business logic changes are needed in `main.py` or `utils/data_processing.py`.

## Supabase Schema Expected

This implementation expects tables compatible with:

- `registrations`
- `interesting_registrations`
- `interesting_models`
- `aircraft_models`
- `flight_history`

## API Monitoring + X Budget

- Every outbound integration writes events to `database/usage_metrics.db`.
- Aggregation is by provider and month.
- X-specific enforcement blocks only X calls when projected monthly cost exceeds budget.
- Budget defaults to `$10` and uses temporary per-call cost values until exact endpoint pricing is configured.
- AeroAPI keys are monitored against `GET /aeroapi/account/usage` and rotated automatically when a key reaches its monthly budget.

## AeroAPI Key Rotation

- Configure one key with `AEROAPI_KEY`, or multiple keys with `AEROAPI_KEYS`.
- Multiple key format supports labels:
  - `AEROAPI_KEYS=key1:<key>,key2:<key>,key3:<key>`
- On each AeroAPI run, usage is checked via `GET /account/usage` (cached for 10 minutes by default).
- If a key reaches the configured budget (`$5` by default), it is skipped and the next key is used.

Configuration knobs:

```yaml
api:
  aeroapi:
    monthly_budget_per_key_usd: 5.0
    usage_cache_ttl_seconds: 600
```

Configure in `config/config.yaml`:

```yaml
usage_monitoring:
  enabled: true
  db_path: database/usage_metrics.db
  x:
    enforce_budget: true
    monthly_budget_usd: 10.0
    default_cost_per_call_usd: 0.01
    endpoint_costs_usd:
      POST /2/tweets: 0.01
      POST /1.1/media/upload.json: 0.01
      GET /2/usage/tweets: 0.01
```

## Environment Variables

Use `.env` for secrets and credentials. Key variables:

- `SUPABASE_URL` (or dashboard URL, auto-normalized to `https://<project>.supabase.co`)
- `SUPABASE_SERVICE_ROLE_KEY` (preferred) or `SUPABASE_PRIV`
- `AEROAPI_KEY`
- `AEROAPI_KEYS` (optional, comma-separated key pool)
- `AEROAPI_MONTHLY_BUDGET_USD` (optional env override)
- `AEROAPI_USAGE_CACHE_TTL_SECONDS` (optional env override)
- `AERODATABOX_KEY`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `BLUESKY_HANDLE`
- `BLUESKY_PASSWORD`
- `X_ACCESS_TOKEN` (for post writes)
- `X_BEARER_TOKEN` / `BEARER_TOKEN` (for usage endpoint sync)

## Run

Set airport at `config/config.yaml` (`api.airport_icao`, e.g. `LEMD`, `LHR`, `JFK`).

```bash
python main.py
```

## E2E Telegram Checks

Run controlled integration checks that send to your configured Telegram channel:

```bash
python3 test/integration/e2e_telegram_checks.py --phase all
```

Phases:

- `--phase adapter`: sends through `socials/telegram.py` adapter contract.
- `--phase pipeline`: runs mocked `main.py` end-to-end flow and sends one interesting flight.
