---
name: adventure-scout
description: >
  A configurable weather-scoring engine that evaluates forecasts against named
  "search profiles" to find ideal conditions for outdoor adventures. Use this
  skill whenever the user wants to set up weather watches, create condition-based
  alerts, score ski days, corn snow harvests, backpacking windows, stargazing
  nights, sunrise/sunset photography, or any activity where specific weather
  criteria matter. Also trigger when the user asks to check, run, edit, or create
  adventure profiles, or mentions "adventure scout", "weather scoring",
  "condition matching", "bluebird day", or "corn harvest."
---

# Adventure Scout

A modular framework for defining, storing, and evaluating **adventure search
profiles** — human-readable YAML files that describe ideal conditions for an
outdoor activity, scored against live forecast data from multiple locations,
with notifications pushed to WhatsApp (or other channels).

---

## Architecture

Adventure Scout is built from four independent layers. Each layer has a clean
interface boundary so it can be upgraded, swapped, or extended without touching
the others.

```
┌─────────────────────────────────────────────────────────┐
│                      run_scout.py                       │
│                   (orchestrator / CLI)                   │
├──────────┬──────────┬───────────────┬───────────────────┤
│ Profiles │  Engine  │   Providers   │    Notifiers      │
│  (YAML)  │ (scoring)│ (weather data)│ (WhatsApp, etc.)  │
└──────────┴──────────┴───────────────┴───────────────────┘
```

### Layer 1: Profiles (`search-profiles/*.yaml`)
Human-readable YAML files. One file per adventure type. Users create, edit,
and version these directly. No code changes needed to add a new adventure.

### Layer 2: Engine (`scripts/engine.py`)
Pure scoring logic. Takes a profile + weather data dict, produces scored
results. Has no knowledge of where data comes from or where results go.
Upgrade scoring curves or methods here without touching anything else.

### Layer 3: Providers (`scripts/weather_provider.py`)
Weather API adapters. Each provider implements one method: `fetch_forecast()`.
Swap Open-Meteo for NWS or Tomorrow.io by writing a new class. The engine
and profiles don't care which provider you use.

### Layer 4: Notifiers (`notifiers/`)
Output channels. Each notifier implements `send_alert()`. WhatsApp via Twilio
is the default. Add email, Slack, SMS, or push notifications by dropping in
a new notifier module.

### The Orchestrator (`scripts/run_scout.py`)
Wires the layers together: loads profiles → fetches weather → scores →
notifies. This is the only file that knows about all four layers.

---

## Directory Layout

```
adventure-scout/
├── SKILL.md                              ← You are here
├── search-profiles/                      ← User-created YAML profiles
│   ├── bluebird-powder-day.yaml
│   ├── corn-harvest.yaml
│   ├── nightsky-backpacking.yaml
│   └── sunset-sunrise-backpacking.yaml
├── scripts/
│   ├── engine.py                         ← Scoring engine (Layer 2)
│   ├── profile_loader.py                 ← YAML → Profile objects
│   ├── weather_provider.py               ← Weather API adapters (Layer 3)
│   └── run_scout.py                      ← CLI orchestrator
├── notifiers/
│   ├── __init__.py                       ← Notifier interface
│   ├── whatsapp_notifier.py              ← WhatsApp via Twilio
│   └── console_notifier.py              ← Print to terminal (default)
└── references/
    └── profile-schema.md                 ← Full schema docs
```

---

## Quick Start

```bash
# Test with mock data
python scripts/run_scout.py --profile search-profiles/bluebird-powder-day.yaml --mock

# Run all profiles with live weather
python scripts/run_scout.py --all

# Run with WhatsApp notifications
python scripts/run_scout.py --all --notify whatsapp

# Output as JSON for downstream tools
python scripts/run_scout.py --all --format json --output results.json

# Scheduled run (cron example — every day at 5 AM)
# 0 5 * * * cd /path/to/adventure-scout && python scripts/run_scout.py --all --notify whatsapp
```

---

## Swapping or Upgrading a Layer

**Want a different weather API?**
Write a new class in `weather_provider.py` that implements `fetch_forecast()`.
Register it in `run_scout.py`'s provider map. Done — profiles and engine
are untouched.

**Want a new scoring method?**
Add a function in `engine.py`. Add the method name to `ScoringConfig`'s
valid list. Existing profiles keep working; new profiles can opt in.

**Want Slack alerts instead of WhatsApp?**
Create `notifiers/slack_notifier.py` implementing `send_alert()`. Add it to
the notifier registry in `notifiers/__init__.py`. Existing notifiers still work.

**Want a new adventure type?**
Copy any `.yaml` profile, change the criteria. No code changes at all.

---

## Profile Quick Reference

See `references/profile-schema.md` for the full specification. Short version:

```yaml
name: "Adventure Name"
description: "What conditions you're looking for and why."

time_window:
  start_hour: 6
  end_hour: 11
  days_ahead: 3

locations:
  - name: "Place"
    lat: 47.0
    lon: -121.0

criteria:
  - field: temperature_f
    label: "Human description"
    operator: "<="          # <=, >=, ==, between
    threshold: 32
    required: true          # Hard gate vs. soft scoring
    weight: 20              # Points (sum to ~100)
    ideal: 22               # "Perfect" value for max points
    scoring_curve: linear   # linear, step, exponential, bell

scoring:
  method: weighted_sum
  pass_threshold: 60        # "Worth considering"
  highlight_threshold: 85   # "Drop everything"
```

## Supported Weather Fields

| Field | Unit | Aggregation | Description |
|-------|------|-------------|-------------|
| `temperature_f` | °F | window avg | Air temperature |
| `feels_like_f` | °F | window avg | Wind chill / heat index |
| `cloud_cover_pct` | % | window avg | Sky coverage 0-100 |
| `wind_speed_mph` | mph | window avg | Sustained wind |
| `wind_gust_mph` | mph | window max | Peak gusts |
| `precipitation_in` | inches | window sum | Total precipitation |
| `overnight_snowfall_in` | inches | overnight sum | Snow 6PM-6AM |
| `overnight_low_f` | °F | overnight min | Minimum overnight temp |
| `humidity_pct` | % | window avg | Relative humidity |
| `visibility_mi` | miles | window avg | Visibility distance |
| `uv_index` | 0-11+ | window max | UV intensity |
| `pressure_mb` | mbar | window avg | Barometric pressure |
| `dewpoint_f` | °F | window avg | Dew point |
| `precipitation_probability_pct` | % | window max | Chance of precip |
