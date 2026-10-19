"""Wires the config, the weather service and the cycle; draws the frame for a moment."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, get_args

from .config import Config, ScreenKind
from .poller import WeatherService
from .render import Canvas, Settings, render
from .rotation import pick
from .state import State
from .weather.client import WeatherClient

SCREENS: tuple[str, ...] = get_args(ScreenKind)
SHOW_NOW_SECONDS = 30.0


class Runtime:
    def __init__(
        self,
        config: Config,
        *,
        client: WeatherClient | None = None,
        state_path: Path | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.config = config
        self.state = State(state_path)
        self.weather = WeatherService(config, client or WeatherClient(), self.state)
        self._clock = clock
        self._show: tuple[str, float] | None = None  # Show now: (screen, until epoch seconds)

    async def start(self) -> None:
        self.weather.start()

    async def stop(self) -> None:
        await self.weather.stop()

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
        return Settings(clock_format=c.clock.format, seconds=c.clock.seconds, units=c.units,
                        hour_step=c.weather.hour_step, label=self.weather.label)

    def frame(self, t: float | None = None) -> Canvas:
        t = self.now() if t is None else t
        screen, _, _ = self.screen(t)
        return render(screen, self.local(t), self.weather.forecast, self.settings())
