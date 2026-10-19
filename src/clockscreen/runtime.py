"""Wires the config, the weather service and the cycle; draws the frame for a moment.

The preview page can change the clock format, units and location. Those choices are saved
in clockscreen-state.json, one key each, and win over config.yaml until they're reset
(the same rule as nhlscreen's team and player choices).
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, get_args

from pydantic import ValidationError

from .config import ClockConfig, Config, LocationConfig, ScreenKind, Units
from .poller import WeatherService
from .render import Canvas, Settings, render
from .rotation import pick
from .state import State
from .weather.client import WeatherClient

log = logging.getLogger(__name__)

SCREENS: tuple[str, ...] = get_args(ScreenKind)
SHOW_NOW_SECONDS = 30.0
SAVED = ("clock", "units", "location")  # config sections the preview page can override

_COORDINATES = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")


def location_choice(text: str, label: str | None = None) -> dict[str, Any]:
    """A location typed on the preview page: a place name, or "latitude, longitude"."""
    text = text.strip()
    if not text:
        raise ValueError("enter a place name, or latitude, longitude")
    match = _COORDINATES.match(text)
    value: dict[str, Any] = {"latitude": float(match[1]), "longitude": float(match[2])} if match else {"name": text}
    if label and label.strip():
        value["label"] = label.strip()
    LocationConfig.model_validate(value)  # range checks; raises ValueError
    return value


def location_text(loc: LocationConfig) -> str:
    return f"{loc.latitude}, {loc.longitude}" if loc.coordinates else (loc.name or "")


class Runtime:
    def __init__(
        self,
        config: Config,
        *,
        client: WeatherClient | None = None,
        state_path: Path | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.file_config = config  # config.yaml as loaded
        self.state = State(state_path)
        self.config = self._effective()  # with the preview page's saved choices on top
        self.weather = WeatherService(self.config, client or WeatherClient(), self.state)
        self._clock = clock
        self._show: tuple[str, float] | None = None  # Show now: (screen, until epoch seconds)

    async def start(self) -> None:
        self.weather.start()

    async def stop(self) -> None:
        await self.weather.stop()

    # ------------------------------------------------------------------ settings

    def _effective(self) -> Config:
        data = self.file_config.model_dump(exclude_unset=True)  # keeps "was name set?" for the label rule
        config = self.file_config
        for key in SAVED:
            saved = self.state.get(key)
            if saved is None:
                continue
            try:
                config = Config.model_validate({**data, key: saved})
                data[key] = saved
            except ValidationError as exc:
                log.warning("Ignoring the saved %s %r: %s", key, saved, exc)
        return config

    def _save(self, key: str, value: Any) -> None:
        self.state.set(key, value)
        self.config = self._effective()

    def set_clock(self, clock: dict[str, Any] | None) -> None:
        """{"format": "24h", "seconds": true}; None = back to config.yaml. Raises ValueError."""
        self._save("clock", None if clock is None else ClockConfig.model_validate(clock).model_dump())
        self.weather.config = self.config  # nothing to fetch; keeps the label in step

    async def set_units(self, units: str | None) -> None:
        """"metric" or "imperial", then fetch the forecast in them; None = back to config.yaml."""
        if units is not None and units not in get_args(Units):
            raise ValueError("units must be metric or imperial")
        self._save("units", units)
        await self.weather.reconfigure(self.config)

    async def set_location(self, text: str | None, label: str | None = None) -> None:
        """A place name or "lat, lon", looked up before it's saved; None = back to config.yaml.

        Raises ValueError for bad input, LocationNotFound (a WeatherError) for no match, and
        WeatherError / httpx.HTTPError when the lookup itself fails; nothing is saved then.
        """
        if text is None:
            self._save("location", None)
            await self.weather.reconfigure(self.config)  # looked up by the next fetch if needed
            return
        value = location_choice(text, label)
        place = await self.weather.resolve_place(LocationConfig.model_validate(value))
        self._save("location", value)
        await self.weather.reconfigure(self.config, place)

    def settings_state(self) -> dict[str, Any]:
        c, f, w = self.config, self.file_config, self.weather
        return {
            "clock": c.clock.model_dump(),
            "units": c.units,
            "location": {"text": location_text(c.location), "label": c.location.label},
            "place": w.place.describe() if w.place else None,
            "label": w.label,
            "saved": {key: self.state.get(key) is not None for key in SAVED},
            "config_file": {"clock": f.clock.model_dump(), "units": f.units, "location": location_text(f.location)},
            "last_error": w.last_error,
        }

    # ------------------------------------------------------------------ what's on

    def now(self) -> float:
        return self._clock()

    def local(self, t: float) -> datetime:
        return datetime.fromtimestamp(t, self.config.tz)

    def screen(self, t: float | None = None) -> tuple[str, float, str]:
        """(screen, seconds until it changes, "show" or "cycle") at epoch time ``t``."""
        t = self.now() if t is None else t
        if self._show is not None:
            screen, until = self._show
            if t < until:
                return screen, until - t, "show"
            self._show = None
        weather = self.weather.fresh(datetime.fromtimestamp(t, timezone.utc))
        screen, left = pick(self.config.cycle, t, weather)
        return screen, left, "cycle"

    def show_now(self, screen: str | None, t: float | None = None) -> None:
        """Hold ``screen`` for SHOW_NOW_SECONDS, then go back to the cycle. None resumes now."""
        if screen is None:
            self._show = None
            return
        if screen not in SCREENS:
            raise ValueError(f"unknown screen {screen!r} (one of {', '.join(SCREENS)})")
        self._show = (screen, (self.now() if t is None else t) + SHOW_NOW_SECONDS)

    def settings(self) -> Settings:
        c = self.config
        return Settings(clock_format=c.clock.format, seconds=c.clock.seconds, hour_step=c.weather.hour_step,
                        label=self.weather.label)

    def frame(self, t: float | None = None) -> Canvas:
        t = self.now() if t is None else t
        screen, _, _ = self.screen(t)
        return render(screen, self.local(t), self.weather.forecast, self.settings())
