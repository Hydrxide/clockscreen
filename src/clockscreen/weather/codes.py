"""WMO weather codes (Open-Meteo's ``weather_code``) -> condition text and icon.

Icon kinds: clear, partly, cloudy, fog, drizzle, rain, freezing, snow, storm. Clear and
partly have night versions (moon instead of sun), picked with ``is_day``.
"""

from __future__ import annotations

ICON_KINDS = ("clear", "partly", "cloudy", "fog", "drizzle", "rain", "freezing", "snow", "storm")

# code -> (text, icon). Texts fit one line of the regular font across the panel.
_CODES: dict[int, tuple[str, str]] = {
    0: ("CLEAR", "clear"),
    1: ("MAINLY CLEAR", "partly"),
    2: ("PARTLY CLOUDY", "partly"),
    3: ("CLOUDY", "cloudy"),
    45: ("FOG", "fog"),
    48: ("FREEZING FOG", "fog"),
    51: ("LIGHT DRIZZLE", "drizzle"),
    53: ("DRIZZLE", "drizzle"),
    55: ("HEAVY DRIZZLE", "drizzle"),
    56: ("FREEZING DRIZZLE", "freezing"),
    57: ("FREEZING DRIZZLE", "freezing"),
    61: ("LIGHT RAIN", "rain"),
    63: ("RAIN", "rain"),
    65: ("HEAVY RAIN", "rain"),
    66: ("FREEZING RAIN", "freezing"),
    67: ("FREEZING RAIN", "freezing"),
    71: ("LIGHT SNOW", "snow"),
    73: ("SNOW", "snow"),
    75: ("HEAVY SNOW", "snow"),
    77: ("SNOW GRAINS", "snow"),
    80: ("SHOWERS", "rain"),
    81: ("SHOWERS", "rain"),
    82: ("HEAVY SHOWERS", "rain"),
    85: ("SNOW SHOWERS", "snow"),
    86: ("SNOW SHOWERS", "snow"),
    95: ("THUNDERSTORM", "storm"),
    96: ("STORM WITH HAIL", "storm"),
    99: ("STORM WITH HAIL", "storm"),
}

# During the day "clear" reads better as sunny.
_DAY_TEXT = {0: "SUNNY", 1: "MOSTLY SUNNY"}


def condition(code: int, is_day: bool = True) -> str:
    if is_day and code in _DAY_TEXT:
        return _DAY_TEXT[code]
    return _CODES.get(code, ("", "cloudy"))[0]


def icon_kind(code: int) -> str:
    return _CODES.get(code, ("", "cloudy"))[1]
