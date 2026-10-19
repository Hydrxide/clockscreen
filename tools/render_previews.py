#!/usr/bin/env python3
"""Render every screen, plus the worst cases, as LED-dot PNGs.

    .venv/bin/python tools/render_previews.py --out previews/

Writes one PNG per case and ``sheet.png`` with all of them, from the recorded Toronto
forecast and synthetic extremes (no network). Look at them before calling a layout done.
"""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from clockscreen.render import HEIGHT, WIDTH, Canvas, Settings, render
from clockscreen.render.icons import SIZES, draw_icon
from clockscreen.weather import parsers
from clockscreen.weather.codes import ICON_KINDS
from clockscreen.weather.models import Current, Day, Forecast, Hour, Place

ROOT = Path(__file__).resolve().parents[1]
TZ = ZoneInfo("America/Toronto")
TORONTO = Place(name="Toronto", region="Ontario", country="Canada", latitude=43.70643, longitude=-79.39864)


def recorded() -> Forecast:
    raw = json.loads((ROOT / "tests/fixtures/forecast_toronto.json").read_text(encoding="utf-8"))
    return parsers.parse_forecast(raw, place=TORONTO, units="metric", tz=TZ, fetched_at=datetime.now(timezone.utc))


def extreme(now: datetime, temp: float, code: int, *, units: str = "metric", is_day: bool = False,
            chance: int = 100) -> Forecast:
    """Every value at its widest: three-digit or negative temperatures, 100% chances."""
    start = now.replace(minute=0, second=0, microsecond=0)
    return Forecast(
        place=TORONTO, units=units, fetched_at=datetime.now(timezone.utc),
        current=Current(time=now, temperature=temp, feels_like=temp - 8, humidity=99, weather_code=code,
                        is_day=is_day, wind_speed=188, wind_direction=315),
        hours=[Hour(time=start + timedelta(hours=i), temperature=temp - i, weather_code=code, precip_chance=chance,
                    is_day=is_day) for i in range(30)],
        days=[Day(date=now.date() + timedelta(days=i), weather_code=code, high=temp, low=temp - 9,
                  precip_chance=chance) for i in range(4)],
    )


def at(y: int, mo: int, d: int, h: int, mi: int, s: int = 0) -> datetime:
    return datetime(y, mo, d, h, mi, s, tzinfo=TZ)


def cases() -> dict[str, Canvas]:
    rec, noon = recorded(), at(2026, 10, 19, 12, 7)
    toronto = Settings(label="Toronto")
    night = at(2026, 1, 21, 23, 59, 59)
    return {
        "clock_12h": render("clock", at(2026, 10, 19, 19, 42), None, Settings()),
        "clock_12h_seconds": render("clock", at(2026, 10, 19, 12, 59, 59), None, Settings(seconds=True)),
        "clock_12h_am": render("clock", at(2026, 10, 19, 10, 8), None, Settings()),
        "clock_24h": render("clock", at(2026, 10, 19, 19, 42), None, Settings(clock_format="24h")),
        "clock_24h_seconds": render("clock", at(2026, 12, 23, 23, 59, 59), None,
                                    Settings(clock_format="24h", seconds=True)),
        "current": render("current", noon, rec, toronto),
        "current_cold_storm": render("current", night, extreme(night, -25, 96), Settings(label="Yellowknife")),
        "current_hot_imperial": render("current", noon, extreme(noon, 104, 0, units="imperial", is_day=True),
                                       Settings(units="imperial", label="Phoenix")),
        "current_long_text": render("current", night, extreme(night, -8, 56), Settings(label="Saint-Jean-sur-Richelieu")),
        "hourly": render("hourly", noon, rec, toronto),
        "hourly_24h_worst": render("hourly", night, extreme(night, -25, 75), Settings(clock_format="24h")),
        "hourly_12h_midnight": render("hourly", at(2026, 10, 19, 21, 30), extreme(at(2026, 10, 19, 21, 30), 12, 63),
                                      Settings(hour_step=1)),
        "daily": render("daily", noon, rec, toronto),
        "daily_worst": render("daily", night, extreme(night, -21, 95), Settings()),
        "daily_hot": render("daily", noon, extreme(noon, 104, 2, units="imperial", chance=40), Settings()),
        "no_weather": render("current", noon, None, toronto),
    }


def icon_sheet() -> Canvas:
    c = Canvas(len(ICON_KINDS) * 2 * 34 + 2, 34 + 18 + 4)
    x = 2
    for kind in ICON_KINDS:
        for is_day in ((True, False) if kind in ("clear", "partly") else (True,)):
            draw_icon(c, x, 2, kind, SIZES[0], is_day)
            draw_icon(c, x + 8, 38, kind, SIZES[1], is_day)
            x += 34
    return c


def sheet(frames: list[Canvas], columns: int = 4, gap: int = 4) -> Canvas:
    rows = -(-len(frames) // columns)
    out = Canvas(columns * (WIDTH + gap) - gap, rows * (HEIGHT + gap) - gap)
    for i, frame in enumerate(frames):
        ox, oy = (i % columns) * (WIDTH + gap), (i // columns) * (HEIGHT + gap)
        for y in range(frame.height):
            for x in range(frame.width):
                out.set(ox + x, oy + y, frame.get(x, y))
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default="previews", help="output folder (default previews/)")
    parser.add_argument("--pitch", type=int, default=6, help="pixels per LED in the PNGs")
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    frames = cases()
    for name, frame in frames.items():
        (out / f"{name}.png").write_bytes(frame.to_png(pitch=args.pitch))
    (out / "icons.png").write_bytes(icon_sheet().to_png(pitch=args.pitch))
    (out / "sheet.png").write_bytes(sheet(list(frames.values())).to_png(pitch=3))
    print(f"wrote {len(frames) + 2} PNGs to {out}/")


if __name__ == "__main__":
    main()
