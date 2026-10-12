# METAR Reader

**Airport weather reports, in plain English.**

METAR Reader is a small Flask web app that takes the cryptic weather reports pilots use and turns them into something anyone can read. Type an airport code and get the current conditions as a friendly summary.

A raw METAR like this:

```
METAR KHIO 111853Z VRB03KT 10SM CLR 13/06 A2991 RMK AO2 SLP128 T01280061
```

becomes:

> **Clear skies, 55°F (13°C). Light and variable winds around 3 mph.**

## What is a METAR?

A METAR (Meteorological Aerodrome Report) is a standard weather observation published by airports around the world, usually every hour. METARs are packed with useful information, but they're written in a compact code meant for pilots and forecasters. This app decodes them for everyone else.

## Features

- **Plain-English summary**: sky conditions, temperature, wind, and any rain, snow, fog, or storms, in one or two sentences.
- **Detailed breakdown**: temperature, dew point, humidity, wind, visibility, cloud layers, and pressure.
- **Feels-like temperature**: shows wind chill or heat index when it differs noticeably from the actual temperature.
- **Airports worldwide**: works with any 4-letter ICAO code (`KJFK`, `EGLL`, `RJTT`). US 3-letter codes such as `LAX` are converted to their ICAO form (`KLAX`) automatically.
- **US and international formats**: reads visibility in miles or meters and pressure in inches of mercury or hectopascals.
- **Shareable links**: every report has its own URL, such as `/?code=KDEN`.
- **The original report**: the raw METAR is available in a collapsible section on the page.

### Examples

| Airport | Summary |
|---|---|
| `KDEN` Denver | Partly cloudy, 81°F (27°C). Moderate wind from the south-southwest at 16 mph, gusting to 28 mph. |
| `PANC` Anchorage | Light rain, mist, overcast, 42°F (6°C), feels like 37°F. Moderate wind from the south-southeast at 9 mph. |
| `EGLL` London Heathrow | Overcast, 57°F (14°C). Moderate wind from the south-southeast at 8 mph. |

## Installation

### Requirements

- [Python](https://www.python.org/downloads/) 3.10 or newer
- [Git](https://git-scm.com/downloads)
- An internet connection (reports are fetched live)

### 1. Clone the repository

```bash
git clone https://github.com/StephenInce/METAR-READER.git
cd METAR-READER
```

### 2. Create a virtual environment and install dependencies

**Windows (PowerShell)**

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

If PowerShell blocks the activation script, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once and try again.

**macOS / Linux / Git Bash**

```bash
python3 -m venv .venv
source .venv/bin/activate        # Git Bash on Windows: source .venv/Scripts/activate
pip install -r requirements.txt
```

### 3. Run the app

```bash
python app.py
```

Open **http://127.0.0.1:5000** in your browser, enter an airport code, and press **Get weather**. Press `Ctrl+C` in the terminal to stop the server.

To turn on Flask's debug mode (automatic reloading and in-browser error pages) while developing, set `FLASK_DEBUG=1` first:

```bash
FLASK_DEBUG=1 python app.py               # macOS / Linux / Git Bash
$env:FLASK_DEBUG = "1"; python app.py     # PowerShell
```

> **Never enable debug mode on a public server.** The debugger lets anyone who can reach the page run code on your machine.

## Testing

The project has a [pytest](https://docs.pytest.org/) suite covering both the METAR decoder and the web app. pytest is installed with the other dependencies in `requirements.txt`.

### Running the tests

With the virtual environment activated, from the project folder:

```bash
pytest
```

You should see something like `52 passed in 0.71s`. If a test fails, pytest prints the expected and actual values.

To run the tests without activating the virtual environment:

```bash
.venv\Scripts\python.exe -m pytest      # Windows PowerShell
.venv/Scripts/python.exe -m pytest      # Git Bash
.venv/bin/python -m pytest              # macOS / Linux
```

Useful options:

| Command | What it does |
|---|---|
| `pytest -v` | Lists each test by name with PASSED or FAILED |
| `pytest tests/test_app.py` | Runs only the web app tests |
| `pytest tests/test_metar_decoder.py` | Runs only the decoder tests |
| `pytest -k snow` | Runs only tests whose name contains "snow" |
| `pytest -x` | Stops at the first failure |
| `pytest --lf` | Re-runs only the tests that failed last time |

### What's tested

**`tests/test_metar_decoder.py`: the METAR decoder**

Decodes real METARs from US and international airports and checks each part: wind, gusts, visibility in miles and meters, weather, cloud layers, temperatures below freezing, pressure in inHg and hPa, and wind chill. It also covers edge cases such as calm winds, missing cloud heights, reports from the previous month, and empty input.

**`tests/test_app.py`: the web app**

These tests never contact aviationweather.gov. `requests.get` is replaced with a mock that returns a canned response containing a mock METAR, so the tests run offline, finish in under a second, and don't depend on the current weather. Everything else runs for real: code checking, the API request, decoding, and the rendered page.

- **Mock METARs → plain English**: six weather scenarios, each checked against the exact summary sentence and the details on the page:

  | Scenario | Expected summary |
  |---|---|
  | Clear day | Clear skies, 55°F (13°C). Light and variable winds around 3 mph. |
  | Thunderstorm | Heavy thunderstorm with rain, overcast, 75°F (24°C). Strong wind from the west at 29 mph, gusting to 46 mph. Visibility is reduced to 1 mile. |
  | Snow | Light snow, freezing fog, overcast, 10°F (-12°C), feels like -9°F. Strong wind from the northwest at 21 mph. Visibility is reduced to 1/2 mile. |
  | Hot and humid | Partly cloudy, 91°F (33°C), feels like 108°F. Moderate wind from the east at 14 mph. |
  | Dense fog | Fog, sky obscured, 54°F (12°C). Calm winds. Visibility is reduced to 1/4 mile. |
  | CAVOK (international) | Clear skies, 64°F (18°C). Moderate wind from the northeast at 12 mph. |

- **Airport codes**: lowercase and padded input is accepted, US 3-letter codes become ICAO codes (`LAX` → `KLAX`), and invalid codes are rejected without calling the API.
- **Weather service responses**: the correct URL and parameters are sent, and unknown airports, empty replies, server errors, bad data, timeouts, and network failures each produce a friendly error message.
- **Page details**: observation time and age ("20 minutes ago"), the airport name (or the station code when there's no name), and the raw METAR.

### Adding a weather scenario

To test how a new METAR is decoded, add an entry to `WEATHER_CASES` in `tests/test_app.py`: a name, the raw METAR, the summary you expect, and any other text that should appear on the page.

```python
"windy and clear": (
    "METAR KABC 111853Z 27030KT 10SM CLR 20/05 A3000",
    "Clear skies, 68°F (20°C). Very strong wind from the west at 35 mph.",
    ["10+ miles (excellent)"],
),
```

Work out the expected text by hand rather than copying the app's output, so the test checks the right answer instead of the current one.

## Deploying publicly

`python app.py` uses Flask's built-in development server, which isn't designed for public traffic. To host the app, run it with a production WSGI server instead:

```bash
# macOS / Linux
pip install gunicorn
gunicorn app:app --bind 0.0.0.0:8000

# Windows
pip install waitress
waitress-serve --listen=0.0.0.0:8000 app:app
```

The app needs no database, API key, or other configuration, so it also runs as-is on hosting platforms that support Python web apps (such as Render, Railway, Fly.io, or PythonAnywhere). Use `app:app` as the WSGI entry point.

## How it works

1. You enter an airport code. The app checks it and converts US 3-letter codes to ICAO form.
2. The app requests the latest report from the [aviationweather.gov Data API](https://aviationweather.gov/data/api/), e.g. `https://aviationweather.gov/api/data/metar?ids=KHIO`.
3. `metar_decoder.py` parses the raw METAR into structured data: wind, visibility, weather, clouds, temperature, and pressure.
4. The decoder builds the plain-English summary, and Flask renders it on the page.

## Project structure

```
METAR-READER/
├── app.py                  # Flask routes, input validation, and the API request
├── metar_decoder.py        # METAR parser and plain-English summary builder
├── templates/
│   └── index.html          # Search page and report layout
├── static/
│   └── style.css           # Page styles
├── tests/
│   ├── test_app.py         # Web app tests using mock METARs
│   └── test_metar_decoder.py
├── LICENSE
├── requirements.txt
└── pytest.ini
```

## Data source and disclaimer

Weather data is provided by the [Aviation Weather Center](https://aviationweather.gov/), part of the U.S. National Weather Service.

**This app is for general information only and is not for flight planning or navigation.** Pilots should use official sources for preflight weather briefings.

## License

Released under the [MIT License](LICENSE).
