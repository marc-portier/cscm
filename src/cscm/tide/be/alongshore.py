"""
Belgian Coastal Alongshore Tidal Interpolation and Extrapolation Model.

Discretizes the 66.5 km Belgian coastline into alongshore chainage coordinates (s in [0.0, 66.5 km])
and evaluates water level curves h(t, s) by phase-shifting and spatially interpolating
between primary Flemish Hydro Information Centre (HIC) coastal tide stations (NPT, OST, ZLD).
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union
import logging
import numpy as np
import pandas as pd
import yaml

from cscm.tide.hic import HicClient

logger = logging.getLogger(__name__)

# Default reference station positions along the Belgian alongshore chainage (km from French border)
DEFAULT_STATION_CHAINAGE = {
    "NPT": 15.00,   # Nieuwpoort Haven
    "OST": 31.50,   # Oostende Haven
    "ZLD": 53.25,   # Zeebrugge Haven
}

# Empirical phase propagation delays (minutes) between stations under typical conditions
# High Water progresses from SW to NE: NPT -> OST -> ZLD
DEFAULT_PHASE_LAG_NPT_OST_MIN = 15.0  # ~0.91 min/km
DEFAULT_PHASE_LAG_OST_ZLD_MIN = 22.0  # ~1.01 min/km


@dataclass
class InterpolatedTidePoint:
    """Result of alongshore tidal interpolation for a single spatial point."""

    chainage_km: float
    name: Optional[str]
    regime: str  # 'west_extrapolation' | 'npt_ost_interpolation' | 'ost_zld_interpolation' | 'east_extrapolation'
    phase_lag_min: float  # Time shift in minutes relative to Oostende (OST)
    weights: Dict[str, float]  # Contribution weights of reference stations (e.g. {'OST': 0.83, 'ZLD': 0.17})
    water_levels: pd.DataFrame  # Timeseries with columns ['timestamp', 'water_level_m_taw']


class AlongshoreTidalModel:
    """
    Alongshore 1D tidal interpolation and extrapolation model for the Belgian North Sea coast.
    """

    def __init__(
        self,
        yaml_path: Optional[Union[str, Path]] = None,
        hic_client: Optional[HicClient] = None,
    ):
        """Initialize the alongshore model with coastal registry metadata."""
        if yaml_path is None:
            # Fallback to packaged full-coast locations registry
            repo_root = Path(__file__).resolve().parents[4]
            yaml_path = repo_root / "src" / "cscm" / "resources" / "be-full-coast-locations.yaml"

        self.yaml_path = Path(yaml_path)
        self.hic = hic_client or HicClient()
        self._load_registry()

    def _load_registry(self) -> None:
        """Load stations and chainage nodes from YAML registry."""
        with open(self.yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        self.metadata = data.get("metadata", {})
        self.station_chainage = dict(DEFAULT_STATION_CHAINAGE)

        # Update station chainage if specified in registry
        wl_stations = data.get("water_level_stations", {})
        if "nieuwpoort" in wl_stations and "chainage_km" in wl_stations["nieuwpoort"]:
            self.station_chainage["NPT"] = float(wl_stations["nieuwpoort"]["chainage_km"])
        if "oostende" in wl_stations and "chainage_km" in wl_stations["oostende"]:
            self.station_chainage["OST"] = float(wl_stations["oostende"]["chainage_km"])
        if "zeebrugge" in wl_stations and "chainage_km" in wl_stations["zeebrugge"]:
            self.station_chainage["ZLD"] = float(wl_stations["zeebrugge"]["chainage_km"])

        self.chainage_nodes = data.get("chainage_750m", [])
        self.landmarks = data.get("landmarks", [])
        self.municipalities = data.get("municipalities", {})

    def get_regime_and_weights(self, s_km: float) -> Tuple[str, float, Dict[str, float]]:
        """
        Determine interpolation regime, phase lag relative to Oostende (OST), and station weights.

        Args:
            s_km: Alongshore chainage distance in kilometers (0.0 to 66.5 km).

        Returns:
            Tuple of (regime_name, phase_lag_min_relative_to_ost, weights_dict)
        """
        s_npt = self.station_chainage["NPT"]  # 15.0
        s_ost = self.station_chainage["OST"]  # 31.5
        s_zld = self.station_chainage["ZLD"]  # 53.25

        lag_npt_ost = DEFAULT_PHASE_LAG_NPT_OST_MIN
        lag_ost_zld = DEFAULT_PHASE_LAG_OST_ZLD_MIN

        rate_west = lag_npt_ost / (s_ost - s_npt)   # ~0.91 min/km
        rate_east = lag_ost_zld / (s_zld - s_ost)   # ~1.01 min/km

        if s_km < s_npt:
            # 1. West extrapolation (De Panne to Nieuwpoort)
            # Tide occurs earlier than Nieuwpoort (negative lag relative to OST)
            regime = "west_extrapolation"
            lag = -lag_npt_ost - (s_npt - s_km) * rate_west
            weights = {"NPT": 1.0}

        elif s_km <= s_ost:
            # 2. Mid-West interpolation (Nieuwpoort to Oostende)
            regime = "npt_ost_interpolation"
            alpha = (s_km - s_npt) / (s_ost - s_npt)
            lag = -lag_npt_ost * (1.0 - alpha)
            weights = {"NPT": 1.0 - alpha, "OST": alpha}

        elif s_km <= s_zld:
            # 3. Mid-East interpolation (Oostende to Zeebrugge)
            regime = "ost_zld_interpolation"
            beta = (s_km - s_ost) / (s_zld - s_ost)
            lag = lag_ost_zld * beta
            weights = {"OST": 1.0 - beta, "ZLD": beta}

        else:
            # 4. East extrapolation (Zeebrugge to Het Zwin)
            # Tide occurs later than Zeebrugge
            regime = "east_extrapolation"
            lag = lag_ost_zld + (s_km - s_zld) * rate_east
            weights = {"ZLD": 1.0}

        return regime, round(lag, 2), {k: round(v, 4) for k, v in weights.items()}

    def predict_alongshore_water_levels(
        self,
        s_km: float,
        station_data: Dict[str, pd.DataFrame],
        name: Optional[str] = None,
    ) -> InterpolatedTidePoint:
        """
        Evaluate interpolated water level curve for a target chainage point using station timeseries.

        Args:
            s_km: Alongshore chainage distance in kilometers (0.0 to 66.5 km).
            station_data: Dictionary mapping station codes ('NPT', 'OST', 'ZLD') to DataFrames
                          with ['timestamp', 'water_level_m_taw'].
            name: Optional descriptive label.

        Returns:
            InterpolatedTidePoint dataclass with the continuous water level curve.
        """
        regime, lag_min, weights = self.get_regime_and_weights(s_km)

        # Base reference time grid is taken from the highest-weight station (or OST)
        ref_code = max(weights, key=weights.get)
        ref_df = station_data[ref_code].copy().sort_values("timestamp").reset_index(drop=True)
        timestamps = pd.to_datetime(ref_df["timestamp"], utc=True)
        epoch_utc = pd.Timestamp("1970-01-01", tz="UTC")
        t_ref_sec = (timestamps - epoch_utc).dt.total_seconds().values

        # Compute phase-shifted and weighted water level series
        levels = np.zeros(len(timestamps), dtype=float)

        for code, w in weights.items():
            if w <= 0.0:
                continue
            df_st = station_data[code].copy().sort_values("timestamp")
            t_st_dt = pd.to_datetime(df_st["timestamp"], utc=True)
            t_st = (t_st_dt - epoch_utc).dt.total_seconds().values
            h_st = df_st["water_level_m_taw"].values

            # Time shift for this station relative to the target point
            st_chainage = self.station_chainage[code]
            _, st_lag_to_ost, _ = self.get_regime_and_weights(st_chainage)
            delta_t_sec = (lag_min - st_lag_to_ost) * 60.0

            # Query station curve at shifted times
            target_times_sec = t_ref_sec - delta_t_sec
            h_interp = np.interp(target_times_sec, t_st, h_st)
            levels += w * h_interp

        res_df = pd.DataFrame({
            "timestamp": timestamps,
            "water_level_m_taw": np.round(levels, 3)
        })

        return InterpolatedTidePoint(
            chainage_km=s_km,
            name=name,
            regime=regime,
            phase_lag_min=lag_min,
            weights=weights,
            water_levels=res_df,
        )

    def fetch_reference_station_data(
        self,
        start_dt: datetime,
        end_dt: datetime,
        source: str = "forecast",
    ) -> Dict[str, pd.DataFrame]:
        """Fetch 5-minute water levels for NPT, OST, and ZLD from HIC."""
        data = {}
        for code in ["NPT", "OST", "ZLD"]:
            df = self.hic.get_water_levels(code, start_dt, end_dt, source=source)
            data[code] = df
        return data

    def predict_all_chainage_nodes(
        self,
        station_data: Dict[str, pd.DataFrame],
    ) -> List[InterpolatedTidePoint]:
        """Compute alongshore tidal curves across all 89 chainage markers."""
        results = []
        for node in self.chainage_nodes:
            s_km = float(node["chainage_km"])
            marker = node["marker"]
            pt = self.predict_alongshore_water_levels(s_km, station_data, name=marker)
            results.append(pt)
        return results
