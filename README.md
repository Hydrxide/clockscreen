# clockscreen

A clock and local weather for a 128 × 64 LED panel. It cycles between the time and three weather screens, and runs as a module of [HController](https://github.com/Hydrxide/HController), the hub that owns the panel and decides which app is on it.

| Screen | Shows |
|---|---|
| **Clock** | The time in large digits (12-hour with AM/PM, or 24-hour; seconds optional) and the date |
| **Current conditions** | Weather icon, temperature, feels-like, condition (`PARTLY CLOUDY`), today's high/low, wind, the place's name and the time |
| **Next hours** | Four columns, 2 hours apart by default: time, icon, temperature, chance of precipitation (from 10%) |
| **Next days** | The next three days: day, icon, high, low, chance of precipitation |

Weather comes from [Open-Meteo](https://open-meteo.com/): free, no API key or sign-up, and it covers the whole world. Until the first forecast arrives, or if the forecast is more than 3 hours old, the panel shows only the clock.

## Quick start

```bash
git clone https://github.com/Hydrxide/clockscreen.git ~/clockscreen && cd ~/clockscreen
python3 -m venv .venv
.venv/bin/pip install -e .
cp config.example.yaml config.yaml     # optional: it runs on the defaults without one
.venv/bin/python -m clockscreen        # preview at http://127.0.0.1:9300/
```

On Windows, use `.venv\Scripts\` in place of `.venv/bin/`. Python 3.11 or newer is required.

The preview page draws exactly what the panel shows, as LED dots, with **Show now** buttons and the forecast's status. To use it as a module, stop it again (Ctrl+C) and let HController run it. HController won't start a second copy while this one holds the port.

## Running it on HController

These steps set it up from scratch on the machine that runs HController (a Raspberry Pi, or a Mac or PC for testing). They assume HController is already installed and working; see its README.

**1. Install clockscreen next to HController.**

```bash
git clone https://github.com/Hydrxide/clockscreen.git ~/clockscreen && cd ~/clockscreen
python3 -m venv .venv
.venv/bin/pip install -e .
```

There's no need to create `config.yaml` now. Until it exists, HController's config editor starts from `config.example.yaml`, and clockscreen runs on its defaults (Toronto, °C, 12-hour clock).

**2. Register it.** Paste this block under `modules:` in HController's `hcontroller.yaml`:

<!-- hcontroller-module: tests/test_docs.py checks this block against the code -->
```yaml
  clockscreen:
    name: Clock & Weather
    cwd: ~/clockscreen                             # where you cloned it
    command: [.venv/bin/python, -m, clockscreen]   # picks up ~/clockscreen/config.yaml if it exists
    url: http://127.0.0.1:9300                     # the port must match server.port in clockscreen's config
    health: /health                                # always healthy while running: the clock can always be drawn
    ui: /                                          # set clockscreen's server.host to 0.0.0.0 for this link to work from other devices
    display: {frame: /render/frame}
    config_file: config.yaml
    config_example: config.example.yaml            # the editor starts from this until config.yaml exists
    process: always                                # or: scheduled (runs only around its schedule windows)
    restart: on-failure
```

clockscreen doesn't log each frame request, so it needs no `log_ignore`. If you cloned somewhere other than `~/clockscreen`, change `cwd`.

**3. Restart HController,** which reads `hcontroller.yaml` only at startup: `sudo systemctl restart hcontroller` on a Pi, or stop and start `.venv/bin/python -m hcontroller` elsewhere. Then on the dashboard (`http://<that machine>:1630/`), the **Clock & Weather** card should go from **starting** to **healthy** within a few seconds.

**4. Put it on the panel.** To try it straight away, press **Show now → Clock & Weather** in the LED panel section. To keep it there, add a window in the dashboard's **Schedule**, or in `hcontroller.yaml` under `display:`. For example, to make it what the panel shows whenever no other window applies:

```yaml
display:
  default: clockscreen
```

or to show it every morning:

```yaml
display:
  schedule:
    - {module: clockscreen, days: daily, start: "06:00", end: "09:00"}
```

Quote the times. `days` can also be `weekdays`, `weekends` or a list like `[sat, sun]`, and a window can set its own `brightness`.

**5. Set it up from the dashboard.** Open the card's **Config file** editor to set the location, units, clock format, seconds and the cycle (see [Configuration](#configuration)), then **Save & restart**. Within a few seconds the logs show the place the name was matched to, for example `Location 'Toronto' is Toronto, Ontario, Canada (43.7064, -79.3986)`, and then the first forecast.

**If something's wrong:**
- **conflict:** something else holds port 9300, probably a copy you started by hand. Stop it, and HController starts its own within 5 s.
- **Changing the port:** set it in both places: `server.port` in clockscreen's config, and the port in the module's `url`. Then restart HController.
- **Only the clock shows:** the forecast hasn't arrived yet, or is over 3 hours old. The card's **Logs** show why (no network, a place name with no match), and clockscreen keeps retrying.
- **The Open link doesn't load from your phone:** set `server: {host: 0.0.0.0}` in clockscreen's config.
- **Its own systemd unit:** there isn't one, and it doesn't need one, because HController runs it.

## Configuration

Copy `config.example.yaml` to `config.yaml` (or edit it from HController's dashboard). Every key is optional.

**Location.** It can be anywhere in the world, given in either of two ways:

```yaml
location:
  name: Toronto          # looked up once through Open-Meteo's geocoding, then remembered
```

```yaml
location:
  latitude: 43.6532      # no lookup; these win over name
  longitude: -79.3832
  label: HOME            # text on the weather screens (default: the place's name)
```

- A `name` can be a city or town. Narrow it down with a region or country after a comma: `Portland, OR`, `Paris, France`, `London, Ontario`.
- US ZIP codes work, but Canadian postal codes don't; use the city name, or latitude and longitude, instead.
- The first match is used, and it's remembered in `clockscreen-state.json`, so restarts don't look it up again. A different `name` is looked up afresh.
- With latitude and longitude, a `name` (if given) is only the label.

Set `timezone` too if the board isn't in Toronto's. It's used for the clock and for where the forecast's days begin.

| Key | Default | |
|---|---|---|
| `timezone` | `America/Toronto` | any IANA zone name |
| `server.host`, `server.port` | `127.0.0.1`, `9300` | `0.0.0.0` lets other devices open the preview page |
| `units` | `metric` | `metric` (°C, km/h) or `imperial` (°F, mph) |
| `clock.format` | `12h` | `12h` (AM/PM is always shown) or `24h` |
| `clock.seconds` | `false` | `true` shows the seconds next to the time |
| `weather.refresh_minutes` | `15` | how often to fetch the forecast (at least 5) |
| `weather.hour_step` | `2` | hours between the columns of the hourly screen (1–6) |
| `cycle` | clock 20 s, current 10 s, hourly 8 s, daily 8 s | the screens in order, each `{screen, dwell}`; a screen may appear more than once |

For example, to show the clock between every weather screen:

```yaml
cycle:
  - {screen: clock, dwell: 15}
  - {screen: current, dwell: 8}
  - {screen: clock, dwell: 15}
  - {screen: hourly, dwell: 8}
  - {screen: clock, dwell: 15}
  - {screen: daily, dwell: 8}
```

clockscreen reads its config only at startup, so restart it after a change (the dashboard's **Save & restart**).

## API

| Endpoint | |
|---|---|
| `GET /health` | always 200 while running: the matched place, forecast age, last error, the screen on now |
| `GET /render/frame` | the panel's frame now: raw RGB, 128 × 64 × 3 bytes, with `X-Width` / `X-Height` headers (what HController fetches) |
| `GET /render/frame.png?pitch=6` | the same frame drawn as LED dots |
| `GET /screen` | which screen is on, why (`cycle` or `show`), for how much longer, and the data it shows |
| `GET /weather` | the whole forecast (`null` until the first fetch) |
| `POST /control/show` | `{"screen": "hourly"}` holds that screen for 30 s; `{"screen": null}` goes back to the cycle |
| `GET /` | the preview page |

The cycle is worked out from the clock (seconds since 1970, modulo the total dwell), so every request agrees on the screen. A **Show now** on clockscreen's own page also applies to the panel while HController has clockscreen on it.

## Testing

```bash
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest -q                                    # offline, recorded Open-Meteo responses, ~1 s
.venv/bin/python tools/render_previews.py --out previews/   # every screen and worst case as PNGs
```

`render_previews.py` uses the recorded Toronto forecast plus made-up extremes: −25°, 104 °F, `12:59:59 PM`, `23:59:59`, long place names and condition text, and every icon by day and by night.

## Layout

```
src/clockscreen/
  config.py            config.yaml models + validation
  state.py             clockscreen-state.json (the remembered geocoding result)
  weather/client.py    Open-Meteo geocoding + forecast (httpx)
  weather/parsers.py   the only code that reads Open-Meteo's JSON
  weather/codes.py     WMO weather codes -> condition text and icon
  poller.py            keeps the forecast fresh; retries with backoff
  rotation.py          which screen is on (pure function of the time)
  runtime.py           wires it together; Show now
  render/              fonts (from nhlscreen, plus big clock digits), icons, layouts
  api/app.py           the endpoints; api/preview.html
tools/render_previews.py
```

## Weather data

Weather data by [Open-Meteo.com](https://open-meteo.com/), under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). The free API is for non-commercial use and allows 10,000 calls a day; clockscreen makes about 100.
