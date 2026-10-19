# clockscreen: context for Claude sessions

A clock and local weather for the user's 128×64 LED panel, as an **HController module** (`~/HController`, the hub on :1630 that runs modules and owns the panel; `~/HController/docs/modules.md` is the contract). It cycles a clock screen and three weather screens itself, because HController doesn't rotate between overlapping schedule windows. `README.md` is the user-facing guide, including the copy-paste HController setup; this file holds the decisions and conventions. Sibling module: `~/nhlscreen` (same stack; the renderer came from there).

## Commands

```bash
/opt/anaconda3/bin/python3.13 -m venv .venv && .venv/bin/pip install -e '.[dev]'   # setup (system python3 is 3.9)
.venv/bin/pytest -q                                          # offline, ~1s
.venv/bin/python -m clockscreen                              # live Open-Meteo data -> http://127.0.0.1:9300/
.venv/bin/python tools/render_previews.py --out previews/    # every screen + worst cases -> LED PNGs
```

`config.yaml` (gitignored) overrides defaults; copy `config.example.yaml`. macOS has no `timeout`; run servers as background tasks. Stop a hand-started copy before HController runs it, or HController reports a port **conflict**.

## Decisions (made by the user; keep them unless asked)

- **Weather: Open-Meteo.** No API key, which matters because module config files are readable by anyone on the LAN through HController's dashboard. Free non-commercial use is limited to 10k calls a day. The data is CC BY 4.0, and the preview page credits it.
- **Views:** current conditions, the next few hours, and the next few days, all in the cycle.
- **Clock:** `clock.format` is `12h` or `24h`, and AM/PM is *always* shown in 12h. `clock.seconds` is an on/off toggle.
- **Location:** set in config, anywhere in the world:
  - `name`, geocoded once and cached in `clockscreen-state.json` keyed by the query;
  - or `latitude`/`longitude`, which win over name, and then `name` is only the label, but only if it was set explicitly (`model_fields_set`), so the default "Toronto" never labels someone else's coordinates.
- **Preview-page settings** (added 2026-10-19 at the user's request): the time format and seconds, the timezone, the units, and the location (a name or `lat, lon`, plus an optional label).
  - They're saved in `clockscreen-state.json` under the keys `clock`, `timezone`, `units` and `location`, with one key per choice like nhlscreen, and win over `config.yaml` until **Reset to config**.
  - `Runtime._effective()` layers them over `file_config.model_dump(exclude_unset=True)`, which keeps the label rule intact.
  - A new location is geocoded before it's saved, so a non-match is a 400 and nothing changes.
  - Units and location changes go through `WeatherService.reconfigure`, which fetches straight away under the service's lock and restarts the loop's wait.
  - The wind label uses `forecast.units`, so a failed refetch after a units change still shows consistent data.
- **The clock's timezone is separate from the weather location** (the user picked this over "the clock follows the location", 2026-10-19). `timezone` drives the clock, the hourly labels (converted to `now.tzinfo` at draw time) and the forecast's day boundaries, which are refetched on a change. Names are canonicalised against `zoneinfo.available_timezones()` (`config.canonical_timezone`), because macOS would accept the wrong case and the Pi wouldn't.
- **Docs:** HController's repo gets no doc changes for this module. The setup instructions live only in this README's "Running it on HController" section, written for an outside user on a fresh machine. `tests/test_docs.py` checks its YAML block against the code.
- Port 9300, and the repo is private (`Hydrxide/clockscreen`).

## Architecture

```
config.yaml -> config.py ──► runtime.py wires:
  poller.py (WeatherService) ── weather/client.py (httpx) ── weather/parsers.py -> weather/models.py
  rotation.py (pure: cycle + time -> screen) · Show now override (runtime, 30 s)
  render/layouts.py (4 screens) ── fonts.py (REGULAR/SMALL from nhlscreen + BIG) · icons.py · canvas.py
  api/app.py (/health, /render/frame, ...) + api/preview.html
```

| Module | Role |
|---|---|
| `weather/parsers.py` | **The only code that touches raw Open-Meteo JSON.** Forgiving: rows with missing values are skipped. The forecast is requested with `timeformat=unixtime`, so times are exact instants; daily times are local midnight. |
| `runtime.py` | `file_config` (config.yaml) plus the saved preview-page choices = `config`. `set_clock` / `set_units` / `set_location`, Show now. |
| `poller.py` | Resolve the place, then fetch every `refresh_minutes`. On failure it keeps the last good forecast and backs off 30 s, doubling up to the refresh interval. `STALE_AFTER` is 3 h; after that the weather screens drop out of the cycle. |
| `rotation.py` | Pure function of the time: the screen at `epoch mod total dwell`, over the screens available right now. There's no counter, so every request agrees (modules.md: render from the clock, never from the request count). |
| `render/fonts.py` | REGULAR/SMALL are copied from nhlscreen, plus `°`; `normalize` keeps `°` through the ASCII fold. BIG is 16×28 tabular digits and a colon, generated from stroke outlines and touched up by hand; edit the grids directly. |
| `render/icons.py` | Palette pixel art at 32 px and 16 px for 9 kinds (`weather/codes.ICON_KINDS`), with day and night versions of clear and partly. The grids were generated, then hand-fixed (the 16 px sun, partly-sunny and drizzle are hand-drawn). |

## Display conventions

- Same colours as nhlscreen: values (time, temperatures) gold (255,176,0), labels white, chance of precipitation light blue. Draw on black at full intensity; HController applies brightness.
- **Clock:** BIG time centred. A right-hand column holds AM/PM (REGULAR 1×) at the top and the seconds (REGULAR 2×) at the bottom. The date is below in REGULAR. In 12h there's no leading zero; in 24h the hour is zero-padded.
- **Current:**
  - top line (SMALL): the label, trimmed to fit, and the time;
  - the 32 px icon;
  - the temperature at REGULAR 3×, with feels-like under it;
  - the condition text;
  - a bottom line with H/L and the wind.
- **Hourly:** 4 × 32 px columns from the next full hour. **Daily:** 3 columns from tomorrow, because today's H/L is on Current. Precipitation is shown from 10% (`SHOW_PRECIP_FROM`).
- Weather screens with no forecast (only reachable with Show now) draw `NO WEATHER YET`.

## Working conventions

- **Tests:** no network. They use the recorded fixtures in `tests/fixtures/` (Toronto, 2026-10-19) with respx; the API tests use a fake clock.
- **Visual changes:** run `tools/render_previews.py` and look at the PNGs (Claude can Read them) before calling a layout done. Check the worst cases.
- **Restarting:** `preview.html` is re-read on every request; Python isn't, so restart after backend changes.
- **Docs:** keep the README's HController block in step with the defaults (the test enforces the port, command and paths). Update `README.md` when user-facing behaviour changes. Python ≥3.11 (Raspberry Pi OS Bookworm ships 3.11).
