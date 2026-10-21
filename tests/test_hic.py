"""Tests for the HIC Waterinfo KiWIS client module."""

from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

import pandas as pd
import pytest

from cscm.tide.be.hic import HicClient, HicStation, HIC_COASTAL_STATIONS
from cscm.tide import HicClient as ReexportedHicClient


def test_station_resolution():
    """Verify that canonical station codes and synonyms resolve properly."""
    client = HicClient(waterinfo=MagicMock())

    # Direct canonical lookup
    ost = client.get_station("OST")
    assert ost.code == "OST"
    assert ost.name == "Oostende MVB"
    assert ost.ts_forecast_5min == "96861010"
    assert ost.ts_astro_5min == "84306010"

    # Synonyms & case insensitivity
    assert client.get_station("ohm") == ost
    assert client.get_station("NPT").code == "NPT"
    assert client.get_station("zld").code == "ZLD"
    assert client.get_station("zb").code == "ZLD"

    # Unknown code raises ValueError
    with pytest.raises(ValueError, match="Unknown station code"):
        client.get_station("XYZ")

    # Verify backward compatibility of re-export from cscm.tide
    assert ReexportedHicClient is HicClient


def test_get_water_levels_mocked():
    """Verify fetching and parsing of 5-minute water level curves."""
    mock_wi = MagicMock()
    mock_wi.get_timeseries_values.return_value = pd.DataFrame(
        {
            "Timestamp": ["2026-10-15 12:00:00+00:00", "2026-10-15 12:05:00+00:00"],
            "Value": ["4.12", "4.25"],
        }
    )

    client = HicClient(waterinfo=mock_wi)
    t0 = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 10, 15, 12, 10, tzinfo=timezone.utc)

    df = client.get_water_levels("OST", t0, t1, source="forecast")

    assert len(df) == 2
    assert list(df.columns) == ["timestamp", "water_level_m_taw", "station", "source"]
    assert df["water_level_m_taw"].iloc[0] == pytest.approx(4.12)
    assert df["water_level_m_taw"].iloc[1] == pytest.approx(4.25)
    assert df["station"].iloc[0] == "OST"
    assert df["source"].iloc[0] == "forecast"

    # Verify KiWIS call args
    mock_wi.get_timeseries_values.assert_called_once_with(
        ts_id="96861010",
        start="202610151200",
        end="202610151210",
    )


def test_get_extremes_mocked():
    """Verify merging and tagging of High Water and Low Water extremes."""
    mock_wi = MagicMock()

    def mock_get_ts(ts_id, start, end):
        if ts_id == "96952010":  # KT-HW Oostende
            return pd.DataFrame({"Timestamp": ["2026-10-15 14:35:00+00:00"], "Value": ["4.55"]})
        elif ts_id == "96953010":  # KT-LW Oostende
            return pd.DataFrame({"Timestamp": ["2026-10-15 08:50:00+00:00"], "Value": ["0.40"]})
        return pd.DataFrame()

    mock_wi.get_timeseries_values.side_effect = mock_get_ts

    client = HicClient(waterinfo=mock_wi)
    t0 = datetime(2026, 10, 15, 0, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 10, 15, 23, 59, tzinfo=timezone.utc)

    df = client.get_extremes("OST", t0, t1, source="forecast")

    assert len(df) == 2
    # Chronologically sorted: LW (08:50) before HW (14:35)
    assert df["extreme_type"].iloc[0] == "LW"
    assert df["water_level_m_taw"].iloc[0] == pytest.approx(0.40)
    assert df["extreme_type"].iloc[1] == "HW"
    assert df["water_level_m_taw"].iloc[1] == pytest.approx(4.55)


def test_get_interpolated_curve_mocked():
    """Verify temporal lag shifting (e.g. +7 min for Bredene)."""
    mock_wi = MagicMock()
    mock_wi.get_timeseries_values.return_value = pd.DataFrame(
        {
            "Timestamp": ["2026-10-15 12:00:00+00:00"],
            "Value": ["3.50"],
        }
    )

    client = HicClient(waterinfo=mock_wi)
    t0 = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 10, 15, 12, 10, tzinfo=timezone.utc)

    df = client.get_interpolated_curve("OST", t0, t1, time_offset_minutes=7.0, source="forecast")

    assert len(df) == 1
    # 12:00 shifted forward by 7 minutes becomes 12:07
    expected_ts = pd.Timestamp("2026-10-15 12:07:00+00:00")
    assert df["timestamp"].iloc[0] == expected_ts
    assert df["target_offset_min"].iloc[0] == 7.0


def test_hic_tide_manager_caching_and_catalog(tmp_path):
    """Verify that HicTideManager stores data and registers entries in catalog.json."""
    from cscm.tide.be.hic import HicTideManager

    mock_client = MagicMock(spec=HicClient)
    ost_station = HIC_COASTAL_STATIONS["OST"]
    mock_client.get_station.return_value = ost_station

    dummy_df = pd.DataFrame({
        "timestamp": [
            pd.Timestamp("2026-10-21 00:00:00+00:00"),
            pd.Timestamp("2026-10-21 01:00:00+00:00"),
        ],
        "water_level_m_taw": [4.2, 3.8],
        "station": ["OST", "OST"],
        "source": ["forecast", "forecast"],
    })
    mock_client.get_water_levels.return_value = dummy_df

    manager = HicTideManager(data_folder=tmp_path, client=mock_client)
    t0 = datetime(2026, 10, 21, 0, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 10, 21, 1, 0, tzinfo=timezone.utc)

    # First call: should query client and write to disk + catalog
    df1 = manager.get_water_levels("OST", t0, t1, source="forecast")
    assert len(df1) == 2
    mock_client.get_water_levels.assert_called_once()
    assert manager.catalog_path.exists()

    catalog = manager.get_catalog(force_reload=True)
    assert len(catalog) == 1
    assert catalog[0].metadata["station"] == "OST"
    assert catalog[0].is_forecast is True

    # Second call for the same interval: should hit cache without calling client again!
    mock_client.get_water_levels.reset_mock()
    df2 = manager.get_water_levels("OST", t0, t1, source="forecast")
    assert len(df2) == 2
    mock_client.get_water_levels.assert_not_called()