#!/usr/bin/env python3
"""
Fetch NOAA/NWS (+ Open-Meteo fallback) forecast data for every unique lat/lon
in adventure-scout.html and write the aggregated result to data/conditions.json.

Runs hourly in GitHub Actions. Between each api.weather.gov call we sleep
5 seconds to be a polite API citizen (prevent IP throttling, spread load).

The output JSON is structured to hydrate the HTML's existing weatherCache
directly — no additional transformation required on the client side.
"""

import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
HTML_PATH = ROOT / "index.html"
OUT_PATH = ROOT / "data" / "conditions.json"
NWS_UA = "AdventureScout/1.0 (github.com - scheduled updater)"
NWS_SLEEP_SEC = 5.0      # gap between NWS grid lookups
HTTP_TIMEOUT = 30        # per-request timeout


# ── HTTP helpers ──────────────────────────────────────────────────────────────
def http_get_json(url: str, headers: dict | None = None) -> dict:
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8"))


def nws_get(url: str) -> dict:
    return http_get_json(url, {
        "User-Agent": NWS_UA,
        "Accept": "application/geo+json",
    })


# ── Unit conversions (match adventure-scout.html exactly) ─────────────────────
def c_to_f(c):        return None if c is None else c * 9 / 5 + 32
def mm_to_in(mm):     return None if mm is None else mm / 25.4
def kmh_to_mph(k):    return None if k is None else k * 0.621371
def m_to_mi(m):       return None if m is None else m / 1609.34


# ── NWS time-series aggregation ───────────────────────────────────────────────
def parse_grid_series(values, agg="avg"):
    """Parse NWS gridpoint time-series values into a dict keyed by YYYY-MM-DD."""
    if not values:
        return {}
    by_date: dict[str, list[float]] = {}
    for entry in values:
        time_str = entry["validTime"].split("/")[0]
        date = time_str[:10]
        v = entry.get("value")
        if v is None:
            continue
        by_date.setdefault(date, []).append(v)
    out = {}
    for date, vals in by_date.items():
        if not vals:
            continue
        if agg == "avg":
            out[date] = sum(vals) / len(vals)
        elif agg == "max":
            out[date] = max(vals)
        elif agg == "min":
            out[date] = min(vals)
        elif agg == "sum":
            out[date] = sum(vals)
    return out


# ── NWS fetch ─────────────────────────────────────────────────────────────────
def fetch_nws(lat: float, lon: float) -> dict:
    """Return { weatherByDay: {...}, forecastUrl: "...", source: "NWS" }."""
    point = nws_get(f"https://api.weather.gov/points/{lat},{lon}")
    p = point["properties"]
    grid_id, grid_x, grid_y = p["gridId"], p["gridX"], p["gridY"]
    forecast_url = p.get("forecast", "")
    print(f"  [NWS] ({lat},{lon}) → grid {grid_id}/{grid_x},{grid_y}", flush=True)

    grid = nws_get(
        f"https://api.weather.gov/gridpoints/{grid_id}/{grid_x},{grid_y}"
    )
    gp = grid["properties"]

    def vals(key):
        return gp.get(key, {}).get("values", []) or []

    temp_max   = parse_grid_series(vals("maxTemperature"),             "max")
    temp_min   = parse_grid_series(vals("minTemperature"),             "min")
    sky_cover  = parse_grid_series(vals("skyCover"),                   "avg")
    wind_speed = parse_grid_series(vals("windSpeed"),                  "avg")
    wind_gust  = parse_grid_series(vals("windGust"),                   "max")
    snowfall   = parse_grid_series(vals("snowfallAmount"),             "sum")
    humidity   = parse_grid_series(vals("relativeHumidity"),           "avg")
    precip_amt = parse_grid_series(vals("quantitativePrecipitation"),  "sum")
    visibility = parse_grid_series(vals("visibility"),                 "avg")
    prob_precip= parse_grid_series(vals("probabilityOfPrecipitation"), "max")

    today = datetime.now(timezone.utc).date().isoformat()
    all_dates = set(temp_max) | set(temp_min) | set(sky_cover)
    dates = sorted(d for d in all_dates if d >= today)[:7]
    if not dates:
        raise RuntimeError("NWS returned no usable dates")

    weather_by_day = {}
    for date in dates:
        hi = temp_max.get(date)
        lo = temp_min.get(date)
        # Match HTML: skip days with no temperature data
        if hi is None and lo is None:
            continue
        weather_by_day[date] = {
            "temperature_f":                 c_to_f(hi if hi is not None else lo),
            "cloud_cover_pct":               sky_cover.get(date),
            "wind_speed_mph":                kmh_to_mph(wind_speed.get(date)),
            "wind_gust_mph":                 kmh_to_mph(wind_gust.get(date)),
            "overnight_snowfall_in":         mm_to_in(snowfall.get(date)),
            "overnight_low_f":               c_to_f(lo),
            "humidity_pct":                  humidity.get(date),
            "precipitation_in":              mm_to_in(precip_amt.get(date)),
            "visibility_mi":                 m_to_mi(visibility.get(date)),
            "precipitation_probability_pct": prob_precip.get(date),
        }

    if not weather_by_day:
        raise RuntimeError("NWS grid has no temperature data")

    return {
        "weatherByDay": weather_by_day,
        "forecastUrl": forecast_url,
        "source": "NWS",
    }


# ── Open-Meteo fallback ───────────────────────────────────────────────────────
def fetch_open_meteo(lat: float, lon: float) -> dict:
    daily_vars = ",".join([
        "temperature_2m_max", "temperature_2m_min",
        "precipitation_sum", "precipitation_probability_max",
        "cloud_cover_mean", "wind_speed_10m_max", "wind_gusts_10m_max",
        "snowfall_sum", "relative_humidity_2m_max", "visibility_mean",
    ])
    url = (
        f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
        f"&daily={daily_vars}&timezone=America%2FLos_Angeles&forecast_days=7"
        f"&wind_speed_unit=mph&temperature_unit=fahrenheit"
    )
    data = http_get_json(url)
    d = data["daily"]
    today = datetime.now(timezone.utc).date().isoformat()

    weather_by_day = {}
    for i, date in enumerate(d["time"]):
        if date < today:
            continue
        hi = d["temperature_2m_max"][i]
        lo = d["temperature_2m_min"][i]
        snow_cm = (d.get("snowfall_sum") or [None] * len(d["time"]))[i]
        vis_m   = (d.get("visibility_mean") or [None] * len(d["time"]))[i]
        weather_by_day[date] = {
            "temperature_f":                 hi if hi is not None else lo,
            "overnight_low_f":               lo,
            "cloud_cover_pct":               d["cloud_cover_mean"][i],
            "wind_speed_mph":                d["wind_speed_10m_max"][i],
            "wind_gust_mph":                 d["wind_gusts_10m_max"][i],
            "overnight_snowfall_in":         None if snow_cm is None else snow_cm / 2.54,
            "precipitation_in":              d["precipitation_sum"][i],
            "precipitation_probability_pct": d["precipitation_probability_max"][i],
            "humidity_pct":                  d["relative_humidity_2m_max"][i],
            "visibility_mi":                 None if vis_m is None else vis_m / 1609.34,
        }

    return {
        "weatherByDay": weather_by_day,
        "forecastUrl": f"https://forecast.weather.gov/MapClick.php?lat={lat}&lon={lon}",
        "source": "Open-Meteo",
    }


def fetch_location(lat: float, lon: float) -> dict:
    try:
        return fetch_nws(lat, lon)
    except (urllib.error.HTTPError, urllib.error.URLError, RuntimeError, KeyError) as e:
        print(f"  [NWS] ({lat},{lon}) FAILED: {e} — falling back to Open-Meteo", flush=True)
        return fetch_open_meteo(lat, lon)


# ── Extract locations from the HTML PROFILES array ────────────────────────────
def extract_unique_locations(html_path: Path) -> list[tuple[float, float]]:
    """Scan the HTML for `{ name: "...", lat: 48.x, lon: -121.x, ...}` and
    return deduplicated (lat, lon) pairs in insertion order."""
    text = html_path.read_text()
    # Match location objects only — profile objects don't have both lat and lon
    pattern = re.compile(
        r'\{\s*name:\s*"[^"]+"\s*,\s*lat:\s*(-?[\d.]+)\s*,\s*lon:\s*(-?[\d.]+)'
    )
    seen = set()
    out = []
    for m in pattern.finditer(text):
        lat = float(m.group(1))
        lon = float(m.group(2))
        key = (lat, lon)
        if key not in seen:
            seen.add(key)
            out.append(key)
    return out


# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> int:
    locs = extract_unique_locations(HTML_PATH)
    print(f"Found {len(locs)} unique locations in {HTML_PATH.name}", flush=True)

    weather_cache: dict[str, dict] = {}
    errors: list[dict] = []

    for i, (lat, lon) in enumerate(locs):
        if i > 0:
            # Be polite to api.weather.gov — spread calls over time
            time.sleep(NWS_SLEEP_SEC)
        print(f"[{i+1}/{len(locs)}] fetching {lat},{lon}", flush=True)
        try:
            weather_cache[f"{lat},{lon}"] = fetch_location(lat, lon)
        except Exception as e:
            print(f"  FAILED entirely: {e}", flush=True)
            errors.append({"lat": lat, "lon": lon, "error": str(e)})

    payload = {
        "lastUpdated": datetime.now(timezone.utc).isoformat(),
        "locationCount": len(weather_cache),
        "errors": errors,
        "weatherCache": weather_cache,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, indent=2))
    print(
        f"\nWrote {OUT_PATH.relative_to(ROOT)} "
        f"({len(weather_cache)} locations, {len(errors)} errors)",
        flush=True,
    )
    return 0 if weather_cache else 1


if __name__ == "__main__":
    sys.exit(main())
