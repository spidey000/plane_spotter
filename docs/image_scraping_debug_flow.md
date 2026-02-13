# Image Scraping Debug Flow

This document describes the practical debugging flow for JetPhotos and Planespotters scraping.

## Goal

Validate, in one run, whether failures come from:

1. network/connectivity,
2. anti-bot challenge pages,
3. selector/DOM drift,
4. parser logic (`utils/image_finder.py`).

## Command

```bash
python3 test/integration/image_scrape_probe.py --registration EC-MLP --output test/artifacts/image_probe_ec_mlp.json
```

## What the probe does

For each provider (`jetphotos`, `planespotters`):

1. Opens the provider URL in `agent-browser`.
2. Waits for DOM load and captures title + current URL.
3. Captures interactive snapshot (`snapshot -i`).
4. Runs a DOM extraction script (`eval`) that returns:
   - selector hit counts,
   - candidate image URLs,
   - anti-bot marker hits.
5. Closes the browser session.

Then it runs the current parser flow:

- `get_first_image_url_jp(registration)`
- `get_first_image_url_pp(registration)`

Finally it emits:

- findings,
- a recommended debug plan.

It also emits explicit mapping blocks per provider:

- `registration_insertion_strategy`
- `image_extraction_strategy`

These two fields answer where to insert registration and how image extraction is expected to work.

## Interpretation quick guide

- `Attention Required! | Cloudflare` + challenge markers -> anti-bot blocking, not selector bug.
- Browser has candidates but parser returns `None` -> selector/parser drift.
- Browser and parser both empty, no challenge markers -> likely no images for that registration.
- Command timeout / DNS error -> infrastructure issue before scraper logic.
