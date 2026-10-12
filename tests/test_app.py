"""Tests for app.py.

The aviationweather.gov API is never called: ``requests.get`` is patched to
return a canned response containing a mock METAR, so these tests are fast,
work offline, and don't depend on today's weather.
"""

import html
import json
import re
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
import requests

import app as app_module
from app import MetarLookupError, describe_age, fetch_metar, normalize_code


# ---- helpers and fixtures ----------------------------------------------------

def make_response(status_code=200, body=None):
    """Build a real requests.Response, as the weather service would return it.

    Args:
        status_code: HTTP status code of the fake response.
        body: Object to serialize as the JSON body, or a raw ``str``/``bytes``
            body. ``None`` means an empty body.
    """
    response = requests.Response()
    response.status_code = status_code
    if body is None:
        response._content = b""
    elif isinstance(body, (str, bytes)):
        response._content = body.encode() if isinstance(body, str) else body
    else:
        response._content = json.dumps(body).encode()
    return response


def metar_record(raw, name="Test Airport, XX, US"):
    """A one-station API payload containing the given raw METAR."""
    return [{"icaoId": raw.split()[1], "name": name, "rawOb": raw}]


@pytest.fixture
def client():
    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as client:
        yield client


@pytest.fixture
def mock_get():
    """Replace requests.get inside app.py; tests set its return_value/side_effect."""
    with patch("app.requests.get") as mocked:
        yield mocked


def get_page(client, code):
    """Request the page for an airport code and return its unescaped HTML."""
    response = client.get("/", query_string={"code": code})
    assert response.status_code == 200
    return html.unescape(response.get_data(as_text=True))


# ---- normalize_code ----------------------------------------------------------

@pytest.mark.parametrize("typed, expected", [
    ("KHIO", "KHIO"),
    ("khio", "KHIO"),
    ("  egll ", "EGLL"),
    ("LAX", "KLAX"),   # US 3-letter code gets the K prefix
    ("lax", "KLAX"),
    ("1S2", "1S2"),    # 3-character codes containing digits are left alone
])
def test_normalize_code_accepts_valid_codes(typed, expected):
    assert normalize_code(typed) == expected


@pytest.mark.parametrize("typed", ["", "K", "KJ", "KJFKX", "KJ!K", "K JF"])
def test_normalize_code_rejects_invalid_codes(typed):
    with pytest.raises(MetarLookupError, match="3 or 4 character airport code"):
        normalize_code(typed)


# ---- describe_age ------------------------------------------------------------

@pytest.mark.parametrize("minutes_ago, expected", [
    (0, "just now"),
    (1, "1 minute ago"),
    (45, "45 minutes ago"),
    (60, "1 hour ago"),
    (150, "2 hours ago"),
])
def test_describe_age(minutes_ago, expected):
    observed = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago, seconds=5)
    assert describe_age(observed) == expected


def test_describe_age_unknown_time():
    assert describe_age(None) is None


# ---- fetch_metar -------------------------------------------------------------

def test_fetch_metar_returns_first_record_and_sends_expected_request(mock_get):
    record = metar_record("METAR KHIO 111853Z VRB03KT 10SM CLR 13/06 A2991")
    mock_get.return_value = make_response(200, record)

    assert fetch_metar("KHIO") == record[0]

    url = mock_get.call_args.args[0]
    kwargs = mock_get.call_args.kwargs
    assert url == "https://aviationweather.gov/api/data/metar"
    assert kwargs["params"] == {"ids": "KHIO", "format": "json"}
    assert kwargs["timeout"] == app_module.REQUEST_TIMEOUT


@pytest.mark.parametrize("response, message", [
    (make_response(204), "No weather report found for KZZZ"),
    (make_response(200, []), "No weather report found for KZZZ"),
    (make_response(200), "No weather report found for KZZZ"),   # 200 with empty body
    (make_response(503), "returned an error (503)"),           # outage, empty body
    (make_response(500, "Server error"), "returned an error (500)"),
    (make_response(200, "<html>not json</html>"), "unexpected response"),
])
def test_fetch_metar_bad_responses(mock_get, response, message):
    mock_get.return_value = response
    with pytest.raises(MetarLookupError, match=re.escape(message)):
        fetch_metar("KZZZ")


@pytest.mark.parametrize("error", [requests.ConnectionError, requests.Timeout])
def test_fetch_metar_network_failure(mock_get, error):
    mock_get.side_effect = error("boom")
    with pytest.raises(MetarLookupError, match="Couldn't reach"):
        fetch_metar("KHIO")


# ---- the page: mock METARs in, plain English out ----------------------------

# Each case: (raw METAR, expected summary, other text expected on the page)
WEATHER_CASES = {
    "clear day": (
        "METAR KHIO 111853Z VRB03KT 10SM CLR 13/06 A2991 RMK AO2 SLP128 T01280061",
        "Clear skies, 55°F (13°C). Light and variable winds around 3 mph.",
        ["64%", "10+ miles (excellent)", "29.91 inHg"],
    ),
    "thunderstorm with gusts": (
        "METAR KMCO 111753Z 27025G40KT 1SM +TSRA BKN015CB OVC030 24/22 A2985",
        "Heavy thunderstorm with rain, overcast, 75°F (24°C). "
        "Strong wind from the west at 29 mph, gusting to 46 mph. "
        "Visibility is reduced to 1 mile.",
        ["Broken clouds at 1,500 ft (thunderstorm clouds); overcast at 3,000 ft", "1 mile (poor)"],
    ),
    "snow with wind chill": (
        "METAR KMSP 111853Z 32018KT 1/2SM -SN FZFG OVC008 M12/M14 A3012",
        "Light snow, freezing fog, overcast, 10°F (-12°C), feels like -9°F. "
        "Strong wind from the northwest at 21 mph. "
        "Visibility is reduced to 1/2 mile.",
        ["Overcast at 800 ft", "1/2 mile (very poor)"],
    ),
    "hot and humid": (
        "METAR KMIA 111853Z 09012KT 10SM SCT030 33/26 A3002",
        "Partly cloudy, 91°F (33°C), feels like 108°F. Moderate wind from the east at 14 mph.",
        ["67%", "Scattered clouds at 3,000 ft"],
    ),
    "dense fog, calm": (
        "METAR KSFO 111356Z 00000KT M1/4SM FG VV001 12/12 A3001",
        "Fog, sky obscured, 54°F (12°C). Calm winds. Visibility is reduced to 1/4 mile.",
        ["100%", "Less than 1/4 mile (very poor)", "Sky obscured, vertical visibility 100 ft"],
    ),
    "international CAVOK": (
        "METAR LFPG 111930Z 05010KT CAVOK 18/10 Q1020",
        "Clear skies, 64°F (18°C). Moderate wind from the northeast at 12 mph.",
        ["10+ km (unlimited)", "No significant clouds", "30.12 inHg"],
    ),
}


@pytest.mark.parametrize("raw, summary, details", WEATHER_CASES.values(), ids=WEATHER_CASES.keys())
def test_mock_metar_is_shown_in_plain_english(client, mock_get, raw, summary, details):
    station = raw.split()[1]
    mock_get.return_value = make_response(200, metar_record(raw, name="Mock Field, ZZ, US"))

    page = get_page(client, station)

    assert summary in page
    for text in details:
        assert text in page
    assert "Mock Field, ZZ, US" in page
    assert raw in page  # raw METAR is available in the collapsible section


def test_page_shows_observation_time_and_age(client, mock_get):
    observed = datetime.now(timezone.utc) - timedelta(minutes=20)
    raw = f"METAR KHIO {observed:%d%H%M}Z 00000KT 10SM CLR 20/10 A3000"
    mock_get.return_value = make_response(200, metar_record(raw))

    page = get_page(client, "KHIO")

    assert f"Observed {observed:%H:%M} UTC" in page
    assert "20 minutes ago" in page


def test_three_letter_code_is_looked_up_as_icao(client, mock_get):
    mock_get.return_value = make_response(200, metar_record("METAR KLAX 111853Z 25010KT 10SM CLR 22/12 A2992"))

    get_page(client, "lax")

    assert mock_get.call_args.kwargs["params"]["ids"] == "KLAX"


def test_station_code_shown_when_api_has_no_name(client, mock_get):
    record = [{"rawOb": "METAR KXYZ 111853Z 00000KT 10SM CLR 20/10 A3000"}]
    mock_get.return_value = make_response(200, record)

    page = get_page(client, "KXYZ")

    assert "<h2>KXYZ" in page


# ---- the page: errors --------------------------------------------------------

def test_empty_search_shows_form_without_calling_api(client, mock_get):
    page = get_page(client, "")

    mock_get.assert_not_called()
    assert 'role="alert"' not in page
    assert 'class="summary"' not in page


def test_invalid_code_shows_error_without_calling_api(client, mock_get):
    page = get_page(client, "ab!")

    mock_get.assert_not_called()
    assert "Please enter a 3 or 4 character airport code" in page


@pytest.mark.parametrize("setup, message", [
    (lambda m: setattr(m, "return_value", make_response(204)), "No weather report found for KZZZ"),
    (lambda m: setattr(m, "return_value", make_response(503)), "returned an error (503)"),
    (lambda m: setattr(m, "side_effect", requests.ConnectionError()), "Couldn't reach the aviation weather service"),
    (lambda m: setattr(m, "return_value", make_response(200, [{"name": "No METAR"}])),
     "couldn't understand the weather report"),
    (lambda m: setattr(m, "return_value", make_response(200, [{"rawOb": ""}])),
     "couldn't understand the weather report"),
], ids=["unknown airport", "server error", "network down", "missing rawOb", "empty METAR"])
def test_lookup_problems_show_friendly_error(client, mock_get, setup, message):
    setup(mock_get)

    page = get_page(client, "KZZZ")

    assert message in page
    assert 'class="summary"' not in page
