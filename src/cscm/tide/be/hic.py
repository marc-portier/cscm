"""
Client for the Flemish Hydro Information Centre (HIC) Waterinfo KiWIS API.

Uses pywaterinfo to fetch operational coastal water level forecasts,
including meteorological surge forecasts (KT-Last), astronomical predictions (Astro.05),
and predicted tidal extremes (HW/LW) for coastal stations (Nieuwpoort, Oostende, Zeebrugge).
"""

from dataclasses import dataclass
from datetime import datetime, timezone
import logging
from typing import Dict, List, Optional, Union

import pandas as pd
from pywaterinfo import Waterinfo

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HicStation:
    """Represents a coastal monitoring and forecasting station in HIC KiWIS."""

    code: str  # Canonical 3-letter code (e.g. 'OST', 'NPT', 'ZLD')
    name: str  # Station name
    station_id: str  # HIC numerical station identifier
    station_no: str  # Official HIC station number (e.g. 'OST-1069')
    latitude: float
    longitude: float
    ts_forecast_5min: str  # KT-Last: Operational surge + tide model (5-min, m TAW)
    ts_astro_5min: str  # Astro.05: Astronomical tide prediction (5-min, m TAW)
    ts_forecast_hw: str  # KT-HW: Forecast High Water extremes
    ts_forecast_lw: str  # KT-LW: Forecast Low Water extremes
    ts_astro_hw: str  # Astro.HW: Astronomical High Water extremes
    ts_astro_lw: str  # Astro.LW: Astronomical Low Water extremes
    ts_observed_5min: Optional[str] = None  # O.05: 5-min gauge observation


# Canonical Flemish coastal water level forecasting stations
HIC_COASTAL_STATIONS: Dict[str, HicStation] = {
    "NPT": HicStation(
        code="NPT",
        name="Nieuwpoort MVB",
        station_id="30250",
        station_no="NPT-1069",
        latitude=51.150003,
        longitude=2.728132,
        ts_forecast_5min="96860010",
        ts_astro_5min="88662010",
        ts_forecast_hw="96949010",
        ts_forecast_lw="96950010",
        ts_astro_hw="115328010",
        ts_astro_lw="115329010",
        ts_observed_5min="55152010",
    ),
    "OST": HicStation(
        code="OST",
        name="Oostende MVB",
        station_id="30256",
        station_no="OST-1069",
        latitude=51.234286,
        longitude=2.926681,
        ts_forecast_5min="96861010",
        ts_astro_5min="84306010",
        ts_forecast_hw="96952010",
        ts_forecast_lw="96953010",
        ts_astro_hw="115332010",
        ts_astro_lw="115333010",
        ts_observed_5min="55177010",
    ),
    "ZLD": HicStation(
        code="ZLD",
        name="Zeebrugge MVB",
        station_id="30408",
        station_no="ZLD-1069",
        latitude=51.346400,
        longitude=3.200364,
        ts_forecast_5min="96872010",
        ts_astro_5min="88658010",
        ts_forecast_hw="96985010",
        ts_forecast_lw="96986010",
        ts_astro_hw="115330010",
        ts_astro_lw="115331010",
        ts_observed_5min="56191010",
    ),
}

# Synonyms for interoperability with MDK codes
HIC_COASTAL_STATIONS["OHM"] = HIC_COASTAL_STATIONS["OST"]
HIC_COASTAL_STATIONS["ZB"] = HIC_COASTAL_STATIONS["ZLD"]


class HicClient:
    """
    Client for querying the HIC Waterinfo KiWIS API via pywaterinfo.

    Specialized in retrieving short-term water level forecasts (today + 1..3 days)
    and astronomical tidal curves for Belgian coastal resorts.
    """

    def __init__(self, waterinfo: Optional[Waterinfo] = None):
        """Initialize the HIC client."""
        self._hic = waterinfo or Waterinfo("hic")

    def get_station(self, station_code: str) -> HicStation:
        """Resolve a station by its code (e.g. 'OST', 'OHM', 'NPT', 'ZLD')."""
        key = station_code.strip().upper()
        if key not in HIC_COASTAL_STATIONS:
            known = ", ".join(HIC_COASTAL_STATIONS.keys())
            raise ValueError(f"Unknown station code '{station_code}'. Available: {known}")
        return HIC_COASTAL_STATIONS[key]

    @staticmethod
    def _format_timestamp(dt: datetime) -> str:
        """Format datetime as YYYYMMDDHHMM (UTC) expected by KiWIS."""
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt.strftime("%Y%m%d%H%M")

    def get_water_levels(
        self,
        station_code: str,
        start_time: datetime,
        end_time: datetime,
        source: str = "forecast",
    ) -> pd.DataFrame:
        """
        Fetch 5-minute water level timeseries in meters TAW.

        Parameters
        ----------
        station_code : str
            Station identifier (e.g. 'OST', 'NPT', 'ZLD').
        start_time : datetime
            Start of query interval.
        end_time : datetime
            End of query interval.
        source : str, default 'forecast'
            - 'forecast': Operational hydrodynamic model including meteorological storm surge (KT-Last)
            - 'astro': Pure astronomical tide prediction (Astro.05)
            - 'observed': Historical 5-minute sensor observations (O.05)

        Returns
        -------
        pd.DataFrame
            DataFrame with columns ['timestamp', 'water_level_m_taw', 'station', 'source']
        """
        station = self.get_station(station_code)
        source_clean = source.strip().lower()

        if source_clean == "forecast":
            ts_id = station.ts_forecast_5min
        elif source_clean == "astro":
            ts_id = station.ts_astro_5min
        elif source_clean == "observed":
            if not station.ts_observed_5min:
                raise ValueError(f"No observed timeseries registered for station {station.code}")
            ts_id = station.ts_observed_5min
        else:
            raise ValueError(f"Invalid source '{source}'. Choose from 'forecast', 'astro', 'observed'")

        start_str = self._format_timestamp(start_time)
        end_str = self._format_timestamp(end_time)

        logger.info(
            "Fetching HIC %s water levels for %s (ts_id=%s) from %s to %s UTC",
            source_clean,
            station.code,
            ts_id,
            start_str,
            end_str,
        )

        raw_df = self._hic.get_timeseries_values(ts_id=ts_id, start=start_str, end=end_str)

        if raw_df is None or raw_df.empty:
            logger.warning("HIC returned no data for %s (%s)", station.code, source_clean)
            return pd.DataFrame(columns=["timestamp", "water_level_m_taw", "station", "source"])

        # Determine value column (typically 'Value', fallback to first numeric column)
        val_col = "Value" if "Value" in raw_df.columns else raw_df.columns[1]

        df = pd.DataFrame(
            {
                "timestamp": pd.to_datetime(raw_df["Timestamp"], utc=True),
                "water_level_m_taw": pd.to_numeric(raw_df[val_col], errors="coerce"),
                "station": station.code,
                "source": source_clean,
            }
        ).dropna(subset=["water_level_m_taw"])

        return df.sort_values("timestamp").reset_index(drop=True)

    def get_extremes(
        self,
        station_code: str,
        start_time: datetime,
        end_time: datetime,
        source: str = "forecast",
    ) -> pd.DataFrame:
        """
        Fetch High Water (HW) and Low Water (LW) tidal extremes in meters TAW.

        Parameters
        ----------
        station_code : str
            Station identifier ('OST', 'NPT', 'ZLD').
        start_time : datetime
            Start of query interval.
        end_time : datetime
            End of query interval.
        source : str, default 'forecast'
            'forecast' (KT-HW and KT-LW) or 'astro' (Astro.HW and Astro.LW).

        Returns
        -------
        pd.DataFrame
            DataFrame with columns ['timestamp', 'water_level_m_taw', 'extreme_type', 'station', 'source']
        """
        station = self.get_station(station_code)
        source_clean = source.strip().lower()

        if source_clean == "forecast":
            ts_hw = station.ts_forecast_hw
            ts_lw = station.ts_forecast_lw
        elif source_clean == "astro":
            ts_hw = station.ts_astro_hw
            ts_lw = station.ts_astro_lw
        else:
            raise ValueError(f"Invalid source '{source}' for extremes. Choose 'forecast' or 'astro'")

        start_str = self._format_timestamp(start_time)
        end_str = self._format_timestamp(end_time)

        frames = []
        for ts_id, extreme_type in [(ts_hw, "HW"), (ts_lw, "LW")]:
            raw_df = self._hic.get_timeseries_values(ts_id=ts_id, start=start_str, end=end_str)
            if raw_df is not None and not raw_df.empty:
                val_col = "Value" if "Value" in raw_df.columns else raw_df.columns[1]
                sub_df = pd.DataFrame(
                    {
                        "timestamp": pd.to_datetime(raw_df["Timestamp"], utc=True),
                        "water_level_m_taw": pd.to_numeric(raw_df[val_col], errors="coerce"),
                        "extreme_type": extreme_type,
                        "station": station.code,
                        "source": source_clean,
                    }
                ).dropna(subset=["water_level_m_taw"])
                frames.append(sub_df)

        if not frames:
            return pd.DataFrame(columns=["timestamp", "water_level_m_taw", "extreme_type", "station", "source"])

        combined = pd.concat(frames, ignore_index=True)
        return combined.sort_values("timestamp").reset_index(drop=True)

    def get_interpolated_curve(
        self,
        station_code: str,
        start_time: datetime,
        end_time: datetime,
        time_offset_minutes: float = 0.0,
        source: str = "forecast",
    ) -> pd.DataFrame:
        """
        Fetch water levels and shift them temporally by time_offset_minutes.

        For example, Bredene Strandpost 4 experiences tidal phases with a +7 minute
        delay relative to Oostende Haven.

        Parameters
        ----------
        station_code : str
            Base reference station (e.g. 'OST').
        start_time : datetime
            Desired start time for the target location.
        end_time : datetime
            Desired end time for the target location.
        time_offset_minutes : float
            Delay in minutes (positive means target location lags behind base station).
        source : str
            'forecast' or 'astro'.

        Returns
        -------
        pd.DataFrame
            DataFrame with shifted timestamps matching the target location's clock.
        """
        # Query base station shifted back by the offset
        delta = pd.Timedelta(minutes=time_offset_minutes)
        query_start = start_time - delta
        query_end = end_time - delta

        df = self.get_water_levels(station_code, query_start, query_end, source=source)
        if df.empty:
            return df

        # Shift timestamps forward to target location
        df["timestamp"] = df["timestamp"] + delta
        df["target_offset_min"] = time_offset_minutes
        return df
