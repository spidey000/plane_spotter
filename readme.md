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
- `socials/message_policy.py`: profile and length selection (`short`/`medium`/`long`) per platform.
- `socials/socials_processing.py`: adapter registry + enabled/disabled dispatch.
- `utils/image_finder.py`: image provider lookup (JetPhotos/Planespotters) with retry, cache, and cooldown.
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

## Message Profiles by Platform

- The bot builds three variants for each flight message: `short`, `medium`, `long`.
- Each platform is mapped to a preferred profile in config.
- If the preferred profile exceeds platform limits, fallback order is applied.
- Overflow policy is configurable; current default is `block` (skip publish on that platform).

## Image Finder Hardening

- Provider order is configurable via `image_finder.providers`.
- Lookups use retry + exponential backoff + jitter and temporary cooldown on anti-bot/rate-limit responses.
- Results are cached by provider+registration (positive and negative TTL) to reduce repeated scraping.
- Image downloads are validated with host allowlist, `Content-Type`, and max size before posting.

## Message Templates (No Redeploy)

- Message text is overrideable from `config/config.yaml` under `message_templates.profiles`.
- The app loads config at runtime, so template changes apply in the next processing cycle without redeploy.
- Overrides are validated before use; invalid templates automatically fall back to code defaults.
- Placeholder lengths are bounded per profile via `message_templates.validation.placeholder_max_chars`.
- Profile budgets are enforced with `message_templates.validation.profile_max_chars` (`short` defaults to `275`).

Available placeholders:

- `flight_label`, `flight_slug`, `flight_url`
- `registration`, `aircraft`, `airline_name`, `airline_code`
- `origin_name`, `origin_icao`, `destination_name`, `destination_icao`
- `scheduled_time`, `terminal`
- `interesting_text`, `diverted_text`
- `short_interesting`, `short_diverted`
- `medium_interesting`, `medium_diverted`
- `long_interesting`, `long_diverted`

Validation rules:

- Unknown placeholders are rejected.
- Unsupported format syntax (`{field:...}` / `{field!r}`) is rejected.
- Every used placeholder must have a configured max length for that profile.
- `static_template_chars + sum(placeholder_max_chars_for_used_fields)` must be `<= profile_max_chars`.

Configuration (`config/config.yaml`):

```yaml
message_policy:
  defaults:
    preferred_profile: long
    fallback_order: [long, medium, short]
    overflow_action: block
  platform_limits:
    twitter: 280
    bluesky: 300
    threads: 500
    instagram: 2200
    linkedin: 3000
    telegram_text: 4096
    telegram_caption: 1024
  platforms:
    twitter: { preferred_profile: short }
    bluesky: { preferred_profile: short }
    telegram: { preferred_profile: long }
```

### Live tuning from Telegram bot

Admin commands:

- `/help` (or `/start`) to show command usage.
- `/help_tech` (or `/help_tecnico`) for detailed technical command guide.
- `/profile_set <platform> <short|medium|long>`
- `/profile_get <platform>`
- `/profile_list`
- `/profile_preview <platform> [image]`

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

## Image Scraping Probe

Run an agent-browser + parser probe for JetPhotos and Planespotters:

```bash
python3 test/integration/image_scrape_probe.py --registration EC-MLP --output test/artifacts/image_probe_ec_mlp.json
```

The report includes:

- Browser-level checks (title, snapshot, challenge markers, candidate image URLs).
- Parser-level checks (`utils/image_finder.py` resolution for both providers).
- Auto-generated findings and a debugging plan based on the observed signals.
