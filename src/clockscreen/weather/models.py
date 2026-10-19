"""Weather data as the screens use it. Temperatures and wind are in the configured units."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel


class Place(BaseModel):
    name: str
    region: str | None = None  # state / province (geocoding's admin1)
    country: str | None = None
    latitude: float
    longitude: float

    def describe(self) -> str:
        where = ", ".join(p for p in (self.name, self.region, self.country) if p)
        return f"{where} ({self.latitude:.4f}, {self.longitude:.4f})"


class Current(BaseModel):
    time: datetime
    temperature: float
    feels_like: float
    humidity: int | None = None
    weather_code: int
    is_day: bool
    wind_speed: float
    wind_direction: float | None = None  # degrees the wind blows from


class Hour(BaseModel):
    time: datetime
    temperature: float
    weather_code: int
    precip_chance: int | None = None  # %
    is_day: bool


class Day(BaseModel):
    date: date
    weather_code: int
    high: float
    low: float
    precip_chance: int | None = None  # %


class Forecast(BaseModel):
    place: Place
    units: str  # metric | imperial
    fetched_at: datetime  # UTC
    current: Current
    hours: list[Hour]
    days: list[Day]  # days[0] is today
