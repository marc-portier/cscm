"""
Universal Data Access Layer (UDAL) - CMEMS Current Domain Broker.

Dedicated broker handling 'urn:cscm:query:current' queries via CmemsCurrentManager.
"""

from datetime import datetime, timezone, timedelta
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd
import xarray as xr

from cscm.broker.base import AbstractDataBroker, NamedQuery, QueryResult
from cscm.broker.catalogue import URI_QUERY_CURRENT, resolve_query_contract
from cscm.broker.exceptions import (
    GeographicOutOfDomainError,
    InvalidQueryParameterError,
    TemporalOutOfDomainError,
)
from cscm.current.cmems.analyse import classify_grid_cells
from cscm.current.cmems.retrieve import CmemsCurrentManager

log = logging.getLogger(__name__)


class CmemsCurrentBroker(AbstractDataBroker):
    """
    Domain broker handling hydrodynamic current queries against Copernicus CMEMS data store.
    """

    def __init__(self, manager: Optional[CmemsCurrentManager] = None):
        self.manager = manager or CmemsCurrentManager()

    def named_query(self, uri: str = URI_QUERY_CURRENT) -> NamedQuery:
        """Instantiate a NamedQuery builder bound to this broker."""
        contract = resolve_query_contract(uri)
        if contract.uri != URI_QUERY_CURRENT:
            raise ValueError(f"CmemsCurrentBroker only handles '{URI_QUERY_CURRENT}', got '{uri}'")
        return NamedQuery(uri=contract.uri, contract=contract, broker=self)

    def _execute_query(self, query: NamedQuery) -> QueryResult:
        """Executes current query against CMEMS data store."""
        params = query.params
        start_time: Optional[datetime] = params.get("start_time")
        end_time: Optional[datetime] = params.get("end_time")
        lat: Optional[float] = params.get("lat")
        lon: Optional[float] = params.get("lon")
        positions: Optional[List[Tuple[float, float]]] = params.get("positions")
        avoid_damping: bool = params.get("avoid_boundary_damping", True)

        now_utc = datetime.now(timezone.utc)
        if start_time is None:
            start_time = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        if end_time is None:
            end_time = start_time + timedelta(days=1)

        if start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=timezone.utc)
        if end_time.tzinfo is None:
            end_time = end_time.replace(tzinfo=timezone.utc)

        # Validation: Bad-weather checks
        if start_time > end_time:
            raise InvalidQueryParameterError(
                f"Query start_time ({start_time.isoformat()}) must be before end_time ({end_time.isoformat()})."
            )

        if start_time > now_utc + timedelta(days=7):
            raise TemporalOutOfDomainError(
                f"Requested start_time ({start_time.isoformat()}) is beyond the 6-day Copernicus CMEMS forecast horizon."
            )

        # Geographic bounds validation for CMEMS NW European Shelf 1.5km model
        check_coords = positions or ([(lat, lon)] if (lat is not None and lon is not None) else [])
        for c_lat, c_lon in check_coords:
            if not (48.0 <= c_lat <= 58.0 and -5.0 <= c_lon <= 10.0):
                raise GeographicOutOfDomainError(
                    lat=c_lat,
                    lon=c_lon,
                    provider="CMEMS NW European Shelf 1.5km model",
                    max_distance_km=500.0,
                )

        # 1. Resolve covering NetCDF file
        covering = self.manager.find_covering_files(start_time, end_time)
        target_file: Optional[Path] = None

        if covering:
            covering.sort(key=lambda e: e.retrieved_at, reverse=True)
            target_file = self.manager.data_folder / covering[0].file_name
        else:
            catalog = self.manager.get_catalog()
            overlapping = [e for e in catalog if e.overlaps(start_time, end_time)]
            if overlapping:
                overlapping.sort(key=lambda e: e.retrieved_at, reverse=True)
                target_file = self.manager.data_folder / overlapping[0].file_name

        if target_file is None or not target_file.exists():
            log.info(f"No cached CMEMS file covering [{start_time}, {end_time}]. Triggering retrieval...")
            self.manager.retrieve(start_date=start_time, end_date=end_time, limit=1)
            covering = self.manager.find_covering_files(start_time, end_time)
            if covering:
                target_file = self.manager.data_folder / covering[0].file_name
            else:
                nc_files = sorted(self.manager.data_folder.glob("*.nc"))
                if not nc_files:
                    raise RuntimeError(f"No CMEMS NetCDF files available in {self.manager.data_folder}")
                target_file = nc_files[-1]

        # 2. Extract currents from NetCDF
        with xr.open_dataset(target_file) as ds:
            lats = ds["latitude"].values
            lons = ds["longitude"].values
            status_mask, _ = classify_grid_cells(ds)

            # Determine query points
            target_coords: List[Tuple[float, float]] = []
            if positions:
                target_coords = positions
            elif lat is not None and lon is not None:
                target_coords = [(lat, lon)]
            else:
                target_coords = [(float(lats[len(lats) // 2]), float(lons[len(lons) // 2]))]

            dfs = []
            grid_metadata = []

            for t_lat, t_lon in target_coords:
                lon_2d, lat_2d = np.meshgrid(lons, lats)
                d_lat = (lat_2d - t_lat) * 111320.0
                d_lon = (lon_2d - t_lon) * 111320.0 * np.cos(np.radians(t_lat))
                dist = np.hypot(d_lat, d_lon)

                if avoid_damping and np.any(status_mask == 2):
                    dist_filtered = np.where(status_mask == 2, dist, np.inf)
                elif np.any(status_mask > 0):
                    dist_filtered = np.where(status_mask > 0, dist, np.inf)
                else:
                    dist_filtered = dist

                y_idx, x_idx = np.unravel_index(np.argmin(dist_filtered), dist_filtered.shape)
                cell_lat = float(lats[y_idx])
                cell_lon = float(lons[x_idx])
                distance_m = float(dist[y_idx, x_idx])
                cell_status = int(status_mask[y_idx, x_idx])

                ds_point = ds.isel(latitude=y_idx, longitude=x_idx)
                times = pd.to_datetime(ds_point["time"].values, utc=True)
                mask = (times >= start_time) & (times <= end_time)

                times_filtered = times[mask]
                u_vals = ds_point["uo"].values[mask]
                v_vals = ds_point["vo"].values[mask]

                speed_vals = np.hypot(u_vals, v_vals)
                dir_vals = (np.degrees(np.arctan2(u_vals, v_vals)) + 360.0) % 360.0

                sub_df = pd.DataFrame({
                    "timestamp": times_filtered,
                    "lat": cell_lat,
                    "lon": cell_lon,
                    "current_speed_eastward_m_s": u_vals,
                    "current_speed_northward_m_s": v_vals,
                    "current_speed_m_s": speed_vals,
                    "current_direction_deg": dir_vals,
                })
                dfs.append(sub_df)
                grid_metadata.append({
                    "target_lat": t_lat,
                    "target_lon": t_lon,
                    "selected_lat": cell_lat,
                    "selected_lon": cell_lon,
                    "distance_to_target_m": distance_m,
                    "cell_status": cell_status,
                })

            combined_df = pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()

            metadata = {
                "uri": URI_QUERY_CURRENT,
                "provider": "cmems",
                "source_file": target_file.name,
                "avoid_boundary_damping": avoid_damping,
                "points_queried": len(target_coords),
                "grid_points": grid_metadata if len(grid_metadata) > 1 else grid_metadata[0],
                "units": {
                    "current_speed_eastward_m_s": "m/s",
                    "current_speed_northward_m_s": "m/s",
                    "current_speed_m_s": "m/s",
                    "current_direction_deg": "degrees from True North",
                },
            }

            return QueryResult(_df=combined_df, metadata=metadata)
