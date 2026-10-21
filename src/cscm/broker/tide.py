"""
Universal Data Access Layer (UDAL) - Belgian Tide Domain Brokers.

Implements specialized brokers for HIC (operational forecasts / astronomical curves)
and MDK (historical high-precision sensor observations), plus the overarching
BelgianTideBroker that seamlessly splits and composites historical observations
and future forecasts across 'now'.
"""

from datetime import datetime, timezone, timedelta
import logging
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd

from cscm.broker.base import AbstractDataBroker, NamedQuery, QueryResult
from cscm.broker.catalogue import URI_QUERY_TIDE, resolve_query_contract
from cscm.broker.exceptions import (
    GeographicOutOfDomainError,
    InvalidQueryParameterError,
    TemporalOutOfDomainError,
)
from cscm.tide.be.hic import HIC_COASTAL_STATIONS, HicStation, HicTideManager
from cscm.tide.be.mdk import COASTAL_TIDE_STATIONS, MdkTideManager

log = logging.getLogger(__name__)

# Maximum permissible distance in meters from the nearest Belgian coastal gauge (~35 km)
BELGIAN_COASTAL_MAX_DISTANCE_M = 35_000.0


def _find_nearest_station(lat: float, lon: float) -> Tuple[HicStation, float]:
    """
    Finds the nearest canonical HIC coastal station to given coordinates
    and computes the approximate distance in meters.
    """
    best_station = None
    min_dist = float("inf")
    for code, station in HIC_COASTAL_STATIONS.items():
        if code in ("OHM", "ZB"):  # skip synonyms
            continue
        d_lat = (station.latitude - lat) * 111320.0
        d_lon = (station.longitude - lon) * 111320.0 * np.cos(np.radians(lat))
        dist = np.hypot(d_lat, d_lon)
        if dist < min_dist:
            min_dist = dist
            best_station = station
    return best_station, min_dist


class HicTideBroker(AbstractDataBroker):
    """
    Specialized broker for Flemish Hydro Information Centre (HIC) Waterinfo KiWIS data.
    Provides operational hydrodynamic surge + tide forecasts (KT-Last) and astronomical extremes.
    """

    def __init__(self, manager: Optional[HicTideManager] = None):
        self.manager = manager or HicTideManager()

    def named_query(self, uri: str = URI_QUERY_TIDE) -> NamedQuery:
        contract = resolve_query_contract(uri)
        return NamedQuery(uri=contract.uri, contract=contract, broker=self)

    def _execute_query(self, query: NamedQuery) -> QueryResult:
        params = query.params
        station_code: Optional[str] = params.get("station")
        lat: Optional[float] = params.get("lat")
        lon: Optional[float] = params.get("lon")
        start_time: Optional[datetime] = params.get("start_time")
        end_time: Optional[datetime] = params.get("end_time")
        source_param: str = str(params.get("source", "forecast")).lower()
        time_offset_min: float = float(params.get("time_offset_minutes", 0.0))

        now_utc = datetime.now(timezone.utc)
        if start_time is None:
            start_time = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        if end_time is None:
            end_time = start_time + timedelta(days=1)

        if start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=timezone.utc)
        if end_time.tzinfo is None:
            end_time = end_time.replace(tzinfo=timezone.utc)

        if start_time > end_time:
            raise InvalidQueryParameterError(
                f"Query start_time ({start_time.isoformat()}) must be before end_time ({end_time.isoformat()})."
            )

        # Spatial resolution & geographic domain validation
        resolved_lat = lat
        resolved_lon = lon
        if station_code:
            station = self.manager.client.get_station(station_code)
            if resolved_lat is None:
                resolved_lat = station.latitude
            if resolved_lon is None:
                resolved_lon = station.longitude
        elif lat is not None and lon is not None:
            station, dist_m = _find_nearest_station(lat, lon)
            if dist_m > BELGIAN_COASTAL_MAX_DISTANCE_M:
                raise GeographicOutOfDomainError(
                    lat=lat,
                    lon=lon,
                    provider="HIC Waterinfo",
                    max_distance_km=BELGIAN_COASTAL_MAX_DISTANCE_M / 1000.0,
                )
            station_code = station.code
            if station.code == "OST" and lon > 2.95 and time_offset_min == 0.0:
                time_offset_min = 7.0  # +7 min phase lag for Bredene
        else:
            station = self.manager.client.get_station("OST")
            station_code = station.code
            resolved_lat = station.latitude
            resolved_lon = station.longitude

        df = self.manager.get_water_levels(
            station_code=station.code,
            start_time=start_time,
            end_time=end_time,
            source=source_param,
        )

        if time_offset_min != 0.0 and not df.empty:
            df["timestamp"] = df["timestamp"] + pd.Timedelta(minutes=time_offset_min)

        if not df.empty:
            df["lat"] = resolved_lat
            df["lon"] = resolved_lon
            result_df = df[["timestamp", "lat", "lon", "station", "water_level_m_taw", "source"]].reset_index(drop=True)
        else:
            result_df = pd.DataFrame(columns=["timestamp", "lat", "lon", "station", "water_level_m_taw", "source"])

        metadata = {
            "uri": URI_QUERY_TIDE,
            "provider": "hic",
            "station": station.code,
            "station_name": station.name,
            "target_lat": lat,
            "target_lon": lon,
            "resolved_lat": resolved_lat,
            "resolved_lon": resolved_lon,
            "effective_source": source_param,
            "time_offset_minutes": time_offset_min,
            "units": {"water_level_m_taw": "m TAW"},
        }
        return QueryResult(_df=result_df, metadata=metadata)


class MdkTideBroker(AbstractDataBroker):
    """
    Specialized broker for Meetnet Vlaamse Banken (MDK) high-precision sensor measurements.
    Strictly serves historical observations (past up to present).
    """

    def __init__(self, manager: Optional[MdkTideManager] = None):
        self.manager = manager or MdkTideManager()

    def named_query(self, uri: str = URI_QUERY_TIDE) -> NamedQuery:
        contract = resolve_query_contract(uri)
        return NamedQuery(uri=contract.uri, contract=contract, broker=self)

    def _execute_query(self, query: NamedQuery) -> QueryResult:
        params = query.params
        station_code: Optional[str] = params.get("station")
        lat: Optional[float] = params.get("lat")
        lon: Optional[float] = params.get("lon")
        start_time: Optional[datetime] = params.get("start_time")
        end_time: Optional[datetime] = params.get("end_time")
        time_offset_min: float = float(params.get("time_offset_minutes", 0.0))

        now_utc = datetime.now(timezone.utc)
        if start_time is None:
            start_time = now_utc - timedelta(hours=24)
        if end_time is None:
            end_time = now_utc

        if start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=timezone.utc)
        if end_time.tzinfo is None:
            end_time = end_time.replace(tzinfo=timezone.utc)

        if start_time > end_time:
            raise InvalidQueryParameterError(
                f"Query start_time ({start_time.isoformat()}) must be before end_time ({end_time.isoformat()})."
            )

        # MDK Bad-Weather check: cannot predict the future
        if end_time > now_utc:
            raise TemporalOutOfDomainError(
                f"MDK only provides historical sensor observations up to present ({now_utc.isoformat()}). "
                f"Requested interval extends into the future ({end_time.isoformat()})."
            )

        # Geographic resolution
        resolved_lat = lat
        resolved_lon = lon
        if station_code:
            target_station = station_code.upper()
            if target_station in ("OST", "OHM"):
                resolved_lat, resolved_lon = 51.2333, 2.9167
        elif lat is not None and lon is not None:
            station, dist_m = _find_nearest_station(lat, lon)
            if dist_m > BELGIAN_COASTAL_MAX_DISTANCE_M:
                raise GeographicOutOfDomainError(
                    lat=lat,
                    lon=lon,
                    provider="Meetnet Vlaamse Banken (MDK)",
                    max_distance_km=BELGIAN_COASTAL_MAX_DISTANCE_M / 1000.0,
                )
            target_station = "OHM" if station.code == "OST" else station.code
            resolved_lat = lat
            resolved_lon = lon
            if target_station in ("OST", "OHM") and lon > 2.95 and time_offset_min == 0.0:
                time_offset_min = 7.0
        else:
            target_station = "OHM"
            resolved_lat, resolved_lon = 51.2333, 2.9167

        df = self.manager.get_water_levels(
            stations=[target_station],
            start_time=start_time,
            end_time=end_time,
        )

        if time_offset_min != 0.0 and not df.empty:
            df["timestamp"] = df["timestamp"] + pd.Timedelta(minutes=time_offset_min)

        if not df.empty:
            df["lat"] = resolved_lat
            df["lon"] = resolved_lon
            df["station"] = "OST" if target_station == "OHM" else target_station
            df["source"] = "observed"
            result_df = df[["timestamp", "lat", "lon", "station", "water_level_m_taw", "source"]].reset_index(drop=True)
        else:
            result_df = pd.DataFrame(columns=["timestamp", "lat", "lon", "station", "water_level_m_taw", "source"])

        metadata = {
            "uri": URI_QUERY_TIDE,
            "provider": "mdk",
            "station": target_station,
            "target_lat": lat,
            "target_lon": lon,
            "effective_source": "observed",
            "time_offset_minutes": time_offset_min,
            "units": {"water_level_m_taw": "m TAW"},
        }
        return QueryResult(_df=result_df, metadata=metadata)


class BelgianTideBroker(AbstractDataBroker):
    """
    Overarching Composite Tide Broker for the Belgian Coast.
    
    Seamlessly orchestrates MDK (historical high-precision sensor observations)
    and HIC (operational hydrodynamic storm surge + tide forecasts).
    
    When a query window spans across 'now' (e.g. yesterday to tomorrow), it splits
    the query at current time, fetches historical sensor data for the past and
    operational forecast data for the future, and merges them into one continuous curve.
    """

    def __init__(
        self,
        hic_broker: Optional[HicTideBroker] = None,
        mdk_broker: Optional[MdkTideBroker] = None,
    ):
        self.hic_broker = hic_broker or HicTideBroker()
        self.mdk_broker = mdk_broker or MdkTideBroker()

    def named_query(self, uri: str = URI_QUERY_TIDE) -> NamedQuery:
        contract = resolve_query_contract(uri)
        if contract.uri != URI_QUERY_TIDE:
            raise ValueError(f"BelgianTideBroker only handles '{URI_QUERY_TIDE}', got '{uri}'")
        return NamedQuery(uri=contract.uri, contract=contract, broker=self)

    def _execute_query(self, query: NamedQuery) -> QueryResult:
        params = query.params
        lat: Optional[float] = params.get("lat")
        lon: Optional[float] = params.get("lon")
        start_time: Optional[datetime] = params.get("start_time")
        end_time: Optional[datetime] = params.get("end_time")
        source_param: str = str(params.get("source", "auto")).lower()

        now_utc = datetime.now(timezone.utc)
        if start_time is None:
            start_time = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        if end_time is None:
            end_time = start_time + timedelta(days=1)

        if start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=timezone.utc)
        if end_time.tzinfo is None:
            end_time = end_time.replace(tzinfo=timezone.utc)

        # 1. Bad-weather Parameter Validation
        if start_time > end_time:
            raise InvalidQueryParameterError(
                f"Query start_time ({start_time.isoformat()}) must be before end_time ({end_time.isoformat()})."
            )

        # 2. Bad-weather Geographic Domain Validation
        if lat is not None and lon is not None:
            station, dist_m = _find_nearest_station(lat, lon)
            if dist_m > BELGIAN_COASTAL_MAX_DISTANCE_M:
                raise GeographicOutOfDomainError(
                    lat=lat,
                    lon=lon,
                    provider="Belgian Coastal Tide System",
                    max_distance_km=BELGIAN_COASTAL_MAX_DISTANCE_M / 1000.0,
                )

        # 3. Explicit source routing
        if source_param == "forecast":
            return self.hic_broker.execute(query)
        elif source_param in ("observed", "historic"):
            return self.mdk_broker.execute(query)

        # 4. Automatic Composite Routing ('auto')
        # Scenario A: Entirely in the past
        if end_time <= now_utc:
            try:
                return self.mdk_broker.execute(query)
            except Exception as e:
                log.info(f"MDK observation query fallback to HIC observed: {e}")
                q_copy = NamedQuery(uri=query.uri, contract=query.contract, broker=self.hic_broker, params=dict(query.params))
                q_copy.params["source"] = "observed"
                return self.hic_broker.execute(q_copy)

        # Scenario B: Entirely in the future
        if start_time >= now_utc:
            q_copy = NamedQuery(uri=query.uri, contract=query.contract, broker=self.hic_broker, params=dict(query.params))
            q_copy.params["source"] = "forecast"
            return self.hic_broker.execute(q_copy)

        # Scenario C: Window spans across 'now' -> Composite Split & Merge!
        log.info(f"Composite tidal query spanning past and future across {now_utc.isoformat()}. Splitting...")

        # Past slice [start_time, now_utc]
        q_past = NamedQuery(uri=query.uri, contract=query.contract, broker=self, params=dict(query.params))
        q_past.params["start_time"] = start_time
        q_past.params["end_time"] = now_utc

        try:
            res_past = self.mdk_broker.execute(q_past)
        except Exception as e:
            log.info(f"MDK past slice query fallback to HIC: {e}")
            q_past_hic = NamedQuery(uri=query.uri, contract=query.contract, broker=self.hic_broker, params=dict(q_past.params))
            q_past_hic.params["source"] = "observed"
            res_past = self.hic_broker.execute(q_past_hic)

        # Future slice [now_utc, end_time]
        q_future = NamedQuery(uri=query.uri, contract=query.contract, broker=self.hic_broker, params=dict(query.params))
        q_future.params["start_time"] = now_utc
        q_future.params["end_time"] = end_time
        q_future.params["source"] = "forecast"
        res_future = self.hic_broker.execute(q_future)

        # Merge segments seamlessly
        df_past = res_past.data()
        df_future = res_future.data()

        merged_df = (
            pd.concat([df_past, df_future], ignore_index=True)
            .drop_duplicates(subset=["timestamp"])
            .sort_values("timestamp")
            .reset_index(drop=True)
        )

        metadata = {
            "uri": URI_QUERY_TIDE,
            "provider": "belgian_composite_tide",
            "composite": True,
            "split_pivot_time": now_utc.isoformat(),
            "segments": [
                {
                    "provider": res_past.metadata["provider"],
                    "source": res_past.metadata.get("effective_source", "observed"),
                    "start_time": start_time.isoformat(),
                    "end_time": now_utc.isoformat(),
                    "row_count": len(df_past),
                },
                {
                    "provider": res_future.metadata["provider"],
                    "source": res_future.metadata.get("effective_source", "forecast"),
                    "start_time": now_utc.isoformat(),
                    "end_time": end_time.isoformat(),
                    "row_count": len(df_future),
                },
            ],
            "units": {"water_level_m_taw": "m TAW"},
        }

        return QueryResult(_df=merged_df, metadata=metadata)