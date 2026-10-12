"""METAR Reader web application.

A small Flask app that looks up the latest METAR (aviation routine weather
report) for an airport and presents it in plain English.

The raw report is fetched from the aviationweather.gov Data API and decoded
by :mod:`metar_decoder`. This module only handles input validation, the HTTP
request to the weather service, and rendering the page.

Run locally with::

    python app.py

then open http://127.0.0.1:5000 in a browser.
"""

import os
import re
from datetime import datetime, timezone

import requests
from flask import Flask, render_template, request

from metar_decoder import MetarDecodeError, decode

#: Endpoint of the aviationweather.gov METAR API.
METAR_API_URL = "https://aviationweather.gov/api/data/metar"

#: Seconds to wait for the weather service before giving up.
REQUEST_TIMEOUT = 10

app = Flask(__name__)


class MetarLookupError(Exception):
    """A problem fetching a METAR whose message is safe to show to users."""


def normalize_code(code: str) -> str:
    """Validate an airport code and convert it to the ICAO form used by METARs.

    Args:
        code: The airport code as typed by the user, e.g. ``"khio"`` or ``"LAX"``.

    Returns:
        The upper-cased ICAO station identifier, e.g. ``"KHIO"`` or ``"KLAX"``.

    Raises:
        MetarLookupError: If the code isn't 3 or 4 letters/digits.
    """
    code = code.strip().upper()
    if not re.fullmatch(r"[A-Z0-9]{3,4}", code):
        raise MetarLookupError("Please enter a 3 or 4 character airport code, like KJFK or LAX.")

    # People usually know US airports by their 3-letter FAA/IATA code (LAX),
    # but the weather service only accepts the 4-letter ICAO form (KLAX).
    if len(code) == 3 and code.isalpha():
        code = "K" + code
    return code


def fetch_metar(code: str) -> dict:
    """Fetch the latest METAR record for a station from aviationweather.gov.

    Args:
        code: A 4-character ICAO station identifier, e.g. ``"KHIO"``.

    Returns:
        The station's record from the API's JSON response. The fields used by
        this app are ``rawOb`` (the raw METAR text) and ``name`` (the
        airport's full name).

    Raises:
        MetarLookupError: If the service can't be reached, returns an error,
            or has no report for the station.
    """
    try:
        response = requests.get(
            METAR_API_URL,
            params={"ids": code, "format": "json"},
            # Identify the app to the service, as its usage guidelines ask.
            headers={"User-Agent": "METAR-Reader/1.0"},
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise MetarLookupError(
            "Couldn't reach the aviation weather service. Please try again in a moment."
        ) from exc

    # The API answers unknown stations with "204 No Content" rather than a 404.
    if response.status_code == 204:
        raise MetarLookupError(f"No weather report found for {code}. Check the airport code and try again.")
    # Check for errors before looking at the body, so an outage isn't
    # mistaken for an unknown airport.
    if response.status_code != 200:
        raise MetarLookupError(f"The aviation weather service returned an error ({response.status_code}).")
    if not response.content:
        raise MetarLookupError(f"No weather report found for {code}. Check the airport code and try again.")

    try:
        records = response.json()
    except ValueError as exc:
        raise MetarLookupError("The aviation weather service sent back an unexpected response.") from exc
    if not records:
        raise MetarLookupError(f"No weather report found for {code}. Check the airport code and try again.")

    # We request a single station, so the first record is the one we want.
    return records[0]


def describe_age(observed_at: datetime | None) -> str | None:
    """Describe how long ago a report was observed, e.g. ``"12 minutes ago"``.

    Args:
        observed_at: The observation time in UTC, or ``None`` if unknown.

    Returns:
        A short human-readable age, or ``None`` if ``observed_at`` is ``None``.
    """
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
    """Render the search page and, if a code was submitted, its weather report.

    The airport code arrives as the ``code`` query parameter (``/?code=KHIO``),
    so every report has a shareable, bookmarkable URL.
    """
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
            # The service responded, but not with a METAR we could read.
            context["error"] = "Sorry, we couldn't understand the weather report for that airport."

    return render_template("index.html", **context)


if __name__ == "__main__":
    # Flask's built-in server is for local development only. Debug mode is
    # off unless FLASK_DEBUG=1 is set, because the debugger lets anyone who
    # can reach the page run code on the machine.
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
