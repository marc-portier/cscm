# src/cscm/simulation/predict.py

import json
import math
from datetime import datetime, timezone, timedelta
from pathlib import Path
from logging import getLogger
from typing import Optional, Union

import numpy as np
import pandas as pd
import xarray as xr
import matplotlib
matplotlib.use('Agg')  # Headless mode for sandboxed environments
import matplotlib.pyplot as plt
from shapely.geometry import Point, Polygon, MultiPolygon
import shapely.wkt

from cscm.model import Position
from cscm.current.cmems.analyse import project_to_principal_axis

# Set up logger
log = getLogger(__name__)


class CmemsForecastCurrentsModel:
    """
    Currents model that reads from a live forecast NetCDF dataset.
    Provides bilinear spatio-temporal interpolation for any given Position and timestamp.
    """

    def __init__(self, ds: xr.Dataset):
        self.ds = ds
        self.lat_col = 'latitude' if 'latitude' in ds.coords else 'lat'
        self.lon_col = 'longitude' if 'longitude' in ds.coords else 'lon'

    def get_current_vector(self, position: Position, moment: datetime) -> tuple[float, float]:
        """
        Calculates the interpolated currents vector (U_east, V_north) in m/s
        at the specified Position and timestamp.
        """
        moment_np = np.datetime64(moment.astimezone(timezone.utc).replace(tzinfo=None))

        # Check temporal bounding box
        times = self.ds['time'].values
        if moment_np < times[0] or moment_np > times[-1]:
            return 0.0, 0.0

        # Check spatial bounding box
        lats = self.ds[self.lat_col].values
        lons = self.ds[self.lon_col].values
        min_lat, max_lat = min(lats), max(lats)
        min_lon, max_lon = min(lons), max(lons)

        if not (min_lat <= position.lat <= max_lat) or not (min_lon <= position.lon <= max_lon):
            return 0.0, 0.0

        try:
            point_ds = self.ds.interp(
                {self.lat_col: position.lat, self.lon_col: position.lon, 'time': moment_np},
                method='linear'
            )
            u_val = float(point_ds['uo'].values)
            v_val = float(point_ds['vo'].values)

            # Safeguard against NaNs (near beach/land interpolation boundary)
            if np.isnan(u_val) or np.isnan(v_val):
                return 0.0, 0.0

            return u_val, v_val
        except Exception as e:
            log.warning(f"Interpolation failed at lat={position.lat}, lon={position.lon}: {e}")
            return 0.0, 0.0


def find_daily_tide_peaks(
    ds: xr.Dataset,
    focal_pos: Position,
    start_time: datetime,
    end_time: datetime
) -> list[dict]:
    """
    Finds the exact tidal current peaks (max Flood / PFC, and max Eb / PEC)
    near focal_pos within the specified start and end timestamps.
    Returns a list of dictionaries with timestamp, peak_type, and peak velocity.
    """
    lat_col = 'latitude' if 'latitude' in ds.coords else 'lat'
    lon_col = 'longitude' if 'longitude' in ds.coords else 'lon'
    lats = ds[lat_col].values
    lons = ds[lon_col].values
    times = ds['time'].values

    # Find closest active grid cell coordinates
    dist = (lats[:, np.newaxis] - focal_pos.lat)**2 + (lons[np.newaxis, :] - focal_pos.lon)**2
    y_idx, x_idx = np.unravel_index(np.argmin(dist), dist.shape)

    uo = ds['uo'][:, y_idx, x_idx].values
    vo = ds['vo'][:, y_idx, x_idx].values

    # Calculate local principal flow angle (Oostwaartse Aligned)
    u_clean = uo[~np.isnan(uo)]
    v_clean = vo[~np.isnan(vo)]
    if len(u_clean) < 2:
        log.error("Focal point is on hard land. Cannot resolve tide peaks.")
        return []

    cov = np.cov(u_clean, v_clean)
    eigenvalues, eigenvectors = np.linalg.eigh(cov)
    major_idx = np.argmax(eigenvalues)
    major_vector = eigenvectors[:, major_idx]
    angle_rad = np.arctan2(major_vector[1], major_vector[0])

    # Align \"Oostwaartse Vloed\"
    if np.cos(angle_rad) < 0 or (np.isclose(np.cos(angle_rad), 0) and np.sin(angle_rad) < 0):
        angle_rad += np.pi
    angle_rad = angle_rad % (2 * np.pi)

    # Project to find parallel velocity
    v_parallel, _ = project_to_principal_axis(uo, vo, angle_rad)

    # Identify all peak timings via local extrema on parallel velocity
    detected_peaks = []
    min_peak_threshold = 0.1  # 0.1 m/s threshold to bypass zero-velocity noise

    for t_idx in range(1, len(v_parallel) - 1):
        v_prev = v_parallel[t_idx - 1]
        v_curr = v_parallel[t_idx]
        v_next = v_parallel[t_idx + 1]

        if np.isnan(v_prev) or np.isnan(v_curr) or np.isnan(v_next):
            continue

        # Local Maximum (Max Flood -> PVS / PFC)
        if v_prev < v_curr > v_next and v_curr > min_peak_threshold:
            peak_time = pd.to_datetime(times[t_idx]).replace(tzinfo=timezone.utc)
            if start_time <= peak_time <= end_time:
                detected_peaks.append({
                    "time": peak_time,
                    "type": "PFC",  # Peak Flood Current (PVS)
                    "velocity_mps": v_curr
                })

        # Local Minimum (Max Eb -> PES / PEC)
        elif v_prev > v_curr < v_next and v_curr < -min_peak_threshold:
            peak_time = pd.to_datetime(times[t_idx]).replace(tzinfo=timezone.utc)
            if start_time <= peak_time <= end_time:
                detected_peaks.append({
                    "time": peak_time,
                    "type": "PEC",  # Peak Eb Current (PES)
                    "velocity_mps": v_curr
                })

    return detected_peaks


def simulate_test_swim(
    model: CmemsForecastCurrentsModel,
    start_pos: Position,
    start_time: datetime,
    heading_deg: float,
    duration_hours: float = 6.0,
    time_step_sec: int = 60
) -> pd.DataFrame:
    """
    Simulates a 6-hour test swim with constant heading and swimmer speed (1 m/s),
    incorporating live CMEMS currents velocity.
    Returns a pandas DataFrame of the trajectory (timestamp, lat, lon, u_current, v_current).
    """
    current_pos = Position(start_pos.lat, start_pos.lon)
    current_time = start_time
    duration_sec = int(duration_hours * 3600.0)

    trajectory = []
    heading_rad = math.radians(heading_deg)

    # Swimmer intrinsic speed: 1.0 m/s (from wellknown SWIMMERS)
    v_swimmer_east = 1.0 * math.sin(heading_rad)
    v_swimmer_north = 1.0 * math.cos(heading_rad)

    # Step-by-step vector addition integration
    for elapsed in range(0, duration_sec + time_step_sec, time_step_sec):
        u_c, v_c = model.get_current_vector(current_pos, current_time)

        trajectory.append({
            "time": current_time.isoformat(),
            "lat": current_pos.lat,
            "lon": current_pos.lon,
            "u_current": u_c,
            "v_current": v_c,
            "v_magnitude": math.sqrt(u_c**2 + v_c**2)
        })

        if elapsed >= duration_sec:
            break

        # Combined movement components
        v_eff_east = v_swimmer_east + u_c
        v_eff_north = v_swimmer_north + v_c

        # WGS84 degree offsets
        delta_lat = v_eff_north * time_step_sec / 111132.0
        delta_lon = v_eff_east * time_step_sec / (111132.0 * math.cos(math.radians(current_pos.lat)))

        current_pos = Position(current_pos.lat + delta_lat, current_pos.lon + delta_lon)
        current_time += timedelta(seconds=time_step_sec)

    return pd.DataFrame(trajectory)


def write_gpx_track(df: pd.DataFrame, track_name: str, output_path: Path) -> None:
    """
    Saves the trajectory DataFrame into a standard GPX 1.1 XML track file.
    """
    gpx_pts = []
    for _, row in df.iterrows():
        gpx_pts.append(
            f"      <trkpt lat='{row['lat']:.6f}' lon='{row['lon']:.6f}'>\n"
            f"        <time>{row['time']}</time>\n"
            f"      </trkpt>"
        )

    gpx_pts_str = "\n".join(gpx_pts)
    gpx_xml = f"""<?xml version='1.0' encoding='UTF-8'?>
<gpx version='1.1' creator='CSCM Trajectory Generator'
     xmlns='http://www.topografix.com/GPX/1/1'>
  <metadata>
    <name>{track_name}</name>
    <desc>Simulated 6h Coast Swim Track from Koksijde</desc>
  </metadata>
  <trk>
    <name>{track_name}</name>
    <trkseg>
{gpx_pts_str}
    </trkseg>
  </trk>
</gpx>"""

    with open(output_path, "w") as f:
        f.write(gpx_xml)


def plot_daily_simulations(
    df_list: list[tuple[pd.DataFrame, str, datetime]],
    day_label: str,
    output_path: Path,
    status_mask: np.ndarray,
    lats: np.ndarray,
    lons: np.ndarray,
    mussel_farm_wkt: Optional[str] = None,
    coastline_wkt_path: Optional[Path] = None,
    obstructions_wkt_path: Optional[Path] = None
) -> None:
    """
    Generates a beautiful daily map plot showing the 4 test swim trajectories
    overlaid on the model's grid coastline contour and Colruyt mussel farm.
    Auto-zooms to the bounding box of the trajectories + 500m outset buffer.
    """
    plt.figure(figsize=(11, 10))

    # Calculate trajectories bounding box
    all_lats = []
    all_lons = []
    for df, _, _ in df_list:
        all_lats.extend(df['lat'].values)
        all_lons.extend(df['lon'].values)

    min_lat, max_lat = min(all_lats), max(all_lats)
    min_lon, max_lon = min(all_lons), max(all_lons)

    # Outset buffer of 500m (approx 0.005 degrees latitude/longitude)
    buffer_deg = 0.005
    map_min_lat = min_lat - buffer_deg
    map_max_lat = max_lat + buffer_deg
    map_min_lon = min_lon - buffer_deg
    map_max_lon = max_lon + buffer_deg

    # 1. Background Grid Plotting
    # Status levels: 0: Land (brown), 1: Boundary (grey), 2: Water (blue)
    cmap = matplotlib.colors.ListedColormap(['#8B4513', '#C0C0C0', '#E0F7FA'])
    plt.pcolormesh(lons, lats, status_mask, cmap=cmap, shading='auto', alpha=0.15, zorder=1)
    plt.contour(lons, lats, status_mask, levels=[0.5, 1.5], colors='black', linewidths=0.5, alpha=0.3, zorder=2)

    # 2. Vloeiende Kustlijn WKT Plotting
    if coastline_wkt_path and coastline_wkt_path.exists():
        try:
            coast_df = pd.read_csv(coastline_wkt_path)
            for _, row in coast_df.iterrows():
                geom_str = row.get("WKT") or row.get("wkt")
                if geom_str:
                    geom = shapely.wkt.loads(geom_str)
                    if isinstance(geom, (Polygon, MultiPolygon)):
                        # Draw Polygon fill and stroke
                        if isinstance(geom, Polygon):
                            polys = [geom]
                        else:
                            polys = geom.geoms

                        for poly in polys:
                            x, y = poly.exterior.xy
                            plt.fill(x, y, color='#8B4513', alpha=0.45, zorder=3)
                            plt.plot(x, y, color='black', linewidth=1.2, zorder=4)
                    else:
                        # Draw Linestring stroke
                        x, y = geom.xy
                        plt.plot(x, y, color='black', linewidth=1.5, zorder=4)
            log.info(f"Successfully rendered custom coastline from: {coastline_wkt_path.name}")
        except Exception as e:
            log.warning(f"Could not load custom coastline WKT: {e}")

    # 3. Obstructions WKT Plotting (from File or Default Mussel Farm)
    has_custom_obstructions = False
    if obstructions_wkt_path and obstructions_wkt_path.exists():
        try:
            obs_df = pd.read_csv(obstructions_wkt_path)
            for idx, row in obs_df.iterrows():
                geom_str = row.get("WKT") or row.get("wkt")
                name = row.get("name", f"Obstruction_{idx}")
                if geom_str:
                    geom = shapely.wkt.loads(geom_str)
                    if isinstance(geom, (Polygon, MultiPolygon)):
                        if isinstance(geom, Polygon):
                            polys = [geom]
                        else:
                            polys = geom.geoms
                        for poly in polys:
                            x, y = poly.exterior.xy
                            plt.fill(x, y, color='crimson', alpha=0.35, hatch='//', edgecolor='crimson',
                                     linewidth=1.2, label=name if not has_custom_obstructions else "", zorder=5)
                            has_custom_obstructions = True
            log.info(f"Rendered custom obstructions from: {obstructions_wkt_path.name}")
        except Exception as e:
            log.warning(f"Failed to render custom obstructions CSV: {e}")

    # 4. Trajectory Plotting
    styles = {
        "PFC": {"color": "royalblue", "label": "PVS (Vloed)"},
        "PEC": {"color": "forestgreen", "label": "PES (Eb)"}
    }

    for idx, (df, tide_type, start_dt) in enumerate(df_list):
        style = styles.get(tide_type, {"color": "gray", "label": tide_type})
        line_style = "-" if idx % 2 == 0 else "--"

        # Display time in CEST (local time window)
        local_time_str = start_dt.strftime('%H:%M')
        label = f"{style['label']} ({local_time_str} CEST, max {df.iloc[-1]['v_magnitude']:.2f} m/s)"

        plt.plot(df['lon'], df['lat'], color=style["color"], linestyle=line_style,
                 linewidth=2.2, label=label, zorder=6)

        # Swimmer's path vector direction annotation arrow
        mid_idx = len(df) // 2
        plt.annotate("", xy=(df.iloc[mid_idx+1]['lon'], df.iloc[mid_idx+1]['lat']),
                     xytext=(df.iloc[mid_idx]['lon'], df.iloc[mid_idx]['lat']),
                     arrowprops=dict(arrowstyle="->", color=style["color"], lw=2.2), zorder=7)

    # Plot Koksijde start point marker (Gold Star)
    plt.scatter(2.62575, 51.11940, color='gold', edgecolor='black', s=200, marker='*',
                label="Koksijde Start Post 4", zorder=8)

    # Focus map limits tightly on the berekende trajectories window + 500m buffer
    plt.xlim(map_min_lon, map_max_lon)
    plt.ylim(map_min_lat, map_max_lat)

    plt.grid(True, linestyle=":", alpha=0.4)
    plt.xlabel("Longitude (°E)", fontsize=10)
    plt.ylabel("Latitude (°N)", fontsize=10)

    plt.title(f"CSCM Test Swim Trajectory Predictions - {day_label}\n"
              f"Swimmer Speed: 1.0 m/s | 6h Constant Course (PFC=316° N / PEC=333° N)",
              fontsize=12, fontweight='bold')

    plt.legend(loc="upper left", frameon=True, facecolor="white", edgecolor="none", fontsize=9)
    plt.tight_layout()

    plt.savefig(output_path, dpi=150)
    plt.close()
    log.info(f"Daily predictions PNG saved to: {output_path.name}")
