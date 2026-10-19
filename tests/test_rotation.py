"""The cycle: which screen is on at a given time."""

from clockscreen.config import Config, CycleEntry
from clockscreen.rotation import pick

CYCLE = Config().cycle  # clock 20, current 10, hourly 8, daily 8: 46 s
T0 = 46 * 1_000_000  # an epoch time at the start of a cycle


def test_walks_the_cycle():
    assert pick(CYCLE, T0, weather=True) == ("clock", 20)
    assert pick(CYCLE, T0 + 19.5, weather=True) == ("clock", 0.5)
    assert pick(CYCLE, T0 + 20, weather=True) == ("current", 10)
    assert pick(CYCLE, T0 + 30, weather=True) == ("hourly", 8)
    assert pick(CYCLE, T0 + 45, weather=True) == ("daily", 1)
    assert pick(CYCLE, T0 + 46, weather=True) == ("clock", 20)  # and round again


def test_without_weather_only_the_clock():
    for t in range(0, 92, 3):
        assert pick(CYCLE, T0 + t, weather=False)[0] == "clock"


def test_repeated_screens():
    cycle = [CycleEntry(screen="clock", dwell=10), CycleEntry(screen="current", dwell=5),
             CycleEntry(screen="clock", dwell=10), CycleEntry(screen="daily", dwell=5)]
    seen = [pick(cycle, 30 * 1000 + t, weather=True)[0] for t in range(0, 30, 5)]
    assert seen == ["clock", "clock", "current", "clock", "clock", "daily"]


def test_weather_only_cycle_falls_back_to_the_clock():
    cycle = [CycleEntry(screen="current", dwell=10)]
    assert pick(cycle, T0, weather=False)[0] == "clock"
    assert pick(cycle, T0, weather=True)[0] == "current"
