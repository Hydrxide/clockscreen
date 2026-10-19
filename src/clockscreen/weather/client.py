"""Open-Meteo over httpx: geocoding (place name -> coordinates) and the forecast.

Free for non-commercial use with no API key (limit 10,000 calls a day; we make ~100).
Data is CC-BY 4.0: credit "Weather data by Open-Meteo.com" where it's shown.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from . import parsers
from .models import Forecast, Place

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"

_UNITS = {
    "metric": {"temperature_unit": "celsius", "wind_speed_unit": "kmh"},
    "imperial": {"temperature_unit": "fahrenheit", "wind_speed_unit": "mph"},
}
CURRENT_FIELDS = "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,is_day,wind_speed_10m,wind_direction_10m"
HOURLY_FIELDS = "temperature_2m,weather_code,precipitation_probability,is_day"
DAILY_FIELDS = "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max"
FORECAST_DAYS = 4  # today + the three the daily screen shows; also covers the hourly screen


class WeatherError(Exception):
    """The API answered with an error, or something we can't use."""


class LocationNotFound(WeatherError):
    pass


class WeatherClient:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None, timeout: float = 10.0) -> None:
        self._http = httpx.AsyncClient(
            transport=transport,
            timeout=timeout,
            headers={"User-Agent": "clockscreen/0.1 (DIY LED board)"},
        )
        self.request_count = 0

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _get(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        self.request_count += 1
        response = await self._http.get(url, params=params)
        if response.status_code >= 400:
            # Open-Meteo explains bad requests: {"error": true, "reason": "..."}
            try:
                reason = response.json().get("reason")
            except ValueError:
                reason = None
            raise WeatherError(f"HTTP {response.status_code}" + (f": {reason}" if reason else ""))
        try:
            return response.json()
        except ValueError as exc:
            raise WeatherError("response isn't JSON") from exc

    async def geocode(self, query: str) -> Place:
        raw = await self._get(GEOCODING_URL, {"name": query, "count": 1, "language": "en", "format": "json"})
        place = parsers.parse_place(raw)
        if place is None:
            raise LocationNotFound(f"no place called {query!r}")
        return place

    async def forecast(self, place: Place, *, timezone_name: str, units: str) -> Forecast:
        raw = await self._get(
            FORECAST_URL,
            {
                "latitude": place.latitude,
                "longitude": place.longitude,
                "timezone": timezone_name,
                "timeformat": "unixtime",
                "forecast_days": FORECAST_DAYS,
                "current": CURRENT_FIELDS,
                "hourly": HOURLY_FIELDS,
                "daily": DAILY_FIELDS,
                **_UNITS[units],
            },
        )
        try:
            return parsers.parse_forecast(
                raw, place=place, units=units, tz=ZoneInfo(timezone_name), fetched_at=datetime.now(timezone.utc)
            )
        except (ValueError, TypeError) as exc:
            raise WeatherError(f"unusable forecast: {exc}") from exc
