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

## Running the tests

```bash
pytest
```

The tests cover the decoder using real METARs from US and international airports, plus edge cases such as calm winds, thunderstorms, below-freezing temperatures, and missing data.

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
