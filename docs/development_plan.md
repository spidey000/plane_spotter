# Development Plan

Status is maintained as:

- `[x]` done
- `[~]` in progress
- `[ ]` pending

## Major 1 - Platform-agnostic messaging and modular senders

- [x] Create single message builder module
  - [x] Add `MessageContext` for reusable payload
  - [x] Centralize text rendering in one place
- [x] Refactor social dispatcher to adapter registry
  - [x] Use `send_message(context, image_path)` contract
  - [x] Keep per-platform enable/disable via config
- [~] Finalize X adapter with official XDK
  - [x] Add posting flow using XDK
  - [x] Add optional media upload path
  - [ ] Add optional OAuth2 refresh/token persistence workflow

## Major 2 - Database provider abstraction and Supabase migration

- [x] Define database provider interface
  - [x] Contract methods for reads/upserts/history
- [x] Implement Supabase provider module
  - [x] Load env + normalize project URL
  - [x] Implement indexed reads for registrations and interesting entities
  - [x] Implement registration upsert + flight history insert
- [x] Add provider resolver (`db_manager`) for backend swap
  - [x] Configure provider name in `config/config.yaml`
- [x] Migrate orchestration/data processing to provider contract
  - [x] Remove runtime dependency on Baserow manager
- [x] Remove Baserow references from code/docs

## Major 3 - Global API usage monitoring and X-only budget cap

- [x] Implement central usage monitor module
  - [x] SQLite event schema + monthly summary
- [x] Add X budget guard
  - [x] Enforce monthly `$10` with per-endpoint/default costs
  - [x] Block only X when budget exceeded
- [~] Instrument outbound calls across modules
  - [x] AeroAPI handler
  - [x] AeroDataBox handler
  - [x] Supabase provider
  - [x] Image scrapers and downloads
  - [x] Bluesky helper requests
  - [x] Telegram sender
  - [x] X sender
  - [ ] Add provider tags/metadata standardization pass

## Major 4 - Airport configurability and operational hardening

- [x] Add airport configuration parameter for flight ingestion
  - [x] `api.airport_icao` in config
  - [x] Pass airport into both flight API handlers
  - [x] Save/load preloaded data by airport prefix
- [~] Replace hardcoded secrets with env-backed config
  - [x] Telegram credentials
  - [x] Bluesky credentials
  - [x] Flight API keys
  - [x] AeroAPI key pool (`AEROAPI_KEYS`) + per-key budget config
  - [x] AeroAPI `/account/usage` monitoring integration for rotation decisions
  - [ ] Remove legacy sensitive values from local `.env` if user requests

## Major 5 - Validation and docs

- [x] Update README and architecture docs
- [x] Add `.env.example`
- [x] Add reusable Telegram E2E script (`test/integration/e2e_telegram_checks.py`)
- [x] Validation
  - [x] Run syntax compile (`python3 -m compileall ...`)
  - [x] Run tests (`python3 -m pytest -q`) -> 6 passed
