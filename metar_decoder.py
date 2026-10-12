"""Decode raw METAR weather reports into structured data and plain English.

Example:
    >>> report = decode("METAR KHIO 111853Z VRB03KT 10SM CLR 13/06 A2991")
    >>> report.summary
    'Clear skies, 55°F (13°C), light and variable winds around 3 mph. ...'
"""

import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

KNOTS_TO_MPH = 1.15078

COMPASS_POINTS = [
    "north", "north-northeast", "northeast", "east-northeast",
    "east", "east-southeast", "southeast", "south-southeast",
    "south", "south-southwest", "southwest", "west-southwest",
    "west", "west-northwest", "northwest", "north-northwest",
]

SKY_COVER = {
    "SKC": "clear",
    "CLR": "clear",
    "NSC": "no significant clouds",
    "NCD": "no clouds detected",
    "FEW": "a few clouds",
    "SCT": "scattered clouds",
    "BKN": "broken clouds",
    "OVC": "overcast",
    "VV": "sky obscured",
}

# Overall sky condition, keyed by the most-covered layer.
SKY_HEADLINE = {
    "SKC": "Clear skies",
    "CLR": "Clear skies",
    "NSC": "Clear skies",
    "NCD": "Clear skies",
    "CAVOK": "Clear skies",
    "FEW": "Mostly clear",
    "SCT": "Partly cloudy",
    "BKN": "Mostly cloudy",
    "OVC": "Overcast",
    "VV": "Sky obscured",
}
SKY_RANK = ["SKC", "CLR", "NSC", "NCD", "CAVOK", "FEW", "SCT", "BKN", "OVC", "VV"]

CLOUD_TYPES = {"CB": "thunderstorm clouds", "TCU": "towering cumulus clouds"}

INTENSITY = {"-": "light", "+": "heavy", "VC": "nearby"}

DESCRIPTORS = {
    "MI": "shallow",
    "PR": "partial",
    "BC": "patchy",
    "DR": "drifting",
    "BL": "blowing",
    "SH": "showers",
    "TS": "thunderstorm",
    "FZ": "freezing",
}

PHENOMENA = {
    "DZ": "drizzle",
    "RA": "rain",
    "SN": "snow",
    "SG": "snow grains",
    "IC": "ice crystals",
    "PL": "ice pellets",
    "GR": "hail",
    "GS": "small hail",
    "UP": "unknown precipitation",
    "BR": "mist",
    "FG": "fog",
    "FU": "smoke",
    "VA": "volcanic ash",
    "DU": "dust",
    "SA": "sand",
    "HZ": "haze",
    "PY": "spray",
    "PO": "dust whirls",
    "SQ": "squalls",
    "FC": "funnel cloud",
    "SS": "sandstorm",
    "DS": "duststorm",
}

WIND_RE = re.compile(r"^(?P<dir>\d{3}|VRB)(?P<speed>\d{2,3})(?:G(?P<gust>\d{2,3}))?(?P<unit>KT|MPS|KMH)$")
WIND_VAR_RE = re.compile(r"^(?P<from>\d{3})V(?P<to>\d{3})$")
VIS_SM_RE = re.compile(r"^(?P<mod>[MP])?(?P<value>\d+|\d+/\d+)SM$")
VIS_METERS_RE = re.compile(r"^\d{4}$")
RVR_RE = re.compile(r"^R\d{2}[LCR]?/")
WEATHER_RE = re.compile(
    r"^(?P<intensity>[-+]|VC)?"
    r"(?P<descriptor>MI|PR|BC|DR|BL|SH|TS|FZ)?"
    r"(?P<phenomena>(?:DZ|RA|SN|SG|IC|PL|GR|GS|UP|BR|FG|FU|VA|DU|SA|HZ|PY|PO|SQ|FC|SS|DS)*)$"
)
SKY_RE = re.compile(r"^(?P<cover>FEW|SCT|BKN|OVC|VV)(?P<height>\d{3}|///)(?P<type>CB|TCU|///)?$")
TEMP_RE = re.compile(r"^(?P<temp>M?\d{2})/(?P<dew>M?\d{2})?$")
ALTIMETER_RE = re.compile(r"^(?P<unit>[AQ])(?P<value>\d{4})$")
PRECISE_TEMP_RE = re.compile(r"^T(?P<ts>[01])(?P<t>\d{3})(?:(?P<ds>[01])(?P<d>\d{3}))?$")


class MetarDecodeError(ValueError):
    """Raised when a METAR string can't be parsed."""


@dataclass
class SkyLayer:
    cover: str
    height_ft: int | None = None
    cloud_type: str | None = None

    def describe(self) -> str:
        text = SKY_COVER[self.cover]
        if self.cover == "VV":
            text = "sky obscured"
            if self.height_ft is not None:
                text += f", vertical visibility {self.height_ft:,} ft"
            return text
        if self.height_ft is not None:
            text += f" at {self.height_ft:,} ft"
        if self.cloud_type:
            text += f" ({CLOUD_TYPES[self.cloud_type]})"
        return text


@dataclass
class Metar:
    raw: str
    report_type: str = "METAR"
    station: str = ""
    observed_at: datetime | None = None
    automated: bool = False
    corrected: bool = False
    wind_direction: int | None = None  # degrees the wind is blowing FROM
    wind_variable: bool = False
    wind_variable_range: tuple[int, int] | None = None
    wind_speed_kt: int | None = None
    wind_gust_kt: int | None = None
    visibility_sm: float | None = None
    visibility_modifier: str | None = None  # "M" (less than) or "P" (more than)
    cavok: bool = False
    weather: list[str] = field(default_factory=list)
    sky: list[SkyLayer] = field(default_factory=list)
    temperature_c: float | None = None
    dewpoint_c: float | None = None
    altimeter_inhg: float | None = None
    remarks: str = ""

    # ---- derived values -------------------------------------------------

    @property
    def temperature_f(self) -> float | None:
        return c_to_f(self.temperature_c)

    @property
    def dewpoint_f(self) -> float | None:
        return c_to_f(self.dewpoint_c)

    @property
    def wind_speed_mph(self) -> int | None:
        return knots_to_mph(self.wind_speed_kt)

    @property
    def wind_gust_mph(self) -> int | None:
        return knots_to_mph(self.wind_gust_kt)

    @property
    def wind_compass(self) -> str | None:
        if self.wind_direction is None:
            return None
        return COMPASS_POINTS[round(self.wind_direction / 22.5) % 16]

    @property
    def humidity(self) -> int | None:
        if self.temperature_c is None or self.dewpoint_c is None:
            return None
        return round(relative_humidity(self.temperature_c, self.dewpoint_c))

    @property
    def feels_like_f(self) -> int | None:
        """Wind chill or heat index, only when it differs meaningfully from the temperature."""
        t = self.temperature_f
        if t is None:
            return None
        mph = self.wind_speed_mph or 0
        if t <= 50 and mph >= 3:
            feels = 35.74 + 0.6215 * t - 35.75 * mph**0.16 + 0.4275 * t * mph**0.16
        elif t >= 80 and self.humidity is not None:
            rh = self.humidity
            feels = (
                -42.379 + 2.04901523 * t + 10.14333127 * rh - 0.22475541 * t * rh
                - 0.00683783 * t * t - 0.05481717 * rh * rh + 0.00122874 * t * t * rh
                + 0.00085282 * t * rh * rh - 0.00000199 * t * t * rh * rh
            )
        else:
            return None
        return round(feels) if abs(feels - t) >= 3 else None

    @property
    def sky_headline(self) -> str:
        if self.cavok:
            return SKY_HEADLINE["CAVOK"]
        if not self.sky:
            return "Sky conditions unavailable"
        worst = max(self.sky, key=lambda layer: SKY_RANK.index(layer.cover))
        return SKY_HEADLINE[worst.cover]

    # ---- plain-English text --------------------------------------------

    def describe_wind(self) -> str:
        if self.wind_speed_kt is None:
            return "Wind information unavailable"
        if self.wind_speed_kt == 0:
            return "Calm winds"
        mph = self.wind_speed_mph
        strength = wind_strength(mph)
        if self.wind_variable or self.wind_direction is None:
            text = f"{strength} and variable winds around {mph} mph"
        else:
            text = f"{strength} wind from the {self.wind_compass} at {mph} mph"
        if self.wind_gust_kt:
            text += f", gusting to {self.wind_gust_mph} mph"
        return text[0].upper() + text[1:]

    def describe_visibility(self) -> str:
        if self.cavok:
            return "10+ km (unlimited)"
        if self.visibility_sm is None:
            return "Unavailable"
        miles = format_miles(self.visibility_sm)
        unit = "mile" if self.visibility_sm <= 1 else "miles"
        if self.visibility_modifier == "P" or self.visibility_sm >= 10:
            return f"{miles}+ miles (excellent)"
        if self.visibility_modifier == "M":
            return f"Less than {miles} mile (very poor)"
        if self.visibility_sm >= 5:
            quality = "good"
        elif self.visibility_sm >= 3:
            quality = "moderate"
        elif self.visibility_sm >= 1:
            quality = "poor"
        else:
            quality = "very poor"
        return f"{miles} {unit} ({quality})"

    def describe_weather(self) -> str | None:
        if not self.weather:
            return None
        return ", ".join(self.weather)

    def describe_sky(self) -> str:
        if self.cavok:
            return "No significant clouds"
        if not self.sky:
            return "Unavailable"
        return "; ".join(layer.describe() for layer in self.sky).capitalize()

    @property
    def summary(self) -> str:
        """A friendly one-paragraph weather report."""
        headline = self.sky_headline
        weather = self.describe_weather()
        if weather:
            headline = f"{weather.capitalize()}, {self.sky_headline.lower()}"

        parts = [headline]
        if self.temperature_c is not None:
            temp = f"{round(self.temperature_f)}°F ({round(self.temperature_c)}°C)"
            if self.feels_like_f is not None:
                temp += f", feels like {self.feels_like_f}°F"
            parts.append(temp)
        sentence = ", ".join(parts) + "."

        wind = self.describe_wind()
        sentence += f" {wind}."

        if self.visibility_sm is not None and self.visibility_sm < 3:
            sentence += f" Visibility is reduced to {format_miles(self.visibility_sm)} " \
                        f"{'mile' if self.visibility_sm <= 1 else 'miles'}."
        return sentence


# ---- helpers ------------------------------------------------------------

def c_to_f(celsius: float | None) -> float | None:
    return None if celsius is None else celsius * 9 / 5 + 32


def knots_to_mph(knots: int | None) -> int | None:
    return None if knots is None else round(knots * KNOTS_TO_MPH)


def relative_humidity(temp_c: float, dew_c: float) -> float:
    """Magnus formula."""
    a, b = 17.625, 243.04
    return 100 * math.exp(a * dew_c / (b + dew_c)) / math.exp(a * temp_c / (b + temp_c))


def wind_strength(mph: int) -> str:
    if mph < 8:
        return "light"
    if mph < 19:
        return "moderate"
    if mph < 32:
        return "strong"
    return "very strong"


def format_miles(miles: float) -> str:
    fractions = {0.25: "1/4", 0.5: "1/2", 0.75: "3/4"}
    whole, frac = int(miles), round(miles - int(miles), 2)
    if frac in fractions:
        return f"{whole} {fractions[frac]}" if whole else fractions[frac]
    return f"{miles:g}"


def parse_fraction(text: str) -> float:
    if "/" in text:
        num, den = text.split("/")
        return int(num) / int(den)
    return float(text)


def parse_temp(text: str) -> int:
    return -int(text[1:]) if text.startswith("M") else int(text)


def parse_observation_time(token: str, now: datetime) -> datetime:
    """Turn DDHHMMZ into a full UTC datetime, assuming the most recent matching day."""
    day, hour, minute = int(token[0:2]), int(token[2:4]), int(token[4:6])
    year, month = now.year, now.month
    if day > now.day:  # report is from last month
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


def describe_weather_token(match: re.Match) -> str:
    intensity = match.group("intensity")
    descriptor = match.group("descriptor")
    codes = re.findall(r"..", match.group("phenomena"))
    names = [PHENOMENA[c] for c in codes]

    if descriptor == "TS":
        text = "thunderstorm" + (f" with {' and '.join(names)}" if names else "")
    elif descriptor == "SH":
        text = f"{' and '.join(names)} showers" if names else "showers"
    elif descriptor:
        text = " ".join([DESCRIPTORS[descriptor], *names])
    else:
        text = " and ".join(names)

    if intensity == "VC":
        return f"{text} in the vicinity"
    if intensity:
        return f"{INTENSITY[intensity]} {text}"
    # Precipitation without a sign is moderate; obscurations (fog, haze) have no intensity.
    if codes and codes[0] in {"DZ", "RA", "SN", "SG", "PL", "GR", "GS", "UP"}:
        return f"moderate {text}"
    return text


# ---- main parser --------------------------------------------------------

def decode(raw: str, now: datetime | None = None) -> Metar:
    raw = " ".join(raw.split())
    if not raw:
        raise MetarDecodeError("Empty METAR")

    now = now or datetime.now(timezone.utc)
    body, _, remarks = raw.partition(" RMK ")
    tokens = body.split()
    report = Metar(raw=raw, remarks=remarks)

    if tokens and tokens[0] in ("METAR", "SPECI"):
        report.report_type = tokens.pop(0)
    if not tokens:
        raise MetarDecodeError("METAR is missing a station identifier")
    report.station = tokens.pop(0)

    pending_whole_miles = None  # for visibilities like "1 1/2SM"

    for token in tokens:
        if token in ("NOSIG", "TEMPO", "BECMG"):
            break  # trend forecast follows; it describes future, not current, weather
        if re.fullmatch(r"\d{6}Z", token):
            report.observed_at = parse_observation_time(token, now)
        elif token == "AUTO":
            report.automated = True
        elif token in ("COR", "CCA", "CCB"):
            report.corrected = True
        elif m := WIND_RE.match(token):
            speed = int(m.group("speed"))
            gust = int(m.group("gust")) if m.group("gust") else None
            if m.group("unit") == "MPS":
                speed = round(speed * 1.94384)
                gust = round(gust * 1.94384) if gust else None
            elif m.group("unit") == "KMH":
                speed = round(speed * 0.539957)
                gust = round(gust * 0.539957) if gust else None
            report.wind_speed_kt = speed
            report.wind_gust_kt = gust
            if m.group("dir") == "VRB":
                report.wind_variable = True
            else:
                report.wind_direction = int(m.group("dir"))
        elif m := WIND_VAR_RE.match(token):
            report.wind_variable_range = (int(m.group("from")), int(m.group("to")))
        elif re.fullmatch(r"\d", token):
            pending_whole_miles = int(token)
        elif m := VIS_SM_RE.match(token):
            value = parse_fraction(m.group("value"))
            if pending_whole_miles is not None:
                value += pending_whole_miles
            report.visibility_sm = value
            report.visibility_modifier = m.group("mod")
        elif VIS_METERS_RE.match(token) and report.visibility_sm is None:
            meters = int(token)
            report.visibility_sm = round(meters / 1609.34, 1)
            if meters == 9999:  # 10 km or more
                report.visibility_sm = 6.2
                report.visibility_modifier = "P"
        elif token == "CAVOK":
            report.cavok = True
            report.visibility_sm = 6.2
            report.visibility_modifier = "P"
        elif token in ("SKC", "CLR", "NSC", "NCD"):
            report.sky.append(SkyLayer(cover=token))
        elif m := SKY_RE.match(token):
            height = m.group("height")
            cloud_type = m.group("type")
            report.sky.append(SkyLayer(
                cover=m.group("cover"),
                height_ft=None if height == "///" else int(height) * 100,
                cloud_type=None if cloud_type in (None, "///") else cloud_type,
            ))
        elif m := TEMP_RE.match(token):
            report.temperature_c = parse_temp(m.group("temp"))
            if m.group("dew"):
                report.dewpoint_c = parse_temp(m.group("dew"))
        elif m := ALTIMETER_RE.match(token):
            value = int(m.group("value"))
            report.altimeter_inhg = value / 100 if m.group("unit") == "A" else round(value * 0.02953, 2)
        elif RVR_RE.match(token):
            continue
        elif token and (m := WEATHER_RE.match(token)) and (m.group("phenomena") or m.group("descriptor")):
            report.weather.append(describe_weather_token(m))
        # Anything else (NOSIG, TEMPO, trends, etc.) is ignored.

    # US stations often include a more precise temperature in the remarks, e.g. T01280061.
    for token in remarks.split():
        if m := PRECISE_TEMP_RE.match(token):
            sign = -1 if m.group("ts") == "1" else 1
            report.temperature_c = sign * int(m.group("t")) / 10
            if m.group("d"):
                report.dewpoint_c = (-1 if m.group("ds") == "1" else 1) * int(m.group("d")) / 10
            break

    return report
