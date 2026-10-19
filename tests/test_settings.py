"""Clock format, units and location chosen on the preview page: saved over config.yaml."""

import asyncio

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from clockscreen.api.app import create_app
from clockscreen.config import Config
from clockscreen.runtime import Runtime, location_choice
from clockscreen.state import State
from clockscreen.weather.client import FORECAST_URL, GEOCODING_URL, LocationNotFound

PARIS = {"results": [{"name": "Paris", "admin1": "Île-de-France", "country": "France",
                      "latitude": 48.85341, "longitude": 2.3488}]}


@pytest.fixture
def api_mock(fixture):
    with respx.mock(assert_all_called=False) as mock:
        mock.get(GEOCODING_URL, params={"name": "Toronto"}).mock(
            return_value=httpx.Response(200, json=fixture("geocode_toronto.json")))
        mock.get(GEOCODING_URL, params={"name": "Paris, France"}).mock(return_value=httpx.Response(200, json=PARIS))
        mock.get(GEOCODING_URL, params={"name": "Nowhereville"}).mock(return_value=httpx.Response(200, json={}))
        mock.get(FORECAST_URL).mock(return_value=httpx.Response(200, json=fixture("forecast_toronto.json")))
        yield mock


def forecast_calls(mock):
    return [c for c in mock.calls if c.request.url.host == "api.open-meteo.com"]


def test_location_choice():
    assert location_choice("  Paris, France ") == {"name": "Paris, France"}
    assert location_choice("49.28, -123.12", label=" HOME ") == {"latitude": 49.28, "longitude": -123.12, "label": "HOME"}
    assert location_choice("-33.9,18.4") == {"latitude": -33.9, "longitude": 18.4}
    for bad in ("", "   ", "95, 10"):
        with pytest.raises(ValueError):
            location_choice(bad)


def test_clock_choice_is_saved_and_reset(tmp_path):
    path = tmp_path / "clockscreen-state.json"
    runtime = Runtime(Config(), state_path=path)
    runtime.set_clock({"format": "24h", "seconds": True})
    assert runtime.config.clock.format == "24h" and runtime.settings().seconds is True

    again = Runtime(Config(), state_path=path)  # a restart keeps it, whatever config.yaml says
    assert again.config.clock.format == "24h" and again.settings_state()["saved"]["clock"] is True

    again.set_clock(None)
    assert again.config.clock.format == "12h" and not again.settings_state()["saved"]["clock"]
    assert "clock" not in State(path)._data

    with pytest.raises(ValueError):
        again.set_clock({"format": "13h"})


def test_unusable_saved_choice_is_ignored(tmp_path):
    path = tmp_path / "clockscreen-state.json"
    state = State(path)
    state.set("units", "kelvin")
    state.set("clock", {"format": "24h", "seconds": False})
    runtime = Runtime(Config.model_validate({"units": "imperial"}), state_path=path)
    assert runtime.config.units == "imperial"  # config.yaml's, not the broken saved value
    assert runtime.config.clock.format == "24h"  # the other saved choice still applies


async def test_units_refetch(api_mock):
    runtime = Runtime(Config())
    await runtime.weather.update()
    await runtime.set_units("imperial")
    assert forecast_calls(api_mock)[-1].request.url.params["temperature_unit"] == "fahrenheit"
    assert runtime.weather.forecast.units == "imperial"
    with pytest.raises(ValueError):
        await runtime.set_units("kelvin")
    await runtime.set_units(None)
    assert runtime.weather.forecast.units == "metric"


async def test_location_by_name(api_mock):
    runtime = Runtime(Config())
    await runtime.weather.update()
    await runtime.set_location("Paris, France")
    assert runtime.weather.place.name == "Paris" and runtime.weather.label == "Paris"
    assert forecast_calls(api_mock)[-1].request.url.params["latitude"] == "48.85341"
    assert runtime.settings_state()["location"] == {"text": "Paris, France", "label": None}

    with pytest.raises(LocationNotFound):
        await runtime.set_location("Nowhereville")
    assert runtime.weather.place.name == "Paris"  # nothing changed

    await runtime.set_location(None)
    assert runtime.weather.place.name == "Toronto"
    assert runtime.weather.forecast is not None and runtime.weather.forecast.place.name == "Toronto"


async def test_location_by_coordinates(api_mock):
    runtime = Runtime(Config())
    await runtime.set_location("49.28, -123.12", label="Cottage")
    assert not [c for c in api_mock.calls if c.request.url.host.startswith("geocoding")]
    assert runtime.weather.label == "Cottage"
    assert runtime.settings_state()["location"] == {"text": "49.28, -123.12", "label": "Cottage"}

    await runtime.set_location("49.28, -123.12")
    assert runtime.weather.label == ""  # the default name "Toronto" isn't used for someone else's coordinates


async def test_reconfigure_restarts_the_wait(api_mock):
    runtime = Runtime(Config())
    runtime.weather.start()
    for _ in range(50):
        if runtime.weather.forecast:
            break
        await asyncio.sleep(0.01)
    await runtime.set_units("imperial")
    await asyncio.sleep(0.05)
    assert len(forecast_calls(api_mock)) == 2  # the first fetch and the units change; no extra one
    await runtime.stop()


def test_settings_api(api_mock, tmp_path):
    runtime = Runtime(Config(), state_path=tmp_path / "clockscreen-state.json")
    api = TestClient(create_app(runtime, manage_lifecycle=False))

    body = api.get("/control/settings").json()
    assert body["clock"] == {"format": "12h", "seconds": False} and body["units"] == "metric"
    assert body["saved"] == {"clock": False, "units": False, "location": False}
    assert body["config_file"]["location"] == "Toronto"

    body = api.put("/control/clock", json={"clock": {"format": "24h", "seconds": True}}).json()
    assert body["clock"] == {"format": "24h", "seconds": True} and body["saved"]["clock"]
    assert api.put("/control/clock", json={"clock": {"format": "25h"}}).status_code == 400

    body = api.put("/control/units", json={"units": "imperial"}).json()
    assert body["units"] == "imperial" and body["last_error"] is None
    assert api.put("/control/units", json={"units": "kelvin"}).status_code == 400

    body = api.put("/control/location", json={"location": "Paris, France", "label": "PARIS"}).json()
    assert body["place"].startswith("Paris, Île-de-France, France") and body["label"] == "PARIS"

    r = api.put("/control/location", json={"location": "Nowhereville"})
    assert r.status_code == 400 and "Nowhereville" in r.json()["detail"]
    assert api.put("/control/location", json={"location": "95, 10"}).status_code == 400

    api_mock.get(GEOCODING_URL, params={"name": "Oslo"}).mock(side_effect=httpx.ConnectError("offline"))
    r = api.put("/control/location", json={"location": "Oslo"})
    assert r.status_code == 502 and "offline" in r.json()["detail"]

    body = api.put("/control/location", json={"location": None}).json()
    assert body["saved"]["location"] is False and body["place"].startswith("Toronto")
