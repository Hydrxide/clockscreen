"""Keeps the forecast fresh: find the location once, then fetch every ``refresh_minutes``.

A failed fetch keeps the last good forecast and retries after 30 s, doubling up to the
refresh interval. The clock never waits on any of this.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import datetime, timedelta, timezone

import httpx

from .config import Config
from .state import State
from .weather.client import WeatherClient, WeatherError
from .weather.models import Forecast, Place

log = logging.getLogger(__name__)

# Older than this, the weather screens drop out of the cycle (only the clock shows).
STALE_AFTER = timedelta(hours=3)
RETRY_FIRST_SECONDS = 30.0


class WeatherService:
    def __init__(self, config: Config, client: WeatherClient, state: State) -> None:
        self.config = config
        self.client = client
        self.state = state
        self.place: Place | None = None
        self.forecast: Forecast | None = None
        self.last_error: str | None = None
        self.last_attempt_at: datetime | None = None
        self.next_attempt_at: datetime | None = None
        self._failures = 0
        self._task: asyncio.Task | None = None

    @property
    def refresh_seconds(self) -> float:
        return self.config.weather.refresh_minutes * 60

    @property
    def label(self) -> str:
        """The place's name on the weather screens."""
        loc = self.config.location
        if loc.label:
            return loc.label
        if self.place is not None:
            return self.place.name
        return "" if loc.coordinates else (loc.name or "")

    def fresh(self, now: datetime) -> bool:
        return self.forecast is not None and now - self.forecast.fetched_at <= STALE_AFTER

    async def resolve_place(self) -> Place:
        loc = self.config.location
        if loc.coordinates is not None:
            # No lookup: a name set alongside the coordinates is only the label.
            name = loc.name if "name" in loc.model_fields_set and loc.name else ""
            return Place(name=name, latitude=loc.coordinates[0], longitude=loc.coordinates[1])

        query = (loc.name or "").strip()
        cached = self.state.get("geocode")
        if isinstance(cached, dict) and cached.get("query") == query:
            with contextlib.suppress(ValueError, TypeError, KeyError):
                return Place.model_validate(cached["place"])
        place = await self.client.geocode(query)
        self.state.set("geocode", {"query": query, "place": place.model_dump(mode="json")})
        log.info("Location %r is %s", query, place.describe())
        return place

    async def refresh(self) -> Forecast:
        if self.place is None:
            self.place = await self.resolve_place()
        self.forecast = await self.client.forecast(
            self.place, timezone_name=self.config.timezone, units=self.config.units
        )
        return self.forecast

    async def update(self) -> float:
        """One attempt. Returns the seconds to wait before the next one."""
        self.last_attempt_at = datetime.now(timezone.utc)
        first = self.forecast is None
        try:
            forecast = await self.refresh()
        except (httpx.HTTPError, WeatherError) as exc:
            self._failures += 1
            self.last_error = str(exc) or type(exc).__name__
            delay = min(RETRY_FIRST_SECONDS * 2 ** (self._failures - 1), self.refresh_seconds)
            log.warning("Weather update failed (%s); retrying in %.0fs", self.last_error, delay)
            return delay
        if first or self._failures:
            c = forecast.current
            log.info("Weather for %s: %.0f°, code %d", self.place.describe(), c.temperature, c.weather_code)
        self._failures = 0
        self.last_error = None
        return self.refresh_seconds

    async def _run(self) -> None:
        while True:
            delay = await self.update()
            self.next_attempt_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
            await asyncio.sleep(delay)

    def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        await self.client.aclose()
