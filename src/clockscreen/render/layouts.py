"""The four screens, drawn on a 128x64 canvas.

Colours follow nhlscreen: values (times, temperatures) gold, labels white, chance of
precipitation light blue. Everything is drawn at full intensity on black; HController
applies the panel brightness.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from ..weather import codes
from ..weather.models import Forecast, Hour
from .canvas import GOLD, RAIN_BLUE, WHITE, Canvas
from .fonts import BIG, REGULAR, SMALL
from .icons import draw_icon

WIDTH, HEIGHT = 128, 64  # must match display.width / display.height in hcontroller.yaml

DAYS = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")
MONTHS = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")
COMPASS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
SHOW_PRECIP_FROM = 10  # %; lower chances aren't worth the space


@dataclass(frozen=True)
class Settings:
    """What the layouts need from the config."""

    clock_format: str = "12h"
    seconds: bool = False
    units: str = "metric"
    hour_step: int = 2
    label: str = ""


# ------------------------------------------------------------------ text helpers


def clock_parts(now: datetime, clock_format: str) -> tuple[str, str | None]:
    """('7:42', 'PM') in 12h, ('19:42', None) in 24h."""
    if clock_format == "24h":
        return f"{now.hour:02d}:{now.minute:02d}", None
    return f"{now.hour % 12 or 12}:{now.minute:02d}", ("AM" if now.hour < 12 else "PM")


def short_time(now: datetime, clock_format: str) -> str:
    hm, ampm = clock_parts(now, clock_format)
    return hm + (ampm or "")


def hour_label(time: datetime, clock_format: str) -> str:
    if clock_format == "24h":
        return f"{time.hour:02d}:00"
    return f"{time.hour % 12 or 12}{'AM' if time.hour < 12 else 'PM'}"


def date_text(now: datetime) -> str:
    return f"{DAYS[now.weekday()]} {MONTHS[now.month - 1]} {now.day}"


def degrees(value: float) -> str:
    return f"{round(value)}°"


def compass(direction: float | None) -> str:
    return "" if direction is None else COMPASS[round(direction / 45) % 8]


def wind_unit(units: str) -> str:
    return "MPH" if units == "imperial" else "KM/H"


def fit(text: str, font, width: int) -> str:
    """``text`` cut short (at a word if possible) so it's at most ``width`` pixels wide."""
    if font.measure(text) <= width:
        return text
    words = text.split()
    while len(words) > 1:
        words.pop()
        if font.measure(" ".join(words)) <= width:
            return " ".join(words)
    while text and font.measure(text) > width:
        text = text[:-1]
    return text.rstrip(" -,")


def pairs(c: Canvas, x: int, y: int, parts: list[tuple[str, tuple[int, int, int]]], font=SMALL) -> int:
    """Draw (text, colour) runs left to right. Returns x after the last."""
    for text, color in parts:
        x = c.text(x, y, text, font, color)
    return x


def pairs_width(parts: list[tuple[str, tuple[int, int, int]]], font=SMALL) -> int:
    return font.measure("".join(text for text, _ in parts))


# ------------------------------------------------------------------ screens


def layout_clock(c: Canvas, now: datetime, s: Settings) -> None:
    hm, ampm = clock_parts(now, s.clock_format)
    secs = f"{now.second:02d}" if s.seconds else None

    # The time, then a column holding AM/PM (top) and the seconds (bottom).
    column = max(REGULAR.measure(ampm) if ampm else 0, REGULAR.measure(secs, 2) if secs else 0)
    gap = 4 if column else 0
    left = (WIDTH - (BIG.measure(hm) + gap + column)) // 2
    top = 9
    x = c.text(left, top, hm, BIG, GOLD) - BIG.spacing + gap
    if ampm:
        c.text(x, top, ampm, REGULAR, WHITE)
    if secs:
        c.text(x, top + BIG.height - REGULAR.height * 2, secs, REGULAR, GOLD, scale=2)

    c.text_center(WIDTH // 2, top + BIG.height + 10, date_text(now), REGULAR, WHITE)


def _no_weather(c: Canvas, s: Settings) -> None:
    if s.label:
        c.text_center(WIDTH // 2, 18, fit(s.label, REGULAR, WIDTH - 4), REGULAR, WHITE)
    c.text_center(WIDTH // 2, 32, "NO WEATHER YET", REGULAR, WHITE)


def layout_current(c: Canvas, now: datetime, f: Forecast, s: Settings) -> None:
    cur = f.current
    # Top line: the place, and the time (the clock screen is away).
    time_left = c.text_right(WIDTH - 2, 1, short_time(now, s.clock_format), SMALL, WHITE)
    c.text(2, 1, fit(s.label, SMALL, time_left - 6), SMALL, WHITE)

    draw_icon(c, 2, 9, codes.icon_kind(cur.weather_code), 32, cur.is_day)
    c.text(38, 10, degrees(cur.temperature), REGULAR, GOLD, scale=3)
    pairs(c, 38, 34, [("FEELS ", WHITE), (degrees(cur.feels_like), GOLD)])

    c.text(2, 45, codes.condition(cur.weather_code, cur.is_day), REGULAR, WHITE)

    bottom = 57
    today = next((d for d in f.days if d.date == now.date()), None)
    if today:
        pairs(c, 2, bottom, [("H ", WHITE), (degrees(today.high), GOLD), ("  L ", WHITE), (degrees(today.low), GOLD)])
    wind = [(f"{compass(cur.wind_direction)} ".lstrip(), WHITE), (f"{round(cur.wind_speed)}", GOLD),
            (f" {wind_unit(s.units)}", WHITE)]
    pairs(c, WIDTH - 1 - pairs_width(wind), bottom, wind)


def upcoming_hours(f: Forecast, now: datetime, step: int, count: int = 4) -> list[Hour]:
    """The forecast hours from the next full hour, ``step`` hours apart."""
    start = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    by_time = {h.time.timestamp(): h for h in f.hours}
    wanted = (start + timedelta(hours=step * i) for i in range(count))
    return [by_time[t.timestamp()] for t in wanted if t.timestamp() in by_time]


def _column(c: Canvas, center: int, title: str, kind: str, is_day: bool, lines: list[tuple[str, tuple]]) -> None:
    c.text_center(center, 4, title, REGULAR, WHITE)
    draw_icon(c, center - 8, 14, kind, 16, is_day)
    y = 34
    for text, color in lines:
        if text:
            c.text_center(center, y, text, REGULAR, color)
        y += 10


def layout_hourly(c: Canvas, now: datetime, f: Forecast, s: Settings) -> None:
    for i, hour in enumerate(upcoming_hours(f, now, s.hour_step)):
        chance = hour.precip_chance or 0
        _column(c, 16 + i * 32, hour_label(hour.time, s.clock_format), codes.icon_kind(hour.weather_code),
                hour.is_day, [(degrees(hour.temperature), GOLD),
                              (f"{chance}%" if chance >= SHOW_PRECIP_FROM else "", RAIN_BLUE)])


def layout_daily(c: Canvas, now: datetime, f: Forecast, s: Settings) -> None:
    days = [d for d in f.days if d.date > now.date()][:3]
    for i, day in enumerate(days):
        chance = day.precip_chance or 0
        center = 21 + i * 43
        c.text_center(center, 2, DAYS[day.date.weekday()], REGULAR, WHITE)
        draw_icon(c, center - 8, 12, codes.icon_kind(day.weather_code), 16)
        c.text_center(center, 31, degrees(day.high), REGULAR, GOLD)
        c.text_center(center, 41, degrees(day.low), REGULAR, WHITE)
        if chance >= SHOW_PRECIP_FROM:
            c.text_center(center, 52, f"{chance}%", REGULAR, RAIN_BLUE)


def render(screen: str, now: datetime, forecast: Forecast | None, settings: Settings) -> Canvas:
    """One frame: ``screen`` (clock/current/hourly/daily) at local time ``now``."""
    weather = {"current": layout_current, "hourly": layout_hourly, "daily": layout_daily}
    if screen != "clock" and screen not in weather:
        raise ValueError(f"unknown screen {screen!r}")
    c = Canvas(WIDTH, HEIGHT)
    if screen == "clock":
        layout_clock(c, now, settings)
    elif forecast is None:
        _no_weather(c, settings)
    else:
        weather[screen](c, now, forecast, settings)
    return c
