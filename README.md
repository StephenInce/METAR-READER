# METAR Reader

A small Flask app that turns cryptic airport weather reports (METARs) into plain English.

Type an airport code (`KHIO`, `KJFK`, `EGLL`, or a US 3-letter code like `LAX`) and get something like:

> Clear skies, 55°F (13°C). Light and variable winds around 3 mph.

plus a breakdown of temperature, humidity, wind, visibility, clouds, and pressure.

Data comes from the [aviationweather.gov METAR API](https://aviationweather.gov/api/data/metar?ids=KHIO).

## Setup

Requires Python 3.10+.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Run

```powershell
python app.py
```

Then open http://127.0.0.1:5000.

## Test

```powershell
pytest
```

## Project layout

- `app.py` – Flask routes and the aviationweather.gov API call
- `metar_decoder.py` – parses a raw METAR string and builds the plain-English summary
- `templates/index.html`, `static/style.css` – the web page
- `tests/` – decoder tests

Not for flight planning.
