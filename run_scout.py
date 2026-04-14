#!/usr/bin/env python3
"""
run_scout.py — CLI orchestrator for Adventure Scout.

Wires together the four layers: Profiles → Providers → Engine → Notifiers.
This is the only file that knows about all four layers.

Usage:
    python scripts/run_scout.py --profile search-profiles/bluebird-powder-day.yaml
    python scripts/run_scout.py --all
    python scripts/run_scout.py --all --notify whatsapp
    python scripts/run_scout.py --all --notify whatsapp --notify console
    python scripts/run_scout.py --profile search-profiles/corn-harvest.yaml --mock --format summary
    python scripts/run_scout.py --all --format json --output results.json

Flags:
    --profile       Path to a single profile YAML file
    --all           Run all profiles in --profiles-dir
    --profiles-dir  Directory containing profiles (default: search-profiles/)
    --format        Output format: markdown (default), json, summary
    --mock          Use mock weather data (for testing)
    --output        Write output to file instead of stdout
    --provider      Weather provider: open-meteo (default)
    --notify        Notifier(s) to use: console, whatsapp (repeatable)
    --notify-config JSON file with notifier config (API keys, phone numbers)
    --only-alerts   Only output/notify when pass threshold is met
"""

import argparse
import json
import os
import sys

# Add parent dir to path so imports work from any cwd
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, SCRIPT_DIR)
sys.path.insert(0, PROJECT_DIR)

from profile_loader import load_profile, load_all_profiles
from engine import run_scout, format_report_markdown, format_report_json
from weather_provider import OpenMeteoProvider, MockWeatherProvider


# ── Mock Data ───────────────────────────────────────────────────────────────────

def build_mock_data():
    """Generate plausible mock data for testing all four profiles."""
    return {
        # Crystal Mountain
        (46.9354, -121.5045): {
            "2026-04-06": {
                "temperature_f": 24.0, "feels_like_f": 18.0, "cloud_cover_pct": 8.0,
                "wind_speed_mph": 7.0, "wind_gust_mph": 15.0, "precipitation_in": 0.0,
                "overnight_snowfall_in": 14.0, "overnight_low_f": 18.0, "humidity_pct": 45.0,
                "visibility_mi": 10.0, "uv_index": 6, "pressure_mb": 1018.0,
                "dewpoint_f": 10.0, "precipitation_probability_pct": 5,
            },
            "2026-04-07": {
                "temperature_f": 42.0, "feels_like_f": 38.0, "cloud_cover_pct": 35.0,
                "wind_speed_mph": 5.0, "wind_gust_mph": 10.0, "precipitation_in": 0.0,
                "overnight_snowfall_in": 0.0, "overnight_low_f": 22.0, "humidity_pct": 40.0,
                "visibility_mi": 15.0, "uv_index": 7, "pressure_mb": 1020.0,
                "dewpoint_f": 18.0, "precipitation_probability_pct": 5,
            },
            "2026-04-08": {
                "temperature_f": 22.0, "feels_like_f": 15.0, "cloud_cover_pct": 5.0,
                "wind_speed_mph": 4.0, "wind_gust_mph": 10.0, "precipitation_in": 0.0,
                "overnight_snowfall_in": 20.0, "overnight_low_f": 14.0, "humidity_pct": 35.0,
                "visibility_mi": 15.0, "uv_index": 8, "pressure_mb": 1022.0,
                "dewpoint_f": 5.0, "precipitation_probability_pct": 0,
            },
        },
        # Stevens Pass
        (47.7448, -121.089): {
            "2026-04-06": {
                "temperature_f": 28.0, "feels_like_f": 22.0, "cloud_cover_pct": 15.0,
                "wind_speed_mph": 10.0, "wind_gust_mph": 18.0, "precipitation_in": 0.0,
                "overnight_snowfall_in": 10.0, "overnight_low_f": 22.0, "humidity_pct": 50.0,
                "visibility_mi": 8.0, "uv_index": 5, "pressure_mb": 1016.0,
                "dewpoint_f": 15.0, "precipitation_probability_pct": 10,
            },
            "2026-04-07": {
                "temperature_f": 40.0, "feels_like_f": 36.0, "cloud_cover_pct": 20.0,
                "wind_speed_mph": 6.0, "wind_gust_mph": 12.0, "precipitation_in": 0.0,
                "overnight_snowfall_in": 0.0, "overnight_low_f": 24.0, "humidity_pct": 42.0,
                "visibility_mi": 12.0, "uv_index": 6, "pressure_mb": 1019.0,
                "dewpoint_f": 16.0, "precipitation_probability_pct": 8,
            },
            "2026-04-08": {
                "temperature_f": 26.0, "feels_like_f": 20.0, "cloud_cover_pct": 10.0,
                "wind_speed_mph": 6.0, "wind_gust_mph": 12.0, "precipitation_in": 0.0,
                "overnight_snowfall_in": 16.0, "overnight_low_f": 16.0, "humidity_pct": 40.0,
                "visibility_mi": 12.0, "uv_index": 7, "pressure_mb": 1020.0,
                "dewpoint_f": 8.0, "precipitation_probability_pct": 5,
            },
        },
        # Mt. Baker
        (48.8566, -121.6644): {
            "2026-04-06": {
                "temperature_f": 26.0, "feels_like_f": 20.0, "cloud_cover_pct": 30.0,
                "wind_speed_mph": 14.0, "wind_gust_mph": 25.0, "precipitation_in": 0.0,
                "overnight_snowfall_in": 12.0, "overnight_low_f": 20.0, "humidity_pct": 55.0,
                "visibility_mi": 7.0, "uv_index": 4, "pressure_mb": 1014.0,
                "dewpoint_f": 14.0, "precipitation_probability_pct": 15,
            },
            "2026-04-07": {
                "temperature_f": 38.0, "feels_like_f": 33.0, "cloud_cover_pct": 40.0,
                "wind_speed_mph": 8.0, "wind_gust_mph": 16.0, "precipitation_in": 0.0,
                "overnight_snowfall_in": 0.0, "overnight_low_f": 20.0, "humidity_pct": 48.0,
                "visibility_mi": 10.0, "uv_index": 5, "pressure_mb": 1017.0,
                "dewpoint_f": 20.0, "precipitation_probability_pct": 10,
            },
            "2026-04-08": {
                "temperature_f": 20.0, "feels_like_f": 12.0, "cloud_cover_pct": 0.0,
                "wind_speed_mph": 3.0, "wind_gust_mph": 8.0, "precipitation_in": 0.0,
                "overnight_snowfall_in": 22.0, "overnight_low_f": 12.0, "humidity_pct": 30.0,
                "visibility_mi": 20.0, "uv_index": 9, "pressure_mb": 1024.0,
                "dewpoint_f": 2.0, "precipitation_probability_pct": 0,
            },
        },
        # Snoqualmie Pass
        (47.4281, -121.4138): {
            "2026-04-06": {
                "temperature_f": 35.0, "feels_like_f": 30.0, "cloud_cover_pct": 12.0,
                "wind_speed_mph": 8.0, "wind_gust_mph": 14.0, "precipitation_in": 0.0,
                "overnight_snowfall_in": 5.0, "overnight_low_f": 30.0, "humidity_pct": 55.0,
                "visibility_mi": 9.0, "uv_index": 5, "pressure_mb": 1017.0,
                "dewpoint_f": 22.0, "precipitation_probability_pct": 10,
            },
            "2026-04-07": {
                "temperature_f": 44.0, "feels_like_f": 40.0, "cloud_cover_pct": 30.0,
                "wind_speed_mph": 4.0, "wind_gust_mph": 8.0, "precipitation_in": 0.0,
                "overnight_snowfall_in": 0.0, "overnight_low_f": 26.0, "humidity_pct": 38.0,
                "visibility_mi": 14.0, "uv_index": 6, "pressure_mb": 1018.0,
                "dewpoint_f": 20.0, "precipitation_probability_pct": 5,
            },
            "2026-04-08": {
                "temperature_f": 30.0, "feels_like_f": 24.0, "cloud_cover_pct": 15.0,
                "wind_speed_mph": 8.0, "wind_gust_mph": 16.0, "precipitation_in": 0.0,
                "overnight_snowfall_in": 9.0, "overnight_low_f": 22.0, "humidity_pct": 45.0,
                "visibility_mi": 10.0, "uv_index": 6, "pressure_mb": 1019.0,
                "dewpoint_f": 12.0, "precipitation_probability_pct": 5,
            },
        },
        # Enchantments (Stuart Lake TH)
        (47.5282, -120.8253): {
            "2026-04-06": {
                "temperature_f": 30.0, "feels_like_f": 25.0, "cloud_cover_pct": 5.0,
                "wind_speed_mph": 4.0, "wind_gust_mph": 8.0, "precipitation_in": 0.0,
                "overnight_snowfall_in": 0.0, "overnight_low_f": 22.0, "humidity_pct": 30.0,
                "visibility_mi": 18.0, "uv_index": 5, "pressure_mb": 1020.0,
                "dewpoint_f": 8.0, "precipitation_probability_pct": 0,
            },
            "2026-04-07": {
                "temperature_f": 48.0, "feels_like_f": 45.0, "cloud_cover_pct": 10.0,
                "wind_speed_mph": 3.0, "wind_gust_mph": 6.0, "precipitation_in": 0.0,
                "overnight_snowfall_in": 0.0, "overnight_low_f": 35.0, "humidity_pct": 28.0,
                "visibility_mi": 22.0, "uv_index": 7, "pressure_mb": 1022.0,
                "dewpoint_f": 12.0, "precipitation_probability_pct": 0,
            },
            "2026-04-08": {
                "temperature_f": 45.0, "feels_like_f": 42.0, "cloud_cover_pct": 38.0,
                "wind_speed_mph": 5.0, "wind_gust_mph": 10.0, "precipitation_in": 0.0,
                "overnight_snowfall_in": 0.0, "overnight_low_f": 38.0, "humidity_pct": 35.0,
                "visibility_mi": 25.0, "uv_index": 6, "pressure_mb": 1019.0,
                "dewpoint_f": 15.0, "precipitation_probability_pct": 5,
            },
        },
        # Goat Rocks (Snowgrass TH)
        (46.4675, -121.5025): {
            "2026-04-06": {
                "temperature_f": 28.0, "feels_like_f": 23.0, "cloud_cover_pct": 8.0,
                "wind_speed_mph": 6.0, "wind_gust_mph": 12.0, "precipitation_in": 0.0,
                "overnight_snowfall_in": 0.0, "overnight_low_f": 20.0, "humidity_pct": 32.0,
                "visibility_mi": 15.0, "uv_index": 5, "pressure_mb": 1019.0,
                "dewpoint_f": 6.0, "precipitation_probability_pct": 5,
            },
            "2026-04-07": {
                "temperature_f": 50.0, "feels_like_f": 47.0, "cloud_cover_pct": 15.0,
                "wind_speed_mph": 5.0, "wind_gust_mph": 10.0, "precipitation_in": 0.0,
                "overnight_snowfall_in": 0.0, "overnight_low_f": 32.0, "humidity_pct": 35.0,
                "visibility_mi": 20.0, "uv_index": 7, "pressure_mb": 1021.0,
                "dewpoint_f": 18.0, "precipitation_probability_pct": 5,
            },
            "2026-04-08": {
                "temperature_f": 42.0, "feels_like_f": 38.0, "cloud_cover_pct": 42.0,
                "wind_speed_mph": 7.0, "wind_gust_mph": 14.0, "precipitation_in": 0.0,
                "overnight_snowfall_in": 0.0, "overnight_low_f": 30.0, "humidity_pct": 40.0,
                "visibility_mi": 18.0, "uv_index": 5, "pressure_mb": 1017.0,
                "dewpoint_f": 20.0, "precipitation_probability_pct": 10,
            },
        },
        # Mt. Rainier (Sunrise)
        (46.9145, -121.6415): {
            "2026-04-06": {
                "temperature_f": 25.0, "feels_like_f": 18.0, "cloud_cover_pct": 5.0,
                "wind_speed_mph": 8.0, "wind_gust_mph": 15.0, "precipitation_in": 0.0,
                "overnight_snowfall_in": 0.0, "overnight_low_f": 18.0, "humidity_pct": 28.0,
                "visibility_mi": 25.0, "uv_index": 6, "pressure_mb": 1021.0,
                "dewpoint_f": 4.0, "precipitation_probability_pct": 0,
            },
            "2026-04-07": {
                "temperature_f": 52.0, "feels_like_f": 50.0, "cloud_cover_pct": 20.0,
                "wind_speed_mph": 4.0, "wind_gust_mph": 8.0, "precipitation_in": 0.0,
                "overnight_snowfall_in": 0.0, "overnight_low_f": 38.0, "humidity_pct": 30.0,
                "visibility_mi": 30.0, "uv_index": 8, "pressure_mb": 1023.0,
                "dewpoint_f": 16.0, "precipitation_probability_pct": 0,
            },
            "2026-04-08": {
                "temperature_f": 48.0, "feels_like_f": 44.0, "cloud_cover_pct": 35.0,
                "wind_speed_mph": 6.0, "wind_gust_mph": 12.0, "precipitation_in": 0.0,
                "overnight_snowfall_in": 0.0, "overnight_low_f": 34.0, "humidity_pct": 38.0,
                "visibility_mi": 22.0, "uv_index": 6, "pressure_mb": 1018.0,
                "dewpoint_f": 18.0, "precipitation_probability_pct": 5,
            },
        },
        # North Cascades (Cascade Pass)
        (48.4748, -121.075): {
            "2026-04-06": {
                "temperature_f": 26.0, "feels_like_f": 20.0, "cloud_cover_pct": 3.0,
                "wind_speed_mph": 5.0, "wind_gust_mph": 10.0, "precipitation_in": 0.0,
                "overnight_snowfall_in": 0.0, "overnight_low_f": 19.0, "humidity_pct": 25.0,
                "visibility_mi": 20.0, "uv_index": 5, "pressure_mb": 1020.0,
                "dewpoint_f": 5.0, "precipitation_probability_pct": 0,
            },
            "2026-04-07": {
                "temperature_f": 46.0, "feels_like_f": 43.0, "cloud_cover_pct": 12.0,
                "wind_speed_mph": 4.0, "wind_gust_mph": 8.0, "precipitation_in": 0.0,
                "overnight_snowfall_in": 0.0, "overnight_low_f": 30.0, "humidity_pct": 30.0,
                "visibility_mi": 25.0, "uv_index": 7, "pressure_mb": 1022.0,
                "dewpoint_f": 12.0, "precipitation_probability_pct": 0,
            },
            "2026-04-08": {
                "temperature_f": 44.0, "feels_like_f": 40.0, "cloud_cover_pct": 25.0,
                "wind_speed_mph": 6.0, "wind_gust_mph": 12.0, "precipitation_in": 0.0,
                "overnight_snowfall_in": 0.0, "overnight_low_f": 32.0, "humidity_pct": 35.0,
                "visibility_mi": 18.0, "uv_index": 6, "pressure_mb": 1019.0,
                "dewpoint_f": 14.0, "precipitation_probability_pct": 5,
            },
        },
        # Mt. Rainier (Spray Park) — for sunset profile
        (46.92, -121.805): {
            "2026-04-06": {
                "temperature_f": 32.0, "feels_like_f": 26.0, "cloud_cover_pct": 10.0,
                "wind_speed_mph": 6.0, "wind_gust_mph": 12.0, "precipitation_in": 0.0,
                "overnight_snowfall_in": 0.0, "overnight_low_f": 20.0, "humidity_pct": 35.0,
                "visibility_mi": 20.0, "uv_index": 5, "pressure_mb": 1020.0,
                "dewpoint_f": 10.0, "precipitation_probability_pct": 0,
            },
            "2026-04-07": {
                "temperature_f": 55.0, "feels_like_f": 52.0, "cloud_cover_pct": 35.0,
                "wind_speed_mph": 4.0, "wind_gust_mph": 8.0, "precipitation_in": 0.0,
                "overnight_snowfall_in": 0.0, "overnight_low_f": 36.0, "humidity_pct": 32.0,
                "visibility_mi": 28.0, "uv_index": 7, "pressure_mb": 1022.0,
                "dewpoint_f": 20.0, "precipitation_probability_pct": 0,
            },
            "2026-04-08": {
                "temperature_f": 50.0, "feels_like_f": 46.0, "cloud_cover_pct": 40.0,
                "wind_speed_mph": 8.0, "wind_gust_mph": 15.0, "precipitation_in": 0.0,
                "overnight_snowfall_in": 0.0, "overnight_low_f": 32.0, "humidity_pct": 42.0,
                "visibility_mi": 18.0, "uv_index": 5, "pressure_mb": 1017.0,
                "dewpoint_f": 22.0, "precipitation_probability_pct": 10,
            },
        },
        # Goat Rocks (Old Snowy) — for sunset profile
        (46.458, -121.442): {
            "2026-04-06": {
                "temperature_f": 28.0, "feels_like_f": 22.0, "cloud_cover_pct": 8.0,
                "wind_speed_mph": 10.0, "wind_gust_mph": 18.0, "precipitation_in": 0.0,
                "overnight_snowfall_in": 0.0, "overnight_low_f": 18.0, "humidity_pct": 30.0,
                "visibility_mi": 22.0, "uv_index": 5, "pressure_mb": 1020.0,
                "dewpoint_f": 6.0, "precipitation_probability_pct": 0,
            },
            "2026-04-07": {
                "temperature_f": 52.0, "feels_like_f": 48.0, "cloud_cover_pct": 38.0,
                "wind_speed_mph": 5.0, "wind_gust_mph": 10.0, "precipitation_in": 0.0,
                "overnight_snowfall_in": 0.0, "overnight_low_f": 34.0, "humidity_pct": 34.0,
                "visibility_mi": 25.0, "uv_index": 7, "pressure_mb": 1021.0,
                "dewpoint_f": 18.0, "precipitation_probability_pct": 0,
            },
            "2026-04-08": {
                "temperature_f": 48.0, "feels_like_f": 44.0, "cloud_cover_pct": 45.0,
                "wind_speed_mph": 7.0, "wind_gust_mph": 14.0, "precipitation_in": 0.0,
                "overnight_snowfall_in": 0.0, "overnight_low_f": 30.0, "humidity_pct": 40.0,
                "visibility_mi": 16.0, "uv_index": 5, "pressure_mb": 1017.0,
                "dewpoint_f": 20.0, "precipitation_probability_pct": 10,
            },
        },
        # North Cascades (Sahale Arm) — for sunset profile
        (48.483, -121.053): {
            "2026-04-06": {
                "temperature_f": 24.0, "feels_like_f": 18.0, "cloud_cover_pct": 5.0,
                "wind_speed_mph": 8.0, "wind_gust_mph": 15.0, "precipitation_in": 0.0,
                "overnight_snowfall_in": 0.0, "overnight_low_f": 16.0, "humidity_pct": 25.0,
                "visibility_mi": 25.0, "uv_index": 5, "pressure_mb": 1021.0,
                "dewpoint_f": 3.0, "precipitation_probability_pct": 0,
            },
            "2026-04-07": {
                "temperature_f": 48.0, "feels_like_f": 44.0, "cloud_cover_pct": 30.0,
                "wind_speed_mph": 5.0, "wind_gust_mph": 10.0, "precipitation_in": 0.0,
                "overnight_snowfall_in": 0.0, "overnight_low_f": 32.0, "humidity_pct": 30.0,
                "visibility_mi": 28.0, "uv_index": 7, "pressure_mb": 1022.0,
                "dewpoint_f": 14.0, "precipitation_probability_pct": 0,
            },
            "2026-04-08": {
                "temperature_f": 45.0, "feels_like_f": 40.0, "cloud_cover_pct": 35.0,
                "wind_speed_mph": 6.0, "wind_gust_mph": 12.0, "precipitation_in": 0.0,
                "overnight_snowfall_in": 0.0, "overnight_low_f": 30.0, "humidity_pct": 32.0,
                "visibility_mi": 20.0, "uv_index": 6, "pressure_mb": 1019.0,
                "dewpoint_f": 12.0, "precipitation_probability_pct": 5,
            },
        },
        # Enchantments (Aasgard Pass) — for sunset profile
        (47.515, -120.81): {
            "2026-04-06": {
                "temperature_f": 26.0, "feels_like_f": 20.0, "cloud_cover_pct": 5.0,
                "wind_speed_mph": 5.0, "wind_gust_mph": 10.0, "precipitation_in": 0.0,
                "overnight_snowfall_in": 0.0, "overnight_low_f": 18.0, "humidity_pct": 28.0,
                "visibility_mi": 22.0, "uv_index": 5, "pressure_mb": 1021.0,
                "dewpoint_f": 5.0, "precipitation_probability_pct": 0,
            },
            "2026-04-07": {
                "temperature_f": 50.0, "feels_like_f": 47.0, "cloud_cover_pct": 32.0,
                "wind_speed_mph": 3.0, "wind_gust_mph": 6.0, "precipitation_in": 0.0,
                "overnight_snowfall_in": 0.0, "overnight_low_f": 36.0, "humidity_pct": 30.0,
                "visibility_mi": 28.0, "uv_index": 7, "pressure_mb": 1023.0,
                "dewpoint_f": 16.0, "precipitation_probability_pct": 0,
            },
            "2026-04-08": {
                "temperature_f": 46.0, "feels_like_f": 42.0, "cloud_cover_pct": 40.0,
                "wind_speed_mph": 5.0, "wind_gust_mph": 10.0, "precipitation_in": 0.0,
                "overnight_snowfall_in": 0.0, "overnight_low_f": 34.0, "humidity_pct": 36.0,
                "visibility_mi": 20.0, "uv_index": 6, "pressure_mb": 1019.0,
                "dewpoint_f": 16.0, "precipitation_probability_pct": 5,
            },
        },
    }


# ── Orchestration ───────────────────────────────────────────────────────────────

def run_single_profile(profile, provider, output_format="markdown"):
    """Run a single profile: fetch weather → score → format."""
    weather_data = {}
    for location in profile.locations:
        print(f"  📡 {location.name}...", file=sys.stderr)
        forecast = provider.fetch_forecast(
            lat=location.lat,
            lon=location.lon,
            days_ahead=profile.time_window.days_ahead,
            start_hour=profile.time_window.start_hour,
            end_hour=profile.time_window.end_hour,
        )
        weather_data[location.name] = forecast

    report = run_scout(profile, weather_data)

    if output_format == "json":
        formatted = json.dumps(format_report_json(report), indent=2)
    elif output_format == "summary":
        formatted = _format_summary(report)
    else:
        formatted = format_report_markdown(report)

    return report, formatted


def _format_summary(report):
    """One-line-per-location summary."""
    lines = [f"=== {report.profile_name} ==="]
    if not report.location_results:
        lines.append("  No results available.")
        return "\n".join(lines)

    by_loc = {}
    for r in report.location_results:
        by_loc.setdefault(r.location_name, []).append(r)

    for loc_name, results in by_loc.items():
        best = max(results, key=lambda r: r.total_score)
        icon = {"EXCEPTIONAL": "⭐", "GOOD": "✅", "MARGINAL": "⚠️", "FAIL": "❌"}.get(best.grade, "")
        lines.append(f"  {icon} {loc_name}: {best.total_score}/100 ({best.grade}) on {best.forecast_date}")

    if report.best_result:
        lines.append(f"  → Best: {report.best_result.location_name} on {report.best_result.forecast_date}")

    return "\n".join(lines)


def send_notifications(report, notifier_names, notify_config):
    """Send alerts through all requested notifiers."""
    for name in notifier_names:
        try:
            from notifiers import get_notifier
            notifier = get_notifier(name)
            success = notifier.send_alert(report, notify_config)
            if success:
                print(f"  ✓ {notifier.notifier_name()} notification sent", file=sys.stderr)
            else:
                print(f"  ✗ {notifier.notifier_name()} notification failed", file=sys.stderr)
        except Exception as e:
            print(f"  ✗ Notifier '{name}' error: {e}", file=sys.stderr)


# ── CLI ─────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Adventure Scout — Find perfect conditions for your next adventure",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/run_scout.py --profile search-profiles/bluebird-powder-day.yaml --mock
  python scripts/run_scout.py --all --format summary
  python scripts/run_scout.py --all --notify whatsapp --notify console
  python scripts/run_scout.py --all --format json --output results.json
        """,
    )
    parser.add_argument("--profile", help="Path to a single profile YAML file")
    parser.add_argument("--all", action="store_true", help="Run all profiles")
    parser.add_argument("--profiles-dir", default=os.path.join(PROJECT_DIR, "search-profiles"),
                        help="Directory containing profiles (default: search-profiles/)")
    parser.add_argument("--format", choices=["markdown", "json", "summary"],
                        default="markdown", help="Output format")
    parser.add_argument("--mock", action="store_true", help="Use mock weather data")
    parser.add_argument("--output", help="Write output to file instead of stdout")
    parser.add_argument("--provider", default="open-meteo",
                        choices=["open-meteo"], help="Weather provider")
    parser.add_argument("--notify", action="append", default=[],
                        help="Notifier(s): console, whatsapp (can repeat)")
    parser.add_argument("--notify-config", help="JSON file with notifier config")
    parser.add_argument("--only-alerts", action="store_true",
                        help="Only output results that meet the pass threshold")

    args = parser.parse_args()

    if not args.profile and not args.all:
        parser.error("Specify --profile <path> or --all")

    # Provider
    if args.mock:
        provider = MockWeatherProvider(build_mock_data())
        print("🧪 Using mock weather data\n", file=sys.stderr)
    else:
        provider = OpenMeteoProvider()

    # Notifier config
    notify_config = {}
    if args.notify_config:
        with open(args.notify_config) as f:
            notify_config = json.load(f)

    # Load profiles
    if args.all:
        profiles = load_all_profiles(args.profiles_dir)
        if not profiles:
            print(f"No profiles found in {args.profiles_dir}/", file=sys.stderr)
            sys.exit(1)
        print(f"🏔  Adventure Scout — {len(profiles)} profiles loaded\n", file=sys.stderr)
    else:
        profiles = [load_profile(args.profile)]
        print(f"🏔  Adventure Scout — {profiles[0].name}\n", file=sys.stderr)

    # Run
    outputs = []
    for profile in profiles:
        print(f"▶ {profile.name}", file=sys.stderr)
        report, formatted = run_single_profile(profile, provider, args.format)

        if args.only_alerts:
            has_alerts = any(
                r.pass_threshold_met or r.highlight_threshold_met
                for r in report.location_results
            )
            if not has_alerts:
                print(f"  — No alerts\n", file=sys.stderr)
                continue

        outputs.append(formatted)

        # Notify
        if args.notify:
            send_notifications(report, args.notify, notify_config)

        print("", file=sys.stderr)

    # Output
    if outputs:
        result = "\n\n".join(outputs)
        if args.output:
            with open(args.output, "w") as f:
                f.write(result)
            print(f"📄 Output written to {args.output}", file=sys.stderr)
        else:
            print(result)
    else:
        print("No results to display.", file=sys.stderr)


if __name__ == "__main__":
    main()
