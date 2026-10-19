"""Which screen is on: a pure function of the time.

The position in the cycle is ``epoch seconds mod total dwell``, so every request (from
HController, the preview page, anything) agrees on the screen without any shared counter.
Weather screens are left out while there's no fresh forecast.
"""

from __future__ import annotations

from .config import WEATHER_SCREENS, CycleEntry


def available(cycle: list[CycleEntry], weather: bool) -> list[CycleEntry]:
    return [e for e in cycle if weather or e.screen not in WEATHER_SCREENS]


def pick(cycle: list[CycleEntry], now: float, weather: bool) -> tuple[str, float]:
    """The screen at ``now`` (epoch seconds) and the seconds until the cycle moves on."""
    entries = available(cycle, weather)
    if not entries:  # a cycle of only weather screens, and no weather yet
        return "clock", 0.0
    pos = now % sum(e.dwell for e in entries)
    for entry in entries:
        if pos < entry.dwell:
            return entry.screen, entry.dwell - pos
        pos -= entry.dwell
    return entries[-1].screen, 0.0  # float rounding at the very end of the cycle
