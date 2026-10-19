"""Config loading and validation."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from clockscreen.config import Config, load_config

ROOT = Path(__file__).resolve().parents[1]


def test_defaults():
    config = Config()
    assert config.server.port == 9300
    assert config.location.name == "Toronto" and config.location.coordinates is None
    assert config.clock.format == "12h" and config.clock.seconds is False
    assert [e.screen for e in config.cycle] == ["clock", "current", "hourly", "daily"]


def test_example_config_matches_defaults():
    assert load_config(ROOT / "config.example.yaml") == Config()


def test_missing_file_means_defaults():
    assert load_config(None) == Config()


def test_yaml_values(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        "clock: {format: 24h, seconds: on}\n"
        "units: imperial\n"
        "location: {latitude: 49.28, longitude: -123.12, label: HOME}\n",
        encoding="utf-8",
    )
    config = load_config(path)
    assert config.clock.format == "24h" and config.clock.seconds is True  # YAML 1.1: on = true
    assert config.units == "imperial"
    assert config.location.coordinates == (49.28, -123.12)


def test_timezone_spelling_is_canonical():
    # macOS would load "america/toronto" (case-insensitive disk); the Pi wouldn't.
    assert Config.model_validate({"timezone": "america/toronto"}).timezone == "America/Toronto"


def test_bare_number_clock_format():
    assert Config.model_validate({"clock": {"format": 24}}).clock.format == "24h"


@pytest.mark.parametrize(
    "data",
    [
        {"timezone": "Mars/Olympus"},
        {"clock": {"format": "13h"}},
        {"location": {"latitude": 43.6}},  # longitude missing
        {"location": {"name": ""}},  # nothing to look up
        {"location": {"latitude": 95, "longitude": 0}},
        {"cycle": []},
        {"cycle": [{"screen": "radar", "dwell": 5}]},
        {"cycle": [{"screen": "clock", "dwell": 0}]},
        {"weather": {"refresh_minutes": 1}},
        {"weather": {"hour_step": 0}},
    ],
)
def test_rejects(data):
    with pytest.raises(ValidationError):
        Config.model_validate(data)
