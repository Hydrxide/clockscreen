# clockscreen

> This project is not actively maintained, and was created with AI assistance for personal use.

A clock and local weather for a 128 × 64 LED panel. It cycles between the time and three weather screens, and runs as a module of [HController](https://github.com/Hydrxide/HController), the hub that owns the panel and decides which app is on it.

| Screen | Shows |
|---|---|
| **Clock** | The time in large digits (12-hour with AM/PM, or 24-hour; seconds optional) and the date |
| **Current conditions** | Weather icon, temperature, feels-like, condition (`PARTLY CLOUDY`), today's high/low, wind, the place's name and the time |
| **Next hours** | Four columns, 2 hours apart by default: time, icon, temperature, chance of precipitation (from 10%) |
| **Next days** | The next three days: day, icon, high, low, chance of precipitation |

Weather comes from [Open-Meteo](https://open-meteo.com/): free, no API key or sign-up, and it covers the whole world. Until the first forecast arrives, or if the forecast is more than 3 hours old, the panel shows only the clock.

This README is a setup guide for a Raspberry Pi, a Mac, a Linux PC or a Windows PC. A browser preview shows exactly what the panel shows, so you can try it without any LED hardware.

**Contents:** [What you need](#what-you-need) · [1. Install](#1-install) · [2. Try it on its own](#2-try-it-on-its-own) · [Running it on HController](#running-it-on-hcontroller) · [Configuration](#configuration) · [Settings on the preview page](#settings-on-the-preview-page) · [Troubleshooting](#troubleshooting) · [For developers](#for-developers) · [License](#license)

## What you need

- **Python 3.11 or newer** and **git**.
- An internet connection for the forecast.

| | Install Python and git | Check |
|---|---|---|
| **Raspberry Pi OS, Debian, Ubuntu** | `sudo apt update && sudo apt install -y git python3 python3-venv` | `python3 --version` |
| **macOS** | `xcode-select --install` for git. Python from [python.org](https://www.python.org/downloads/macos/) or `brew install python@3.13` | `python3 --version` |
| **Windows** | `winget install Git.Git` and `winget install Python.Python.3.13` in PowerShell, or the installers from [git-scm.com](https://git-scm.com/download/win) and [python.org](https://www.python.org/downloads/windows/). Then open a new PowerShell window. | `py --version` |

If `python3 --version` shows something older than 3.11, call the newer Python by its full name below, for example `python3.13 -m venv .venv`. The `python3` that comes with macOS is 3.9, and Ubuntu 22.04's is 3.10; both are too old.

## 1. Install

Install it in your home folder, so it ends up at `~/clockscreen`. If you use HController, install it on the machine that runs HController, beside `~/HController`.

**macOS, Linux and the Pi:**

```bash
cd ~
git clone https://github.com/Hydrxide/clockscreen.git
cd clockscreen
python3 -m venv .venv
.venv/bin/pip install -e .
```

**Windows (PowerShell):**

```powershell
cd ~
git clone https://github.com/Hydrxide/clockscreen.git
cd clockscreen
py -m venv .venv
.venv\Scripts\pip install -e .
```

Use PowerShell rather than the old Command Prompt for the Windows commands in this guide. There's no need to "activate" the venv: the commands call its Python directly.

There's no need to create `config.yaml`. Until it exists, clockscreen runs on its defaults (Toronto, °C, 12-hour clock), and HController's config editor starts from `config.example.yaml`. The location, timezone, units and time format can all be set from the preview page.

## 2. Try it on its own

**macOS, Linux and the Pi:**

```bash
cd ~/clockscreen
.venv/bin/python -m clockscreen
```

**Windows:**

```powershell
cd ~\clockscreen
.venv\Scripts\python.exe -m clockscreen
```

Then open **http://127.0.0.1:9300/** in a browser on the same machine. It keeps running until you press **Ctrl+C**.

On a Pi without a screen, start it with `--host 0.0.0.0` and open **http://raspberrypi.local:9300/** from another device instead.

The preview page draws exactly what the panel shows, as LED dots. It also has **Show now** buttons, the forecast's status, and **Settings** for the time format, timezone, units and location (see [Settings on the preview page](#settings-on-the-preview-page)). Set your location there now: within a few seconds the page shows the place it matched, and the weather screens switch to its forecast.

To use it as a module, stop it again (Ctrl+C) and let HController run it. HController won't start a second copy while this one holds the port.

## Running it on HController

These steps set it up from scratch on the machine that runs HController (a Raspberry Pi, or a Mac or PC for testing). They assume HController is already installed and working; see its README.

**1. Install clockscreen next to HController,** as in [1. Install](#1-install), so it's at `~/clockscreen`.

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

The same block works on Windows: HController finds the venv's `.venv\Scripts\python.exe` there.

clockscreen doesn't log each frame request, so it needs no `log_ignore`. If you cloned somewhere other than `~/clockscreen`, change `cwd` (on Windows, `~` is `C:\Users\<you>`).

**3. Restart HController,** which reads `hcontroller.yaml` only at startup:
- **Pi / Linux with its service:** `sudo systemctl restart hcontroller`.
- **Started in a terminal:** press Ctrl+C there, then start it again (`.venv/bin/python -m hcontroller`, or `.venv\Scripts\python.exe -m hcontroller` on Windows).

Then on the dashboard (`http://<that machine>:1630/`), the **Clock & Weather** card should go from **starting** to **healthy** within a few seconds.

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

**5. Set it up.** There are two ways:
- **The time format, timezone, units and location:** use the card's **Open** link, then **Settings** on clockscreen's page. Changes apply straight away, with no restart (see [Settings on the preview page](#settings-on-the-preview-page)).
- **Everything:** use the card's **Config file** editor, which also covers the cycle, refresh rate and port (see [Configuration](#configuration)), then **Save & restart**.

Either way, within a few seconds the place the name was matched to appears, both on clockscreen's page and in the card's **Logs**, for example `Location 'Toronto' is Toronto, Ontario, Canada (43.7064, -79.3986)`, followed by the first forecast.

clockscreen has no systemd service of its own, and doesn't need one: HController starts it, including at boot when HController runs as a service.

## Configuration

Copy `config.example.yaml` to `config.yaml` (`cp` on macOS and Linux, `copy` on Windows), or edit it from HController's dashboard. Every key is optional.

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

### Settings on the preview page

The **Settings** section of clockscreen's own page (`http://<machine>:9300/`, or the **Open** link on HController's card) changes four things without a restart:

- **Time:** 12-hour (AM/PM) or 24-hour, and whether to show seconds.
- **Timezone:** the clock's timezone, as an IANA name such as `America/Vancouver` or `Europe/Paris`. The field suggests names as you type, and a button offers the timezone of the device you're viewing the page on. Changing it also fetches the forecast again, because the forecast's days begin and end in this timezone.
- **Units:** °C and km/h, or °F and mph. The forecast is fetched again in the new units straight away.
- **Location:** a place name (narrowed with a region or country after a comma, as above), or `latitude, longitude`, with an optional label for the screens. It's looked up first and only saved if it matches a place; the page then shows what it matched.

These choices are saved in `clockscreen-state.json` next to the config. They **win over `config.yaml`**, through restarts, until you press **Reset to config** beside each one. So if a change in `config.yaml` doesn't seem to take effect, check for a **Reset to config** button on the page.

**The timezone and the location are separate.** The clock, the time on the current-conditions screen and the hours on the hourly screen all use the timezone, whatever the weather location is. So a board in Toronto can show Paris weather with Toronto time, and the hourly screen's `1PM` means 1 PM in Toronto. Set both if you've moved the board.

## Troubleshooting

| What you see | What to do |
|---|---|
| `ERROR: Package 'clockscreen' requires a different Python` | The venv was made with Python older than 3.11. Delete the `.venv` folder and make it again with a newer Python (see [What you need](#what-you-need)). |
| `error while attempting to bind on address ('127.0.0.1', 9300)` | Another copy holds port 9300, in another terminal or under HController. Stop one of them. |
| **conflict** on HController's card | Something else holds port 9300, probably a copy you started by hand. Stop it, and HController starts its own within 5 s. |
| `.../.venv/bin/python doesn't exist` on the card | clockscreen's venv is missing. Make it with [1. Install](#1-install). |
| Only the clock shows | The forecast hasn't arrived yet, or is over 3 hours old. The terminal or the card's **Logs** show why (no network, a place name with no match), and clockscreen keeps retrying. |
| A change in `config.yaml` didn't take effect | Restart clockscreen, and check the preview page for a **Reset to config** button: settings made there win over the file. |
| The preview page or **Open** link doesn't load from a phone | Set `server: {host: 0.0.0.0}` in clockscreen's config and restart it. The first time, Windows asks whether to allow Python through the firewall: allow it on **private** networks. |
| Changing the port | Set it in both places: `server.port` in clockscreen's config, and the port in the module's `url`. Then restart HController. |

## For developers

### Testing

```bash
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest -q                                    # offline, recorded Open-Meteo responses, ~1 s
.venv/bin/python tools/render_previews.py --out previews/   # every screen and worst case as PNGs
```

On Windows, use `.venv\Scripts\` in place of `.venv/bin/`.

`render_previews.py` uses the recorded Toronto forecast plus made-up extremes: −25°, 104 °F, `12:59:59 PM`, `23:59:59`, long place names and condition text, and every icon by day and by night.

### API

| Endpoint | |
|---|---|
| `GET /health` | always 200 while running: the matched place, forecast age, last error, the screen on now |
| `GET /render/frame` | the panel's frame now: raw RGB, 128 × 64 × 3 bytes, with `X-Width` / `X-Height` headers (what HController fetches) |
| `GET /render/frame.png?pitch=6` | the same frame drawn as LED dots |
| `GET /screen` | which screen is on, why (`cycle` or `show`), for how much longer, and the data it shows |
| `GET /weather` | the whole forecast (`null` until the first fetch) |
| `POST /control/show` | `{"screen": "hourly"}` holds that screen for 30 s; `{"screen": null}` goes back to the cycle |
| `GET /control/settings` | the time format, timezone, units and location in use, the matched place, and which are saved over `config.yaml` |
| `PUT /control/clock` | `{"clock": {"format": "24h", "seconds": true}}`; `{"clock": null}` goes back to `config.yaml` |
| `PUT /control/timezone` | `{"timezone": "America/Vancouver"}` (any case), then the forecast is fetched again; 400 for an unknown name; `null` goes back to `config.yaml` |
| `PUT /control/units` | `{"units": "imperial"}` (or `metric`), then the forecast is fetched again; `null` goes back to `config.yaml` |
| `PUT /control/location` | `{"location": "Paris, France", "label": null}` or `{"location": "49.28, -123.12"}`; 400 if nothing matches, 502 if the lookup fails; `null` goes back to `config.yaml` |
| `GET /` | the preview page |

The cycle is worked out from the clock (seconds since 1970, modulo the total dwell), so every request agrees on the screen. A **Show now** on clockscreen's own page also applies to the panel while HController has clockscreen on it.

### Layout

```
src/clockscreen/
  config.py            config.yaml models + validation
  state.py             clockscreen-state.json (geocoding result, preview-page settings)
  weather/client.py    Open-Meteo geocoding + forecast (httpx)
  weather/parsers.py   the only code that reads Open-Meteo's JSON
  weather/codes.py     WMO weather codes -> condition text and icon
  poller.py            keeps the forecast fresh; retries with backoff
  rotation.py          which screen is on (pure function of the time)
  runtime.py           wires it together; preview-page settings, Show now
  render/              fonts (from nhlscreen, plus big clock digits), icons, layouts
  api/app.py           the endpoints; api/preview.html
tools/render_previews.py
```

## Weather data

Weather data by [Open-Meteo.com](https://open-meteo.com/), under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). The free API is for non-commercial use and allows 10,000 calls a day; clockscreen makes about 100.

## License

MIT; see [LICENSE](LICENSE). The weather data is Open-Meteo's, under its own license (above).
