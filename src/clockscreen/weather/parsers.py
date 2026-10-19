"""The only code that touches raw Open-Meteo JSON. Forgiving: missing fields are skipped.

Forecasts are requested with ``timeformat=unixtime``, so every time is an exact instant
(daily entries are local midnight) and DST changes need no special handling.
"""

from __future__ import annotations

from datetime import datetime, tzinfo
from typing import Any

from .models import Current, Day, Forecast, Hour, Place


def parse_place(raw: dict[str, Any]) -> Place | None:
    """First geocoding result, or None when nothing matched (the response has no ``results``)."""
    for result in raw.get("results") or []:
        if result.get("latitude") is None or result.get("longitude") is None:
            continue
        return Place(
            name=result.get("name") or "",
            region=result.get("admin1"),
            country=result.get("country"),
            latitude=result["latitude"],
            longitude=result["longitude"],
        )
    return None


def _when(value: Any, tz: tzinfo) -> datetime:
    return datetime.fromtimestamp(int(value), tz)


def _chance(value: Any) -> int | None:
    return None if value is None else int(round(value))


def _columns(block: dict[str, Any], *names: str) -> list[tuple[Any, ...]]:
    """Open-Meteo's hourly/daily blocks are parallel arrays; zip them into rows."""
    columns = [block.get(name) or [] for name in names]
    length = len(block.get("time") or [])
    return [tuple(col[i] if i < len(col) else None for col in columns) for i in range(length)]


def parse_current(raw: dict[str, Any], tz: tzinfo) -> Current:
    c = raw.get("current") or {}
    if c.get("temperature_2m") is None or c.get("weather_code") is None or c.get("time") is None:
        raise ValueError("forecast has no current conditions")
    return Current(
        time=_when(c["time"], tz),
        temperature=c["temperature_2m"],
        feels_like=c["apparent_temperature"] if c.get("apparent_temperature") is not None else c["temperature_2m"],
        humidity=_chance(c.get("relative_humidity_2m")),
        weather_code=int(c["weather_code"]),
        is_day=bool(c.get("is_day", 1)),
        wind_speed=c.get("wind_speed_10m") or 0.0,
        wind_direction=c.get("wind_direction_10m"),
    )


def parse_hours(raw: dict[str, Any], tz: tzinfo) -> list[Hour]:
    rows = _columns(
        raw.get("hourly") or {}, "time", "temperature_2m", "weather_code", "precipitation_probability", "is_day"
    )
    return [
        Hour(time=_when(t, tz), temperature=temp, weather_code=int(code), precip_chance=_chance(pop),
             is_day=bool(1 if day is None else day))
        for t, temp, code, pop, day in rows
        if t is not None and temp is not None and code is not None
    ]


def parse_days(raw: dict[str, Any], tz: tzinfo) -> list[Day]:
    rows = _columns(
        raw.get("daily") or {},
        "time", "weather_code", "temperature_2m_max", "temperature_2m_min", "precipitation_probability_max",
    )
    return [
        Day(date=_when(t, tz).date(), weather_code=int(code), high=high, low=low, precip_chance=_chance(pop))
        for t, code, high, low, pop in rows
        if None not in (t, code, high, low)
    ]


def parse_forecast(raw: dict[str, Any], *, place: Place, units: str, tz: tzinfo, fetched_at: datetime) -> Forecast:
    return Forecast(
        place=place,
        units=units,
        fetched_at=fetched_at,
        current=parse_current(raw, tz),
        hours=parse_hours(raw, tz),
        days=parse_days(raw, tz),
    )
