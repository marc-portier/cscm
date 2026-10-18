"""Unit tests for Belgian alongshore tidal model."""

from datetime import datetime, timezone, timedelta
import numpy as np
import pandas as pd
import pytest

from cscm.tide.be.alongshore import AlongshoreTidalModel, InterpolatedTidePoint


@pytest.fixture
def synthetic_station_data():
    """Create a 12-hour synthetic tidal curve for NPT, OST, ZLD with known phase shifts."""
    t0 = datetime(2026, 10, 18, 0, 0, tzinfo=timezone.utc)
    times = [t0 + timedelta(minutes=5 * i) for i in range(145)]  # 12 hours at 5-min
    timestamps = [t.isoformat() for t in times]
    t_sec = np.array([5 * 60 * i for i in range(145)], dtype=float)

    # M2 period: 12.42 hours = 44712 seconds
    T_m2 = 44712.0
    omega = 2.0 * np.pi / T_m2

    # OST peak at t = 3.0h (10800 s)
    # NPT leads OST by 15 min (900 s) -> peak at t = 2.75h (9900 s)
    # ZLD lags OST by 22 min (1320 s) -> peak at t = 3.37h (12120 s)
    h_ost = 2.5 + 1.5 * np.cos(omega * (t_sec - 10800.0))
    h_npt = 2.5 + 1.5 * np.cos(omega * (t_sec - 9900.0))
    h_zld = 2.5 + 1.5 * np.cos(omega * (t_sec - 12120.0))

    return {
        "OST": pd.DataFrame({"timestamp": timestamps, "water_level_m_taw": np.round(h_ost, 3)}),
        "NPT": pd.DataFrame({"timestamp": timestamps, "water_level_m_taw": np.round(h_npt, 3)}),
        "ZLD": pd.DataFrame({"timestamp": timestamps, "water_level_m_taw": np.round(h_zld, 3)}),
    }


def test_regime_and_weights():
    """Verify interpolation regimes across the coast."""
    model = AlongshoreTidalModel()

    # 1. West extrapolation (De Panne, s = 3.0 km)
    regime, lag, weights = model.get_regime_and_weights(3.0)
    assert regime == "west_extrapolation"
    assert weights == {"NPT": 1.0}
    assert lag < -15.0  # More advance than Nieuwpoort

    # 2. Exact station NPT (s = 15.0 km)
    regime, lag, weights = model.get_regime_and_weights(15.0)
    assert regime == "npt_ost_interpolation"
    assert weights["NPT"] == pytest.approx(1.0)
    assert weights["OST"] == pytest.approx(0.0)
    assert lag == pytest.approx(-15.0)

    # 3. Exact station OST (s = 31.5 km)
    regime, lag, weights = model.get_regime_and_weights(31.5)
    assert regime == "npt_ost_interpolation"
    assert weights["OST"] == pytest.approx(1.0)
    assert lag == pytest.approx(0.0)

    # 4. Bredene Post 4 (s = 35.25 km)
    regime, lag, weights = model.get_regime_and_weights(35.25)
    assert regime == "ost_zld_interpolation"
    assert weights["OST"] > 0.8
    assert weights["ZLD"] < 0.2
    assert 3.0 < lag < 5.0  # Approx +4 min lag relative to Oostende

    # 5. Exact station ZLD (s = 53.25 km)
    regime, lag, weights = model.get_regime_and_weights(53.25)
    assert regime == "ost_zld_interpolation"
    assert weights["ZLD"] == pytest.approx(1.0)
    assert lag == pytest.approx(22.0)

    # 6. East extrapolation (Het Zwin, s = 66.0 km)
    regime, lag, weights = model.get_regime_and_weights(66.0)
    assert regime == "east_extrapolation"
    assert weights == {"ZLD": 1.0}
    assert lag > 22.0  # Further lag after Zeebrugge


def test_predict_alongshore_water_levels(synthetic_station_data):
    """Verify water level calculation at stations and intermediate points."""
    model = AlongshoreTidalModel()

    # Evaluating at Oostende should match OST data exactly
    ost_pt = model.predict_alongshore_water_levels(31.5, synthetic_station_data, name="Oostende")
    assert isinstance(ost_pt, InterpolatedTidePoint)
    assert len(ost_pt.water_levels) == 145
    diff_ost = np.abs(ost_pt.water_levels["water_level_m_taw"] - synthetic_station_data["OST"]["water_level_m_taw"])
    assert diff_ost.max() < 0.05

    # Evaluating at Bredene Post 4 (s = 35.25 km)
    bredene_pt = model.predict_alongshore_water_levels(35.25, synthetic_station_data, name="Bredene")
    assert bredene_pt.phase_lag_min > 0.0
    # Peak at Bredene should be shifted relative to OST
    hw_ost_idx = synthetic_station_data["OST"]["water_level_m_taw"].idxmax()
    hw_bredene_idx = bredene_pt.water_levels["water_level_m_taw"].idxmax()
    # High water at Bredene occurs later than Oostende (higher index)
    assert hw_bredene_idx >= hw_ost_idx


def test_predict_all_chainage_nodes(synthetic_station_data):
    """Verify predicting all 89 chainage markers."""
    model = AlongshoreTidalModel()
    results = model.predict_all_chainage_nodes(synthetic_station_data)
    assert len(results) == len(model.chainage_nodes)
    assert results[0].chainage_km == pytest.approx(0.0)
    assert results[-1].chainage_km == pytest.approx(66.0)


def test_fetch_reference_station_data_mdk():
    """Verify that AlongshoreTidalModel supports MDK station data retrieval."""
    from unittest.mock import patch, MagicMock

    model = AlongshoreTidalModel()

    with patch("cscm.tide.be.mdk.MdkClient") as mock_mdk_cls:
        mock_instance = MagicMock()
        mock_instance.get_water_levels.return_value = pd.DataFrame(
            {
                "timestamp": ["2026-10-18T12:00:00+00:00"],
                "water_level_m_taw": [4.2],
            }
        )
        mock_mdk_cls.return_value = mock_instance

        t0 = datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc)
        t1 = datetime(2026, 10, 18, 13, 0, tzinfo=timezone.utc)
        res = model.fetch_reference_station_data(t0, t1, provider="mdk")

        assert "NPT" in res
        assert "OST" in res
        assert "ZLD" in res
        assert res["OST"]["water_level_m_taw"].iloc[0] == pytest.approx(4.2)
