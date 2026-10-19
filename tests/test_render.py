"""Fonts, icons and the four screen layouts."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from clockscreen.render import HEIGHT, WIDTH, Canvas, Settings, render
from clockscreen.render.canvas import GOLD, WHITE
from clockscreen.render.fonts import BIG, REGULAR, SMALL
from clockscreen.render.icons import _ICONS, PALETTE, SIZES, draw_icon, icon_name
from clockscreen.render.layouts import clock_parts, compass, date_text, fit, hour_label, upcoming_hours
from clockscreen.weather import parsers
from clockscreen.weather.codes import ICON_KINDS
from clockscreen.weather.models import Place

TZ = ZoneInfo("America/Toronto")
TORONTO = Place(name="Toronto", latitude=43.70643, longitude=-79.39864)
NOON = datetime(2026, 10, 19, 12, 7, tzinfo=TZ)  # the fixture's "now" is 12:00


@pytest.fixture
def forecast(fixture):
    return parsers.parse_forecast(fixture("forecast_toronto.json"), place=TORONTO, units="metric", tz=TZ,
                                  fetched_at=datetime.now(timezone.utc))


def count(frame: Canvas, color, rows=range(HEIGHT)) -> int:
    return sum(frame.get(x, y) == color for y in rows for x in range(WIDTH))


# ---------------------------------------------------------------- fonts and icons


def test_fonts():
    for font in (REGULAR, SMALL):
        assert font.glyph("°") is not font.glyph("?")
    assert REGULAR.normalize("12°C, Montréal") == "12°C, MONTREAL"
    assert BIG.height == 28
    assert {BIG.measure(d) for d in "0123456789"} == {16}  # tabular: the clock doesn't shift as it ticks
    assert BIG.measure("12:59") == BIG.measure("10:08")


def test_icons_cover_every_kind():
    for kind in ICON_KINDS:
        for size in SIZES:
            for is_day in (True, False):
                rows = _ICONS[(icon_name(kind, is_day), size)]
                assert len(rows) == size and {len(r) for r in rows} == {size}
                assert set("".join(rows)) <= set(PALETTE) | {"."}
    c = Canvas(32, 32)
    draw_icon(c, 0, 0, "tornado", 32)  # unknown: a cloud, not a crash
    assert c.to_bytes() != bytes(32 * 32 * 3)


# ---------------------------------------------------------------- text


@pytest.mark.parametrize(
    ("hour", "minute", "fmt", "expected"),
    [
        (0, 5, "12h", ("12:05", "AM")),
        (11, 59, "12h", ("11:59", "AM")),
        (12, 0, "12h", ("12:00", "PM")),
        (19, 42, "12h", ("7:42", "PM")),
        (0, 5, "24h", ("00:05", None)),
        (19, 42, "24h", ("19:42", None)),
    ],
)
def test_clock_parts(hour, minute, fmt, expected):
    assert clock_parts(datetime(2026, 10, 19, hour, minute, tzinfo=TZ), fmt) == expected


def test_labels():
    assert date_text(NOON) == "MON OCT 19"
    assert hour_label(datetime(2026, 10, 19, 0, tzinfo=TZ), "12h") == "12AM"
    assert hour_label(datetime(2026, 10, 19, 15, tzinfo=TZ), "12h") == "3PM"
    assert hour_label(datetime(2026, 10, 19, 15, tzinfo=TZ), "24h") == "15:00"
    assert [compass(d) for d in (0, 44, 230, 350, None)] == ["N", "NE", "SW", "N", ""]


def test_fit():
    assert fit("Toronto", SMALL, 100) == "Toronto"
    assert fit("New York City", SMALL, SMALL.measure("NEW YORK")) == "New York"
    assert SMALL.measure(fit("Saint-Jean-sur-Richelieu", SMALL, 60)) <= 60


# ---------------------------------------------------------------- screens


def test_clock_am_pm_only_in_12h_and_seconds_toggle():
    top = range(0, 40)  # the time row; the date is below
    twelve = render("clock", NOON, None, Settings(clock_format="12h"))
    twenty_four = render("clock", NOON, None, Settings(clock_format="24h"))
    assert count(twelve, WHITE, top) > 0  # AM/PM is the only white up there
    assert count(twenty_four, WHITE, top) == 0

    with_seconds = render("clock", NOON, None, Settings(seconds=True))
    assert count(with_seconds, GOLD) > count(twelve, GOLD)


def test_clock_worst_cases_fit():
    for fmt, when in (("12h", datetime(2026, 1, 1, 12, 59, 59, tzinfo=TZ)),
                      ("24h", datetime(2026, 1, 1, 23, 59, 59, tzinfo=TZ))):
        frame = render("clock", when, None, Settings(clock_format=fmt, seconds=True))
        lit = [x for y in range(HEIGHT) for x in range(WIDTH) if frame.get(x, y) != (0, 0, 0)]
        assert min(lit) >= 2 and max(lit) <= WIDTH - 3  # a margin on both sides


def test_upcoming_hours(forecast):
    hours = upcoming_hours(forecast, NOON, step=2)
    assert [h.time.hour for h in hours] == [13, 15, 17, 19]
    assert [h.time.hour for h in upcoming_hours(forecast, NOON.replace(hour=23), step=3)] == [0, 3, 6, 9]
    late = forecast.hours[-1].time - timedelta(minutes=30)  # next full hour is the last one
    assert len(upcoming_hours(forecast, late, step=1)) == 1  # the forecast runs out


def test_every_screen_renders_all_day(forecast):
    for hour in range(24):
        now = datetime(2026, 10, 19, hour, 30, tzinfo=TZ)
        for screen in ("clock", "current", "hourly", "daily"):
            for settings in (Settings(), Settings(clock_format="24h", seconds=True, units="imperial", label="X")):
                frame = render(screen, now, forecast, settings)
                assert len(frame.to_bytes()) == WIDTH * HEIGHT * 3


def test_weather_screen_without_forecast():
    frame = render("hourly", NOON, None, Settings(label="Toronto"))
    assert count(frame, WHITE) > 0  # "NO WEATHER YET"


def test_unknown_screen():
    with pytest.raises(ValueError):
        render("radar", NOON, None, Settings())
