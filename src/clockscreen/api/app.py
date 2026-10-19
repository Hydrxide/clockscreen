"""HTTP API: HController's module contract, plus a preview page.

  GET  /health             always 200 while running; place, forecast age, last error
  GET  /render/frame       the panel's frame now: raw RGB (width*height*3), X-Width/X-Height
  GET  /render/frame.png   the same frame drawn as LED dots
  GET  /screen             which screen is on, why, for how long, and what it shows
  GET  /weather            the forecast (null until the first fetch)
  POST /control/show       {"screen": "hourly"} hold it for 30 s; {"screen": null} resume the cycle
  GET  /control/settings   clock format, units and location in use, and which are saved over config.yaml
  PUT  /control/clock      {"clock": {"format": "24h", "seconds": true}}; {"clock": null} back to config.yaml
  PUT  /control/units      {"units": "imperial"}; {"units": null} back to config.yaml
  PUT  /control/location   {"location": "Paris, France", "label": null} or "43.65, -79.38"; null back to config.yaml
  GET  /                   browser preview of the panel, with Show now buttons and the settings
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, ValidationError

from ..render.layouts import clock_parts, date_text, upcoming_hours
from ..runtime import SCREENS, SHOW_NOW_SECONDS, Runtime
from ..weather import codes
from ..weather.client import LocationNotFound, WeatherError

_PREVIEW_HTML = Path(__file__).with_name("preview.html")


class ShowRequest(BaseModel):
    screen: str | None  # one of clock/current/hourly/daily; None = back to the cycle


class ClockRequest(BaseModel):
    clock: dict[str, Any] | None  # {"format": "12h" | "24h", "seconds": bool}; None = back to config.yaml


class UnitsRequest(BaseModel):
    units: str | None  # metric | imperial; None = back to config.yaml


class LocationRequest(BaseModel):
    location: str | None  # a place name, or "latitude, longitude"; None = back to config.yaml
    label: str | None = None  # text on the weather screens (default: the place's name)


def _reason(exc: ValueError) -> str:
    if isinstance(exc, ValidationError):
        return "; ".join(e["msg"].removeprefix("Value error, ") for e in exc.errors())
    return str(exc)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def create_app(runtime: Runtime, manage_lifecycle: bool = True) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if manage_lifecycle:
            await runtime.start()
        yield
        if manage_lifecycle:
            await runtime.stop()

    app = FastAPI(title="clockscreen", lifespan=lifespan)
    weather = runtime.weather

    @app.get("/health")
    def health() -> dict[str, Any]:
        # Healthy whenever the server is up: the clock can always be drawn, and a missing
        # forecast only drops the weather screens. Diagnostics only; no outbound calls.
        now = datetime.now(timezone.utc)
        screen, _, source = runtime.screen()
        f = weather.forecast
        return {
            "ok": True,
            "now": now.isoformat(),
            "screen": screen,
            "source": source,
            "location": weather.place.describe() if weather.place else None,
            "label": weather.label,
            "forecast_fetched_at": _iso(f.fetched_at) if f else None,
            "forecast_fresh": weather.fresh(now),
            "last_error": weather.last_error,
            "next_attempt_at": _iso(weather.next_attempt_at),
            "api_requests": weather.client.request_count,
        }

    @app.get("/render/frame")
    def render_frame() -> Response:
        frame = runtime.frame()
        return Response(
            frame.to_bytes(),
            media_type="application/octet-stream",
            headers={"X-Width": str(frame.width), "X-Height": str(frame.height), "Cache-Control": "no-store"},
        )

    @app.get("/render/frame.png")
    def render_frame_png(pitch: int = 6) -> Response:
        return Response(runtime.frame().to_png(pitch=max(2, min(pitch, 12))), media_type="image/png",
                        headers={"Cache-Control": "no-store"})

    @app.get("/screen")
    def current_screen() -> dict[str, Any]:
        t = runtime.now()
        screen, left, source = runtime.screen(t)
        now = runtime.local(t)
        settings = runtime.settings()
        f = weather.forecast
        data: dict[str, Any] = {}
        if screen == "clock":
            hm, ampm = clock_parts(now, settings.clock_format)
            data = {"time": hm, "am_pm": ampm, "seconds": f"{now.second:02d}" if settings.seconds else None,
                    "date": date_text(now)}
        elif f and screen == "current":
            data = {**f.current.model_dump(mode="json"),
                    "condition": codes.condition(f.current.weather_code, f.current.is_day)}
        elif f and screen == "hourly":
            data = {"hours": [h.model_dump(mode="json") for h in upcoming_hours(f, now, settings.hour_step)]}
        elif f and screen == "daily":
            data = {"days": [d.model_dump(mode="json") for d in f.days if d.date > now.date()][:3]}
        return {
            "screen": screen,
            "source": source,
            "seconds_left": round(left, 1),
            "cycle": [e.model_dump() for e in runtime.config.cycle],
            "screens": list(SCREENS),
            "show_now_seconds": SHOW_NOW_SECONDS,
            "data": data,
        }

    @app.get("/weather")
    def get_weather() -> dict[str, Any]:
        f = weather.forecast
        return {
            "location": weather.place.model_dump(mode="json") if weather.place else None,
            "label": weather.label,
            "units": runtime.config.units,
            "fresh": weather.fresh(datetime.now(timezone.utc)),
            "last_error": weather.last_error,
            "forecast": f.model_dump(mode="json") if f else None,
        }

    @app.post("/control/show")
    def show_now(req: ShowRequest) -> dict[str, Any]:
        try:
            runtime.show_now(req.screen)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        screen, left, source = runtime.screen()
        return {"screen": screen, "source": source, "seconds_left": round(left, 1)}

    @app.get("/control/settings")
    def get_settings() -> dict[str, Any]:
        return runtime.settings_state()

    @app.put("/control/clock")
    def set_clock(req: ClockRequest) -> dict[str, Any]:
        try:
            runtime.set_clock(req.clock)
        except ValueError as exc:
            raise HTTPException(400, _reason(exc)) from exc
        return runtime.settings_state()

    @app.put("/control/units")
    async def set_units(req: UnitsRequest) -> dict[str, Any]:
        try:
            await runtime.set_units(req.units)
        except ValueError as exc:
            raise HTTPException(400, _reason(exc)) from exc
        return runtime.settings_state()

    @app.put("/control/location")
    async def set_location(req: LocationRequest) -> dict[str, Any]:
        try:
            await runtime.set_location(req.location, req.label)
        except LocationNotFound as exc:
            raise HTTPException(400, f"{exc}; try adding a region or country after a comma") from exc
        except ValueError as exc:
            raise HTTPException(400, _reason(exc)) from exc
        except (WeatherError, httpx.HTTPError) as exc:
            raise HTTPException(502, f"couldn't look the place up: {exc or type(exc).__name__}") from exc
        return runtime.settings_state()

    @app.get("/", response_class=HTMLResponse)
    def preview() -> str:
        return _PREVIEW_HTML.read_text(encoding="utf-8")

    return app
