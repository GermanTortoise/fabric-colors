# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A fabric color-matching catalog. Scrapers pull solid-color fabric listings from
online stores, extract a dominant color from each product image, and store it
as both hex and perceptual LAB. A Flask app lets you browse, filter, and find
fabrics close to a target color (sorted by Delta E). It links out to the
original listing — it never sells anything and stores only solid colors.

## Environment

The system `python3` lacks the `sqlite3` module. Always use the project venv:

```bash
source .venv/bin/activate   # python3.12, has sqlite3 + all deps
```

`requirements.txt` covers it: flask, requests, beautifulsoup4, pillow,
scikit-learn, numpy. The SQLite DB lives at `data/fabrics.db` and the image
cache at `data/cache/images/` — both are gitignored.

## Commands

```bash
# Run the web app (browse at http://localhost:5000)
python -m app.main

# Scrape one source into the DB. Slug = module name under scraper/manufacturers/.
python -m scraper.run <slug> [limit]       # e.g. python -m scraper.run robertkaufman 20

# Re-run color extraction on already-cached images and overwrite hex/lab
# (use after changing scraper/color.py — no network calls)
python -m scraper.recolor [limit]
```

There is no test suite, linter, or build step. To inspect/tune color
extraction visually, run the app and open `/debug/sample?url=<FWD listing url>`
— it renders the crop box and the pixels k-means actually used.

## Architecture

Two halves that meet at the SQLite DB:

**`scraper/`** — offline ingestion.
- `base.py` — `BaseScraper` (rate-limited, retrying HTTP session + on-disk
  image cache) and the `FabricRecord` dataclass. `BaseScraper.is_solid()` /
  `_PATTERN_RE` reject patterned fabrics by whole-word title match.
- `manufacturers/<slug>.py` — one class per source, subclassing `BaseScraper`
  and implementing `iter_records()`. `run.py` discovers the class by importing
  `scraper.manufacturers.<slug>` and finding the `BaseScraper` subclass, so the
  filename IS the CLI slug. Add a source by dropping in a new module here.
- `color.py` — center-crop + k-means dominant color, then RGB→LAB. The crop
  drops background; LAB enables Delta E distance in the app. `extract_with_debug`
  returns intermediate state for the `/debug/sample` view.
- `run.py` saves via an idempotent upsert; `recolor.py` re-extracts from cache.

**`app/`** — Flask read layer (`main.py`). `/` filters by material/weave/text
and, given a target hex, computes Delta E to every row and sorts/filters by
tolerance. The text search splits the query into tokens and requires each token
to match *some* column (so "rayon challis kelly" works across columns). Color
picks are client-side only: `static/picks.js` persists them in localStorage and
broadcasts a `picks-changed` event; there is no user/picks table.

## Identity & dedup model (important, easy to get wrong)

A row is a buyable **listing**, not a fabric. Two distinct concepts:
- `vendor` + `vendor_url` — the store we link out to. **Always set.**
- `manufacturer` + `manufacturer_sku` — the attributed maker and its code. Set
  **only when the source discloses it**; left null otherwise (e.g. SY Fabrics
  is a reseller that hides the maker). House brands (FWD, Robert Kaufman) set
  manufacturer = vendor.

Per-listing idempotency is `UNIQUE (vendor, collection, color_code)` (plus a
unique `vendor_url`). Cross-vendor de-duplication on the manufacturer key is
**deliberately not implemented** — `(manufacturer, manufacturer_sku)` is indexed
but not unique, deferred until two sources actually overlap. Don't add fuzzy
matching. `db.py::_migrate` upgrades the old `brand`/`manufacturer_url` schema
in place; leave it until the DB is known to be migrated everywhere.

## Source / ToS conventions

Each scraper's module docstring records that source's robots.txt stance and the
exact parsing quirks (e.g. Robert Kaufman embeds its whole catalog as
HTML-entity-encoded JSON; FWD prefers the A1 drape image over the featured
swatch). Read it before changing a scraper. Default `crawl_delay` is generous on
purpose. Policy: store images locally but publish only facts + a link out, and
keep `/debug/sample` non-public.
