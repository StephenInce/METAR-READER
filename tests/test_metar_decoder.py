from datetime import datetime, timezone

import pytest

from metar_decoder import MetarDecodeError, decode

NOW = datetime(2026, 10, 11, 20, 0, tzinfo=timezone.utc)


def test_clear_day_light_variable_wind():
    m = decode("METAR KHIO 111853Z VRB03KT 10SM CLR 13/06 A2991 RMK AO2 SLP128 T01280061", now=NOW)
    assert m.station == "KHIO"
    assert m.observed_at == datetime(2026, 10, 11, 18, 53, tzinfo=timezone.utc)
    assert m.wind_variable and m.wind_speed_kt == 3
    assert m.visibility_sm == 10
    assert m.temperature_c == 12.8  # precise value from the T-group remark
    assert m.dewpoint_c == 6.1
    assert m.altimeter_inhg == 29.91
    assert m.summary == "Clear skies, 55°F (13°C). Light and variable winds around 3 mph."


def test_gusty_wind_and_partly_cloudy():
    m = decode("METAR KDEN 111853Z 21014G24KT 10SM FEW100 SCT140 SCT220 27/04 A2981", now=NOW)
    assert m.wind_compass == "south-southwest"
    assert m.wind_speed_mph == 16 and m.wind_gust_mph == 28
    assert m.sky_headline == "Partly cloudy"
    assert "Moderate wind from the south-southwest at 16 mph, gusting to 28 mph" in m.summary


def test_rain_mist_and_fractional_visibility():
    m = decode("SPECI PANC 111937Z 15008KT 1 1/2SM -RA BR SCT023 BKN030 OVC048 06/03 A2956", now=NOW)
    assert m.report_type == "SPECI"
    assert m.visibility_sm == 1.5
    assert m.weather == ["light rain", "mist"]
    assert m.summary.startswith("Light rain, mist, overcast, 43°F (6°C)")
    assert "Visibility is reduced to 1 1/2 miles." in m.summary


def test_international_metric_report():
    m = decode("METAR EGLL 111920Z AUTO 16007KT 120V240 9999 OVC043 14/08 Q1014", now=NOW)
    assert m.automated
    assert m.wind_variable_range == (120, 240)
    assert m.describe_visibility() == "6.2+ miles (excellent)"
    assert m.sky[0].height_ft == 4300
    assert m.altimeter_inhg == 29.94


def test_negative_temperatures_and_thunderstorm():
    m = decode("METAR KXYZ 010000Z 00000KT 1/4SM +TSRA VV002 M05/M10 A3000", now=NOW)
    assert m.temperature_c == -5 and m.dewpoint_c == -10
    assert m.describe_wind() == "Calm winds"
    assert m.weather == ["heavy thunderstorm with rain"]
    assert m.sky_headline == "Sky obscured"


def test_missing_cloud_height_and_cavok():
    m = decode("METAR RJTT 111930Z 36012KT 9999 FEW030 BKN/// 20/16 Q1018 NOSIG", now=NOW)
    assert m.sky[1].height_ft is None
    assert decode("METAR LFPG 111930Z 27005KT CAVOK 18/10 Q1020", now=NOW).sky_headline == "Clear skies"


def test_wind_chill():
    m = decode("METAR KXYZ 111853Z 36020KT 10SM CLR M10/M15 A3000", now=NOW)
    assert m.feels_like_f is not None and m.feels_like_f < m.temperature_f


def test_report_from_previous_month():
    m = decode("METAR KXYZ 302350Z 00000KT 10SM CLR 10/05 A3000", now=NOW)
    assert m.observed_at == datetime(2026, 9, 30, 23, 50, tzinfo=timezone.utc)


def test_empty_metar():
    with pytest.raises(MetarDecodeError):
        decode("   ")
