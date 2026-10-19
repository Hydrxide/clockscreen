"""YAML configuration loaded into typed pydantic models."""

from __future__ import annotations

from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

ScreenKind = Literal["clock", "current", "hourly", "daily"]
Units = Literal["metric", "imperial"]
WEATHER_SCREENS: frozenset[str] = frozenset({"current", "hourly", "daily"})


class ServerConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = Field(9300, ge=1, le=65535)


class LocationConfig(BaseModel):
    # Looked up once through Open-Meteo's geocoding ("Toronto", "Portland, OR", "Paris, France",
    # a US ZIP code). latitude + longitude skip the lookup and win over name.
    name: str | None = "Toronto"
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)
    # Text on the weather screens (default: the place's name).
    label: str | None = None

    @model_validator(mode="after")
    def _where(self) -> LocationConfig:
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("set latitude and longitude together")
        if self.latitude is None and not (self.name or "").strip():
            raise ValueError("set a name, or latitude and longitude")
        return self

    @property
    def coordinates(self) -> tuple[float, float] | None:
        if self.latitude is None or self.longitude is None:
            return None
        return (self.latitude, self.longitude)


class ClockConfig(BaseModel):
    format: Literal["12h", "24h"] = "12h"  # 12h always shows AM/PM
    seconds: bool = False


class WeatherConfig(BaseModel):
    # Open-Meteo's current conditions are 15-minutely, so faster polling gains nothing.
    refresh_minutes: float = Field(15.0, ge=5.0)
    # Hourly screen: 4 columns, this many hours apart, from the next full hour.
    hour_step: int = Field(2, ge=1, le=6)


class CycleEntry(BaseModel):
    screen: ScreenKind
    dwell: float = Field(10.0, gt=0)


class Config(BaseModel):
    timezone: str = "America/Toronto"
    server: ServerConfig = Field(default_factory=ServerConfig)
    location: LocationConfig = Field(default_factory=LocationConfig)
    units: Units = "metric"
    clock: ClockConfig = Field(default_factory=ClockConfig)
    weather: WeatherConfig = Field(default_factory=WeatherConfig)
    cycle: list[CycleEntry] = Field(
        default_factory=lambda: [
            CycleEntry(screen="clock", dwell=20),
            CycleEntry(screen="current", dwell=10),
            CycleEntry(screen="hourly", dwell=8),
            CycleEntry(screen="daily", dwell=8),
        ],
        min_length=1,
    )

    @field_validator("timezone")
    @classmethod
    def _valid_tz(cls, tz: str) -> str:
        try:
            ZoneInfo(tz)
        except (ZoneInfoNotFoundError, ValueError) as exc:  # ZoneInfoNotFoundError is a KeyError
            raise ValueError(f"unknown timezone {tz!r}") from exc
        return tz

    @field_validator("clock", mode="before")
    @classmethod
    def _clock_format(cls, value: object) -> object:
        # YAML reads an unquoted 12h/24h as a string, but a bare 12 or 24 as an int.
        if isinstance(value, dict) and isinstance(value.get("format"), int):
            value = {**value, "format": f"{value['format']}h"}
        return value

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)


def load_config(path: str | Path | None) -> Config:
    if path is None:
        return Config()
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return Config.model_validate(data)
