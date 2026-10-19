"""Open-Meteo parsing, the client, and the service that keeps the forecast fresh."""

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx
import pytest
import respx

from clockscreen.config import Config
from clockscreen.poller import STALE_AFTER, WeatherService
from clockscreen.state import State
from clockscreen.weather import codes, parsers
from clockscreen.weather.client import FORECAST_URL, GEOCODING_URL, LocationNotFound, WeatherClient, WeatherError
from clockscreen.weather.models import Place

TZ = ZoneInfo("America/Toronto")
TORONTO = Place(name="Toronto", region="Ontario", country="Canada", latitude=43.70643, longitude=-79.39864)


def make_service(config: Config | None = None, state: State | None = None) -> WeatherService:
    return WeatherService(config or Config(), WeatherClient(), state or State(None))


# ---------------------------------------------------------------- parsing


def test_parse_place(fixture):
    place = parsers.parse_place(fixture("geocode_toronto.json"))
    assert place == TORONTO
    assert place.describe() == "Toronto, Ontario, Canada (43.7064, -79.3986)"


def test_parse_place_no_results():
    assert parsers.parse_place({"generationtime_ms": 0.1}) is None


def test_parse_forecast(fixture):
    fetched = datetime(2026, 10, 19, 16, 5, tzinfo=timezone.utc)
    forecast = parsers.parse_forecast(fixture("forecast_toronto.json"), place=TORONTO, units="metric", tz=TZ,
                                      fetched_at=fetched)
    c = forecast.current
    assert c.time == datetime(2026, 10, 19, 12, 0, tzinfo=TZ)
    assert (c.temperature, c.feels_like, c.humidity, c.weather_code, c.is_day) == (16.2, 13.5, 50, 0, True)
    assert (c.wind_speed, c.wind_direction) == (11.5, 230)
    assert len(forecast.hours) == 96
    assert forecast.hours[0].time == datetime(2026, 10, 19, 0, 0, tzinfo=TZ)  # local midnight
    assert forecast.hours[0].is_day is False
    assert [d.date for d in forecast.days] == [date(2026, 10, d) for d in (19, 20, 21, 22)]
    assert (forecast.days[1].high, forecast.days[1].low, forecast.days[1].weather_code) == (15.2, 6.5, 3)


def test_parse_forgives_gaps():
    raw = {
        "current": {"time": 1792425600, "temperature_2m": 3.0, "weather_code": 71},
        "hourly": {"time": [1792425600, 1792429200], "temperature_2m": [3.0, None], "weather_code": [71, 73]},
        "daily": {"time": [1792382400], "weather_code": [71], "temperature_2m_max": [4.0]},  # no min
    }
    forecast = parsers.parse_forecast(raw, place=TORONTO, units="metric", tz=TZ, fetched_at=datetime.now(timezone.utc))
    assert forecast.current.feels_like == 3.0  # falls back to the temperature
    assert len(forecast.hours) == 1 and forecast.hours[0].precip_chance is None
    assert forecast.days == []


def test_parse_needs_current_conditions():
    with pytest.raises(ValueError):
        parsers.parse_current({"current": {"time": 1792425600}}, TZ)


def test_weather_codes():
    assert codes.condition(0, is_day=True) == "SUNNY" and codes.condition(0, is_day=False) == "CLEAR"
    assert codes.condition(95) == "THUNDERSTORM" and codes.icon_kind(95) == "storm"
    assert codes.icon_kind(66) == "freezing" and codes.icon_kind(85) == "snow"
    assert codes.condition(1234) == "" and codes.icon_kind(1234) == "cloudy"  # unknown code
    assert {codes.icon_kind(c) for c in codes._CODES} == set(codes.ICON_KINDS)


# ---------------------------------------------------------------- client


@respx.mock
async def test_forecast_request_params(fixture):
    route = respx.get(FORECAST_URL).mock(return_value=httpx.Response(200, json=fixture("forecast_toronto.json")))
    client = WeatherClient()
    forecast = await client.forecast(TORONTO, timezone_name="America/Toronto", units="imperial")
    params = route.calls.last.request.url.params
    assert params["timezone"] == "America/Toronto" and params["timeformat"] == "unixtime"
    assert params["temperature_unit"] == "fahrenheit" and params["wind_speed_unit"] == "mph"
    assert params["latitude"] == "43.70643"
    assert forecast.units == "imperial" and forecast.place == TORONTO
    await client.aclose()


@respx.mock
async def test_api_error_reason():
    respx.get(FORECAST_URL).mock(return_value=httpx.Response(400, json={"error": True, "reason": "Latitude must be in range"}))
    client = WeatherClient()
    with pytest.raises(WeatherError, match="HTTP 400: Latitude must be in range"):
        await client.forecast(TORONTO, timezone_name="America/Toronto", units="metric")
    await client.aclose()


@respx.mock
async def test_geocode_not_found():
    respx.get(GEOCODING_URL).mock(return_value=httpx.Response(200, json={"generationtime_ms": 0.1}))
    client = WeatherClient()
    with pytest.raises(LocationNotFound):
        await client.geocode("Nowhereville")
    await client.aclose()


# ---------------------------------------------------------------- service


@respx.mock
async def test_geocode_is_cached(fixture, tmp_path):
    geo = respx.get(GEOCODING_URL).mock(return_value=httpx.Response(200, json=fixture("geocode_toronto.json")))
    respx.get(FORECAST_URL).mock(return_value=httpx.Response(200, json=fixture("forecast_toronto.json")))
    path = tmp_path / "clockscreen-state.json"

    first = make_service(state=State(path))
    assert await first.update() == 15 * 60
    assert geo.call_count == 1 and first.place == TORONTO and first.label == "Toronto"

    second = make_service(state=State(path))  # a restart
    await second.update()
    assert geo.call_count == 1 and second.place == TORONTO

    renamed = make_service(Config.model_validate({"location": {"name": "Toronto, Ontario"}}), State(path))
    await renamed.update()
    assert geo.call_count == 2  # a different query is looked up again


@respx.mock
async def test_coordinates_skip_the_lookup(fixture):
    geo = respx.get(GEOCODING_URL)
    forecast = respx.get(FORECAST_URL).mock(return_value=httpx.Response(200, json=fixture("forecast_toronto.json")))

    service = make_service(Config.model_validate({"location": {"latitude": 49.28, "longitude": -123.12}}))
    await service.update()
    assert geo.call_count == 0
    assert forecast.calls.last.request.url.params["latitude"] == "49.28"
    assert service.label == ""  # the default name "Toronto" isn't used for someone else's coordinates

    named = make_service(Config.model_validate({"location": {"name": "Cottage", "latitude": 45, "longitude": -79}}))
    await named.update()
    assert geo.call_count == 0 and named.label == "Cottage"

    labelled = make_service(Config.model_validate({"location": {"label": "HOME"}}))
    assert labelled.label == "HOME"


@respx.mock
async def test_failures_back_off_and_keep_the_last_forecast(fixture):
    respx.get(GEOCODING_URL).mock(return_value=httpx.Response(200, json=fixture("geocode_toronto.json")))
    forecast = respx.get(FORECAST_URL).mock(return_value=httpx.Response(200, json=fixture("forecast_toronto.json")))
    service = make_service()
    await service.update()
    good = service.forecast

    forecast.mock(side_effect=httpx.ConnectError("no route to host"))
    assert [await service.update() for _ in range(7)] == [30, 60, 120, 240, 480, 900, 900]
    assert service.forecast is good
    assert service.last_error == "no route to host"

    forecast.mock(return_value=httpx.Response(500))
    await service.update()
    assert service.last_error == "HTTP 500"

    forecast.mock(return_value=httpx.Response(200, json=fixture("forecast_toronto.json")))
    assert await service.update() == 900
    assert service.last_error is None and service.forecast is not good
    assert await service.update() == 900


@respx.mock
async def test_location_lookup_failure_is_retried():
    respx.get(GEOCODING_URL).mock(return_value=httpx.Response(200, json={}))
    service = make_service(Config.model_validate({"location": {"name": "Nowhereville"}}))
    assert await service.update() == 30
    assert service.place is None and "Nowhereville" in service.last_error
    assert service.label == "Nowhereville"


def test_freshness(fixture):
    service = make_service()
    now = datetime(2026, 10, 19, 18, 0, tzinfo=timezone.utc)
    assert not service.fresh(now)
    service.forecast = parsers.parse_forecast(fixture("forecast_toronto.json"), place=TORONTO, units="metric", tz=TZ,
                                              fetched_at=now)
    assert service.fresh(now + STALE_AFTER)
    assert not service.fresh(now + STALE_AFTER + timedelta(seconds=1))
