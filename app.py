"""Flask web app: look up an airport's METAR and show it in plain English."""

import re
from datetime import datetime, timezone

import requests
from flask import Flask, render_template, request

from metar_decoder import MetarDecodeError, decode

METAR_API_URL = "https://aviationweather.gov/api/data/metar"
REQUEST_TIMEOUT = 10  # seconds

app = Flask(__name__)


class MetarLookupError(Exception):
    """A user-facing problem fetching a METAR."""


def normalize_code(code: str) -> str:
    code = code.strip().upper()
    if not re.fullmatch(r"[A-Z0-9]{3,4}", code):
        raise MetarLookupError("Please enter a 3 or 4 character airport code, like KJFK or LAX.")
    # US airports are often known by their 3-letter code (LAX); METAR uses the ICAO form (KLAX).
    if len(code) == 3 and code.isalpha():
        code = "K" + code
    return code


def fetch_metar(code: str) -> dict:
    """Return the latest METAR record for an ICAO station from aviationweather.gov."""
    try:
        response = requests.get(
            METAR_API_URL,
            params={"ids": code, "format": "json"},
            headers={"User-Agent": "METAR-Reader/1.0"},
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException:
        raise MetarLookupError("Couldn't reach the aviation weather service. Please try again in a moment.")

    if response.status_code == 204 or not response.content:
        raise MetarLookupError(f"No weather report found for {code}. Check the airport code and try again.")
    if response.status_code != 200:
        raise MetarLookupError(f"The aviation weather service returned an error ({response.status_code}).")

    try:
        records = response.json()
    except ValueError:
        raise MetarLookupError("The aviation weather service sent back an unexpected response.")
    if not records:
        raise MetarLookupError(f"No weather report found for {code}. Check the airport code and try again.")
    return records[0]


def describe_age(observed_at: datetime | None) -> str | None:
    if observed_at is None:
        return None
    minutes = int((datetime.now(timezone.utc) - observed_at).total_seconds() // 60)
    if minutes < 1:
        return "just now"
    if minutes < 60:
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    hours = minutes // 60
    return f"{hours} hour{'s' if hours != 1 else ''} ago"


@app.route("/")
def index():
    code = request.args.get("code", "").strip()
    context = {"code": code.upper(), "report": None, "error": None}

    if code:
        try:
            station = normalize_code(code)
            record = fetch_metar(station)
            report = decode(record["rawOb"])
            context.update(
                report=report,
                station_name=record.get("name") or report.station,
                age=describe_age(report.observed_at),
            )
        except MetarLookupError as exc:
            context["error"] = str(exc)
        except (MetarDecodeError, KeyError):
            context["error"] = "Sorry, we couldn't understand the weather report for that airport."

    return render_template("index.html", **context)


if __name__ == "__main__":
    app.run(debug=True)
