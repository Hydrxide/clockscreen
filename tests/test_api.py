"""The HTTP API: HController's module contract (/health, /render/frame) and the controls."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from clockscreen.api.app import create_app
from clockscreen.config import Config
from clockscreen.runtime import SHOW_NOW_SECONDS, Runtime
from clockscreen.weather import parsers
from clockscreen.weather.client import FORECAST_URL, GEOCODING_URL
from clockscreen.weather.models import Place

TZ = ZoneInfo("America/Toronto")
TORONTO = Place(name="Toronto", latitude=43.70643, longitude=-79.39864)
# 12:00:20 in Toronto on the fixture's day, 20 s into the default 46 s cycle: "current".
T = 1792425600 + 46 * 2 - (1792425600 % 46) + 20


class Clock:
    def __init__(self, t: float) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t


@pytest.fixture
def clock():
    return Clock(T)


@pytest.fixture
def runtime(clock):
    return Runtime(Config(), clock=clock)


@pytest.fixture
def api(runtime):
    return TestClient(create_app(runtime, manage_lifecycle=False))


@pytest.fixture
def with_forecast(runtime, fixture):
    runtime.weather.place = TORONTO
    runtime.weather.forecast = parsers.parse_forecast(
        fixture("forecast_toronto.json"), place=TORONTO, units="metric", tz=TZ,
        fetched_at=datetime.fromtimestamp(T, timezone.utc),
    )


def test_frame_contract(api):
    r = api.get("/render/frame")
    assert r.status_code == 200
    assert len(r.content) == 128 * 64 * 3
    assert r.headers["x-width"] == "128" and r.headers["x-height"] == "64"
    assert r.headers["cache-control"] == "no-store"


def test_frame_png(api):
    r = api.get("/render/frame.png?pitch=2")
    assert r.status_code == 200 and r.content.startswith(b"\x89PNG")


def test_health_is_ok_without_weather(api):
    r = api.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["forecast_fresh"] is False and body["location"] is None
    assert body["label"] == "Toronto"


def test_clock_only_until_the_forecast_arrives(api, clock):
    for dt in range(0, 46, 2):
        clock.t = T + dt
        assert api.get("/screen").json()["screen"] == "clock"


def test_cycle_with_weather(api, with_forecast):
    body = api.get("/screen").json()
    assert body["screen"] == "current" and body["source"] == "cycle"
    assert body["data"]["temperature"] == 16.2 and body["data"]["condition"] == "SUNNY"
    assert api.get("/health").json()["location"].startswith("Toronto")
    assert api.get("/weather").json()["forecast"]["current"]["temperature"] == 16.2


def test_stale_forecast_drops_the_weather_screens(api, clock, with_forecast):
    clock.t = T + 3 * 3600 + 46  # same cycle position, forecast now over 3 h old
    assert api.get("/screen").json()["screen"] == "clock"


def test_show_now(api, clock, with_forecast):
    r = api.post("/control/show", json={"screen": "daily"})
    assert r.status_code == 200 and r.json()["screen"] == "daily"
    body = api.get("/screen").json()
    assert body["source"] == "show" and len(body["data"]["days"]) == 3

    clock.t += SHOW_NOW_SECONDS - 1
    assert api.get("/screen").json()["screen"] == "daily"
    clock.t += 1
    assert api.get("/screen").json()["source"] == "cycle"

    api.post("/control/show", json={"screen": "hourly"})
    api.post("/control/show", json={"screen": None})
    assert api.get("/screen").json()["source"] == "cycle"

    assert api.post("/control/show", json={"screen": "radar"}).status_code == 400


def test_show_now_weather_without_a_forecast(api):
    api.post("/control/show", json={"screen": "hourly"})
    assert api.get("/screen").json()["screen"] == "hourly"
    assert api.get("/render/frame").status_code == 200  # draws "NO WEATHER YET"


def test_preview_page(api):
    r = api.get("/")
    assert r.status_code == 200 and "clockscreen" in r.text and "Open-Meteo" in r.text


@respx.mock
def test_lifecycle_fetches_the_forecast(fixture, tmp_path):
    respx.get(GEOCODING_URL).mock(return_value=httpx.Response(200, json=fixture("geocode_toronto.json")))
    respx.get(FORECAST_URL).mock(return_value=httpx.Response(200, json=fixture("forecast_toronto.json")))
    runtime = Runtime(Config(), state_path=tmp_path / "clockscreen-state.json")
    with TestClient(create_app(runtime)) as api:
        for _ in range(100):
            if api.get("/health").json()["forecast_fetched_at"]:
                break
        body = api.get("/health").json()
        assert body["location"].startswith("Toronto, Ontario, Canada")
        assert body["forecast_fresh"] is True and body["last_error"] is None
    assert (tmp_path / "clockscreen-state.json").exists()
