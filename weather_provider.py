"""
weather_provider.py — Weather data adapters for Weather Scout.

Provides an abstract interface for fetching weather forecasts and a concrete
implementation using Open-Meteo (free, no API key required).

The provider's job is to translate raw API responses into the flat
field-name → value dicts that the scoring engine expects.
"""

import json
import urllib.request
import urllib.parse
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional


# ── Abstract Provider ───────────────────────────────────────────────────────────

class WeatherProvider(ABC):
    """
    Base class for weather data providers.

    Subclasses must implement fetch_forecast(), which returns weather data
    in the format the scoring engine expects:

    {
        "2026-01-15": {
            "temperature_f": 25.0,
            "cloud_cover_pct": 10.0,
            "wind_speed_mph": 8.0,
            "overnight_snowfall_in": 12.0,
            "overnight_low_f": 18.0,
            ...
        },
        "2026-01-16": { ... },
    }
    """

    @abstractmethod
    def fetch_forecast(self, lat: float, lon: float, days_ahead: int,
                       start_hour: int = 6, end_hour: int = 11) -> dict:
        """
        Fetch forecast data for a location.

        Returns a dict mapping date strings to weather-data dicts.
        The weather-data dicts use the canonical field names from SKILL.md.
        """
        pass

    @abstractmethod
    def provider_name(self) -> str:
        pass


# ── Open-Meteo Provider ────────────────────────────────────────────────────────

class OpenMeteoProvider(WeatherProvider):
    """
    Free weather data from Open-Meteo. No API key needed.
    https://open-meteo.com/

    Provides hourly forecasts up to 16 days out. We aggregate hourly data
    into the time windows defined by the search profile.
    """

    BASE_URL = "https://api.open-meteo.com/v1/forecast"

    def provider_name(self) -> str:
        return "Open-Meteo"

    def fetch_forecast(self, lat: float, lon: float, days_ahead: int,
                       start_hour: int = 6, end_hour: int = 11) -> dict:
        """
        Fetch and aggregate hourly forecast into daily time-window summaries.
        """
        params = {
            "latitude": lat,
            "longitude": lon,
            "hourly": ",".join([
                "temperature_2m",
                "apparent_temperature",
                "cloud_cover",
                "wind_speed_10m",
                "wind_gusts_10m",
                "precipitation",
                "snowfall",
                "relative_humidity_2m",
                "visibility",
                "uv_index",
                "surface_pressure",
                "dew_point_2m",
                "precipitation_probability",
            ]),
            "temperature_unit": "fahrenheit",
            "wind_speed_unit": "mph",
            "precipitation_unit": "inch",
            "forecast_days": min(days_ahead + 1, 16),  # +1 for overnight calc
            "timezone": "America/Los_Angeles",
        }

        url = f"{self.BASE_URL}?{urllib.parse.urlencode(params)}"

        try:
            with urllib.request.urlopen(url, timeout=15) as response:
                data = json.loads(response.read().decode())
        except Exception as e:
            print(f"⚠ Open-Meteo request failed for ({lat}, {lon}): {e}")
            return {}

        return self._aggregate_hourly(data, days_ahead, start_hour, end_hour)

    def _aggregate_hourly(self, api_data: dict, days_ahead: int,
                          start_hour: int, end_hour: int) -> dict:
        """
        Convert hourly API data into per-day summaries for the target time window.
        """
        hourly = api_data.get("hourly", {})
        times = hourly.get("time", [])

        if not times:
            return {}

        # Index hourly data by datetime
        hourly_index = {}
        for i, time_str in enumerate(times):
            dt = datetime.fromisoformat(time_str)
            hourly_index[dt] = {
                "temperature_2m": hourly.get("temperature_2m", [None])[i] if i < len(hourly.get("temperature_2m", [])) else None,
                "apparent_temperature": hourly.get("apparent_temperature", [None])[i] if i < len(hourly.get("apparent_temperature", [])) else None,
                "cloud_cover": hourly.get("cloud_cover", [None])[i] if i < len(hourly.get("cloud_cover", [])) else None,
                "wind_speed_10m": hourly.get("wind_speed_10m", [None])[i] if i < len(hourly.get("wind_speed_10m", [])) else None,
                "wind_gusts_10m": hourly.get("wind_gusts_10m", [None])[i] if i < len(hourly.get("wind_gusts_10m", [])) else None,
                "precipitation": hourly.get("precipitation", [None])[i] if i < len(hourly.get("precipitation", [])) else None,
                "snowfall": hourly.get("snowfall", [None])[i] if i < len(hourly.get("snowfall", [])) else None,
                "relative_humidity_2m": hourly.get("relative_humidity_2m", [None])[i] if i < len(hourly.get("relative_humidity_2m", [])) else None,
                "visibility": hourly.get("visibility", [None])[i] if i < len(hourly.get("visibility", [])) else None,
                "uv_index": hourly.get("uv_index", [None])[i] if i < len(hourly.get("uv_index", [])) else None,
                "surface_pressure": hourly.get("surface_pressure", [None])[i] if i < len(hourly.get("surface_pressure", [])) else None,
                "dew_point_2m": hourly.get("dew_point_2m", [None])[i] if i < len(hourly.get("dew_point_2m", [])) else None,
                "precipitation_probability": hourly.get("precipitation_probability", [None])[i] if i < len(hourly.get("precipitation_probability", [])) else None,
            }

        # Build per-day summaries
        result = {}
        base_date = datetime.fromisoformat(times[0]).date()

        for day_offset in range(days_ahead):
            target_date = base_date + timedelta(days=day_offset)
            date_str = target_date.isoformat()

            # Gather hours in the target window
            window_hours = []
            for hour in range(start_hour, end_hour + 1):
                dt = datetime(target_date.year, target_date.month, target_date.day, hour)
                if dt in hourly_index:
                    window_hours.append(hourly_index[dt])

            # Gather overnight hours (6 PM previous day to 6 AM target day)
            overnight_hours = []
            prev_date = target_date - timedelta(days=1)
            for hour in range(18, 24):
                dt = datetime(prev_date.year, prev_date.month, prev_date.day, hour)
                if dt in hourly_index:
                    overnight_hours.append(hourly_index[dt])
            for hour in range(0, 6):
                dt = datetime(target_date.year, target_date.month, target_date.day, hour)
                if dt in hourly_index:
                    overnight_hours.append(hourly_index[dt])

            if not window_hours:
                continue

            # Aggregate into canonical fields
            result[date_str] = self._build_canonical_fields(window_hours, overnight_hours)

        return result

    def _build_canonical_fields(self, window_hours: list, overnight_hours: list) -> dict:
        """
        Map Open-Meteo hourly data to the canonical field names used by
        the scoring engine.
        """

        def safe_avg(values):
            clean = [v for v in values if v is not None]
            return sum(clean) / len(clean) if clean else None

        def safe_min(values):
            clean = [v for v in values if v is not None]
            return min(clean) if clean else None

        def safe_max(values):
            clean = [v for v in values if v is not None]
            return max(clean) if clean else None

        def safe_sum(values):
            clean = [v for v in values if v is not None]
            return sum(clean) if clean else None

        # Window-period averages/extremes
        temps = [h["temperature_2m"] for h in window_hours]
        feels = [h["apparent_temperature"] for h in window_hours]
        clouds = [h["cloud_cover"] for h in window_hours]
        winds = [h["wind_speed_10m"] for h in window_hours]
        gusts = [h["wind_gusts_10m"] for h in window_hours]
        precip = [h["precipitation"] for h in window_hours]
        humidity = [h["relative_humidity_2m"] for h in window_hours]
        visibility = [h["visibility"] for h in window_hours]
        uv = [h["uv_index"] for h in window_hours]
        pressure = [h["surface_pressure"] for h in window_hours]
        dewpoint = [h["dew_point_2m"] for h in window_hours]
        precip_prob = [h["precipitation_probability"] for h in window_hours]

        # Overnight aggregates
        overnight_snow = [h["snowfall"] for h in overnight_hours]
        overnight_temps = [h["temperature_2m"] for h in overnight_hours]

        # Visibility: Open-Meteo returns meters, convert to miles
        vis_avg = safe_avg(visibility)
        vis_miles = vis_avg / 1609.34 if vis_avg is not None else None

        return {
            "temperature_f": safe_avg(temps),
            "feels_like_f": safe_avg(feels),
            "cloud_cover_pct": safe_avg(clouds),
            "wind_speed_mph": safe_avg(winds),
            "wind_gust_mph": safe_max(gusts),
            "precipitation_in": safe_sum(precip),
            "overnight_snowfall_in": _cm_to_inches(safe_sum(overnight_snow)),
            "overnight_low_f": safe_min(overnight_temps),
            "humidity_pct": safe_avg(humidity),
            "visibility_mi": vis_miles,
            "uv_index": safe_max(uv),
            "pressure_mb": safe_avg(pressure),
            "dewpoint_f": safe_avg(dewpoint),
            "precipitation_probability_pct": safe_max(precip_prob),
        }


def _cm_to_inches(cm_val):
    """Open-Meteo returns snowfall in cm. Convert to inches."""
    if cm_val is None:
        return None
    return round(cm_val / 2.54, 1)


# ── Mock Provider (for testing) ────────────────────────────────────────────────

class MockWeatherProvider(WeatherProvider):
    """
    A mock provider for testing profiles without hitting a real API.
    Supply your own weather data dict at construction time.
    """

    def __init__(self, mock_data: dict):
        """
        mock_data: dict mapping (lat, lon) tuples to weather_by_day dicts.
        """
        self._data = mock_data

    def provider_name(self) -> str:
        return "Mock"

    def fetch_forecast(self, lat: float, lon: float, days_ahead: int,
                       start_hour: int = 6, end_hour: int = 11) -> dict:
        key = (round(lat, 4), round(lon, 4))
        return self._data.get(key, {})
