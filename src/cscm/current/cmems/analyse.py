# src/cscm/current/cmems/analyse.py

import json
import math
import warnings
from datetime import datetime, timezone
from pathlib import Path
from logging import getLogger

import numpy as np
import pandas as pd
import xarray as xr
import matplotlib
matplotlib.use('Agg')  # Headless mode for sandboxed environments
import matplotlib.pyplot as plt
from shapely.geometry import Point
from shapely.geometry.base import BaseGeometry

from cscm.model import Position

# Set up logging matching cscm logger standards
log = getLogger(__name__)

# Earth radius in km for coordinate distance calculations
EARTH_RADIUS_KM = 6371.0


def calculate_grid_principal_angles(ds: xr.Dataset) -> np.ndarray:
    """
    Computes the principal flow angle in radians for the entire 2D grid in one fast vectorised NumPy call.
    Aligns the angle to point Eastward (Oostwaartse Aligned) or Northward if purely vertical.
    """
    u = ds['uo'].values  # Shape: (time, lat, lon)
    v = ds['vo'].values  # Shape: (time, lat, lon)

    # Calculate means along time axis (axis 0)
    u_mean = np.nanmean(u, axis=0)
    v_mean = np.nanmean(v, axis=0)

    u_centered = u - u_mean
    v_centered = v - v_mean

    # Covariance components
    cuu = np.nanmean(u_centered * u_centered, axis=0)
    cvv = np.nanmean(v_centered * v_centered, axis=0)
    cuv = np.nanmean(u_centered * v_centered, axis=0)

    # Analytical principal angle of covariance tensor:
    # angle = 0.5 * arctan2(2 * cuv, cuu - cvv)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        angle_rad = 0.5 * np.arctan2(2.0 * cuv, cuu - cvv)

    cos_val = np.cos(angle_rad)
    sin_val = np.sin(angle_rad)

    # Aligns the major flow axis so that Vloed has a positive Eastward component (cos(angle_rad) > 0).
    # If cos is close to 0 (purely North-South), ensure positive Northward component (sin(angle_rad) > 0).
    flip_mask = (cos_val < 0) | (np.isclose(cos_val, 0) & (sin_val < 0))
    angle_rad = np.where(flip_mask, angle_rad + np.pi, angle_rad)

    return angle_rad % (2 * np.pi)


def classify_grid_cells(ds: xr.Dataset) -> tuple[np.ndarray, np.ndarray]:
    """
    Classifies each cell in the NetCDF grid as Land (0), Boundary (1), or Water (2).
    Land is defined as any cell where 'uo' is completely NaN or constant 0.
    Boundary is defined as any water cell adjacent (including diagonals) to a land cell.
    Water is a water cell with no adjacent land cells.
    Returns:
        status_mask: 2D array of ints (0: Land, 1: Boundary, 2: Water)
        is_boundary_mask: 2D array of bools (True for boundary cells)
    """
    u = ds['uo'].values  # Shape: (time, lat, lon)

    # Land check: any cell where all timesteps are NaN or 0.0
    is_nan = np.all(np.isnan(u), axis=0)
    is_zero = np.all(u == 0.0, axis=0)
    is_land = is_nan | is_zero

    num_lats, num_lons = is_land.shape
    status_mask = np.zeros((num_lats, num_lons), dtype=int)  # Default to 0 (Land)

    # Default all water cells to 2 (Water)
    status_mask[~is_land] = 2

    # Adjacency check for boundary cell classification
    for y in range(num_lats):
        for x in range(num_lons):
            if is_land[y, x]:
                continue

            # Check 8 neighbors (diagonals included)
            has_land_neighbor = False
            for dy in [-1, 0, 1]:
                for dx in [-1, 0, 1]:
                    if dy == 0 and dx == 0:
                        continue
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < num_lats and 0 <= nx < num_lons:
                        if is_land[ny, nx]:
                            has_land_neighbor = True
                            break
                    else:
                        # Out of grid bounds is considered a boundary limit
                        has_land_neighbor = True
                        break
                if has_land_neighbor:
                    break

            if has_land_neighbor:
                status_mask[y, x] = 1  # Boundary (grey)

    is_boundary_mask = (status_mask == 1)
    return status_mask, is_boundary_mask


def generate_gis_files(
    nc_path: Path,
    ds: xr.Dataset,
    status_mask: np.ndarray,
    lat_step: float,
    lon_step: float
) -> None:
    """
    Generates a stylized GeoJSON Polygon layer and a GPX Waypoints file representing the grid.
    Polygons are naturally colored (Land=Brown, Boundary=Grey, Water=Blue) with a strakke black border.
    """
    lat_coord = 'latitude' if 'latitude' in ds.coords else 'lat'
    lon_coord = 'longitude' if 'longitude' in ds.coords else 'lon'
    lats = ds[lat_coord].values
    lons = ds[lon_coord].values

    geojson_path = nc_path.parent / f"{nc_path.stem}_grid.geojson"
    gpx_path = nc_path.parent / f"{nc_path.stem}_grid.gpx"

    features = []
    gpx_wpts = []

    # Map styles for Land, Boundary, and Water
    styles = {
        0: {"name": "Land", "fill": "#8B4513", "gpx_sym": "Scenic Area"},
        1: {"name": "Boundary", "fill": "#808080", "gpx_sym": "Reference"},
        2: {"name": "Water", "fill": "#0000FF", "gpx_sym": "Water"}
    }

    half_lat = float(abs(lat_step)) / 2.0
    half_lon = float(abs(lon_step)) / 2.0

    for y_idx, lat in enumerate(lats):
        for x_idx, lon in enumerate(lons):
            lat_f = float(lat)
            lon_f = float(lon)
            status = int(status_mask[y_idx, x_idx])
            style = styles[status]

            # 1. GeoJSON Polygon element (converting numpy float32/64 to standard Python floats for JSON serialisation)
            coords = [
                [lon_f - half_lon, lat_f - half_lat],
                [lon_f + half_lon, lat_f - half_lat],
                [lon_f + half_lon, lat_f + half_lat],
                [lon_f - half_lon, lat_f + half_lat],
                [lon_f - half_lon, lat_f - half_lat]
            ]

            feature = {
                "type": "Feature",
                "properties": {
                    "cell_id": f"cell_{lat_f:.5f}_{lon_f:.5f}",
                    "status": style["name"],
                    "fill": style["fill"],
                    "stroke": "#000000",
                    "stroke-width": 1.5,
                    "fill-opacity": 0.45
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [coords]
                }
            }
            features.append(feature)

            # 2. GPX Waypoint element representing cell centroid
            wpt_name = f"[{style['name'][0]}] {lat_f:.4f}_{lon_f:.4f}"
            wpt_xml = f"""  <wpt lat='{lat_f:.5f}' lon='{lon_f:.5f}'>
    <name>{wpt_name}</name>
    <sym>{style['gpx_sym']}</sym>
    <type>{style['name']}</type>
  </wpt>"""
            gpx_wpts.append(wpt_xml)

    # Write GeoJSON
    geojson_collection = {
        "type": "FeatureCollection",
        "features": features
    }
    with open(geojson_path, "w") as f:
        json.dump(geojson_collection, f, indent=2)

    # Write GPX
    wpts_str = "\n".join(gpx_wpts)
    gpx_xml = f"""<?xml version='1.0' encoding='UTF-8'?>
<gpx version='1.1' creator='CSCM Grid Classifier'
     xmlns='http://www.topografix.com/GPX/1/1'>
  <metadata>
    <name>CSCM Tidal Analysis Grid Centroids</name>
    <desc>Grid classification for NetCDF: {nc_path.name}</desc>
  </metadata>
{wpts_str}
</gpx>"""
    with open(gpx_path, "w") as f:
        f.write(gpx_xml)

    log.info(f"Successfully generated grid files: {geojson_path.name} and {gpx_path.name}")


def project_to_principal_axis(u: np.ndarray, v: np.ndarray, angle_rad: float):
    """
    Projects eastward (u) and northward (v) velocities onto:
    1. Principal direction (along the major axis of the tidal ellipse)
    2. Orthogonal direction (along the minor axis of the tidal ellipse)
    """
    cos_a = np.cos(angle_rad)
    sin_a = np.sin(angle_rad)

    v_parallel = u * cos_a + v * sin_a
    v_perpendicular = -u * sin_a + v * cos_a
    return v_parallel, v_perpendicular


def find_zero_crossings(times: np.ndarray, values: np.ndarray):
    """
    Finds exact zero crossings in a time series using linear interpolation.
    Returns a list of dictionaries with interpolated time and transition direction.
    """
    crossings = []
    for i in range(len(values) - 1):
        v1, v2 = values[i], values[i+1]
        if np.isnan(v1) or np.isnan(v2):
            continue
        if v1 * v2 < 0:  # Zero crossing detected
            t1, t2 = pd.to_datetime(times[i]), pd.to_datetime(times[i+1])
            # Linear interpolation for zero crossing
            fraction = -v1 / (v2 - v1)
            t_zero = t1 + (t2 - t1) * fraction
            direction = 'neg_to_pos' if v2 > v1 else 'pos_to_neg'
            crossings.append({
                'time': t_zero,
                'index_pre': i,
                'direction': direction
            })
    return crossings


def get_bearing_deg(u: float, v: float) -> float:
    """
    Calculates the current bearing/direction in degrees True North (0-360).
    """
    bearing = math.degrees(math.atan2(u, v))
    return bearing % 360.0


def verify_grid_metadata(ds: xr.Dataset):
    """
    Verifies geographic grid size and temporal step in the NetCDF.
    Logs grid metrics and returns a dictionary of metadata.
    """
    lat_coord = 'latitude' if 'latitude' in ds.coords else 'lat'
    lon_coord = 'longitude' if 'longitude' in ds.coords else 'lon'

    lats = ds[lat_coord].values
    lons = ds[lon_coord].values
    times = ds['time'].values

    # Calculate step sizes
    d_lat = np.mean(np.diff(lats)) if len(lats) > 1 else 0.0
    d_lon = np.mean(np.diff(lons)) if len(lons) > 1 else 0.0

    # Calculate physical grid spacing (approx in km using Haversine)
    lat_spacing_km = d_lat * 111.0
    # Average latitude for longitude conversion
    avg_lat = np.mean(lats)
    lon_spacing_km = d_lon * 111.0 * math.cos(math.radians(avg_lat))

    # Calculate temporal step
    time_diffs = np.diff(times)
    avg_time_diff = np.mean(time_diffs) if len(times) > 1 else np.timedelta64(0, 's')
    time_step_min = float(avg_time_diff / np.timedelta64(1, 'm'))

    bbox = [float(np.min(lons)), float(np.max(lons)), float(np.min(lats)), float(np.max(lats))]

    metadata = {
        "num_lats": len(lats),
        "num_lons": len(lons),
        "lat_step_deg": float(d_lat),
        "lon_step_deg": float(d_lon),
        "lat_spacing_km": float(lat_spacing_km),
        "lon_spacing_km": float(lon_spacing_km),
        "time_step_minutes": float(time_step_min),
        "bbox": bbox,
        "total_time_steps": len(times)
    }

    log.info("--- Grid Verification ---")
    log.info(f"Lats: {len(lats)} steps (spacing approx {lat_spacing_km:.3f} km)")
    log.info(f"Lons: {len(lons)} steps (spacing approx {lon_spacing_km:.3f} km)")
    log.info(f"Time: {len(times)} steps (sampling interval {time_step_min:.2f} minutes)")
    log.info(f"BBox (min_lon, max_lon, min_lat, max_lat): {bbox}")
    log.info("-------------------------")
    return metadata


def get_cells_in_geometry(ds: xr.Dataset, geom: BaseGeometry) -> list:
    """
    Identifies grid cells that fall within a given Shapely geometry.
    Returns a list of tuples: (y_idx, x_idx, lat, lon)
    """
    lat_coord = 'latitude' if 'latitude' in ds.coords else 'lat'
    lon_coord = 'longitude' if 'longitude' in ds.coords else 'lon'

    lats = ds[lat_coord].values
    lons = ds[lon_coord].values

    matching_cells = []
    for y_idx, lat in enumerate(lats):
        for x_idx, lon in enumerate(lons):
            point = Point(lon, lat)
            if geom.contains(point):
                matching_cells.append((y_idx, x_idx, float(lat), float(lon)))

    return matching_cells


def get_moon_cycle_context_direct(
    t: datetime,
    nwmn_start_dt: datetime,
    nwmn_end_dt: datetime,
    lunarperiod_d: float,
    tidalperiod_h: float) -> dict:
    """
    Calculates the relative phase angle (0-360 deg) and offset in days for time 't'
    directly using the parameters of the enclosing new moon cycle from the catalog.
    """
    t_utc = t.astimezone(timezone.utc) if t.tzinfo else t.replace(tzinfo=timezone.utc)
    s_utc = nwmn_start_dt.astimezone(timezone.utc) if nwmn_start_dt.tzinfo else nwmn_start_dt.replace(tzinfo=timezone.utc)
    e_utc = nwmn_end_dt.astimezone(timezone.utc) if nwmn_end_dt.tzinfo else nwmn_end_dt.replace(tzinfo=timezone.utc)

    dt_s = (t_utc - s_utc).total_seconds()
    total_cycle_s = (e_utc - s_utc).total_seconds()

    # Lunar phase angle
    lunar_phase = (dt_s / total_cycle_s) * 360.0

    # Nominal tidal phase (cycles of exact tidalperiod_h)
    t_period_s = tidalperiod_h * 3600.0
    nominal_tidal_phase = ((dt_s % t_period_s) / t_period_s) * 360.0

    return {
        "lunar_phase_deg": float(lunar_phase % 360.0),
        "nominal_tidal_phase_deg": float(nominal_tidal_phase % 360.0),
        "offset_days": float(dt_s / 86400.0)
    }


def calculate_dynamic_tidal_phase(t: datetime, zero_crossings: list) -> float:
    """
    Calculates a self-normalizing, dynamic tidal phase angle (0-360 degrees).
    Eb-to-Vloed Slack starts at 0 deg, Max Vloed is at 90 deg,
    Vloed-to-Eb Slack is at 180 deg, Max Eb is at 270 deg.
    """
    t_utc = t.astimezone(timezone.utc) if t.tzinfo else t.replace(tzinfo=timezone.utc)

    # Find surrounding zero crossings
    cross_times = [c['time'].replace(tzinfo=timezone.utc) for c in zero_crossings]

    pre_crossing = None
    post_crossing = None

    for i in range(len(cross_times) - 1):
        if cross_times[i] <= t_utc <= cross_times[i+1]:
            pre_crossing = zero_crossings[i]
            post_crossing = zero_crossings[i+1]
            break

    if not pre_crossing or not post_crossing:
        return None

    t1 = pre_crossing['time'].replace(tzinfo=timezone.utc)
    t2 = post_crossing['time'].replace(tzinfo=timezone.utc)

    fraction = (t_utc - t1).total_seconds() / (t2 - t1).total_seconds()

    if pre_crossing['direction'] == 'neg_to_pos':
        # Crossing from Eb to Vloed (starts at 0, heads to 180)
        return float(fraction * 180.0)
    else:
        # Crossing from Vloed to Eb (starts at 180, heads to 360)
        return float(180.0 + fraction * 180.0)


def analyse_grid_cell(
    ds: xr.Dataset,
    y_idx: int,
    x_idx: int,
    principal_angle_rad: float,
    nwmn_start_dt: datetime,
    nwmn_end_dt: datetime,
    lunarperiod_d: float,
    tidalperiod_h: float) -> dict:
    """
    Processes the time series of a single grid cell adaptively.
    Projects currents onto the precalculated PCA principal flow axis.
    Extracts peak currents, reversals, amplitudes, bearings, and relative phases.
    Reduces memory size dramatically by only caching the top 6 (Spring) and bottom 6 (Neap) peaks.
    """
    times = ds['time'].values
    lat_coord = 'latitude' if 'latitude' in ds.coords else 'lat'
    lon_coord = 'longitude' if 'longitude' in ds.coords else 'lon'

    lat = float(ds[lat_coord][y_idx].values)
    lon = float(ds[lon_coord][x_idx].values)

    uo = ds['uo'][:, y_idx, x_idx].values
    vo = ds['vo'][:, y_idx, x_idx].values

    # Angle of the principal axis in degrees
    principal_angle_deg = (math.degrees(principal_angle_rad)) % 360.0

    # Project vectors onto cell's major and minor axes
    v_parallel, v_perpendicular = project_to_principal_axis(uo, vo, principal_angle_rad)

    # Find Slack Water zero crossings
    zero_crossings = find_zero_crossings(times, v_parallel)

    all_peaks = []
    # Process half-cycles between zero crossings
    for i in range(len(zero_crossings) - 1):
        idx_start = zero_crossings[i]['index_pre'] + 1
        idx_end = zero_crossings[i+1]['index_pre']

        if idx_end <= idx_start:
            continue

        # Find local maximum parallel velocity in this interval
        abs_v = np.abs(v_parallel[idx_start:idx_end+1])
        local_max_idx = idx_start + np.argmax(abs_v)

        peak_time_raw = pd.to_datetime(times[local_max_idx])
        if not peak_time_raw.tzinfo:
            peak_time_utc = peak_time_raw.replace(tzinfo=timezone.utc)
        else:
            peak_time_utc = peak_time_raw.astimezone(timezone.utc)

        amplitude = float(v_parallel[local_max_idx])
        u_peak = float(uo[local_max_idx])
        v_peak = float(vo[local_max_idx])

        bearing = get_bearing_deg(u_peak, v_peak)

        # Moon cycle offsets directly computed
        moon_ctx = get_moon_cycle_context_direct(peak_time_utc, nwmn_start_dt, nwmn_end_dt, lunarperiod_d, tidalperiod_h)

        # Dynamic tidal phase
        dynamic_phase = calculate_dynamic_tidal_phase(peak_time_utc, zero_crossings)

        all_peaks.append({
            "peak_time": peak_time_utc.isoformat(),
            "amplitude_mps": amplitude,
            "bearing_deg": bearing,
            "lunar_phase_deg": moon_ctx["lunar_phase_deg"],
            "nominal_tidal_phase_deg": moon_ctx["nominal_tidal_phase_deg"],
            "dynamic_tidal_phase_deg": dynamic_phase,
            "offset_days": moon_ctx["offset_days"]
        })

    # Neap/Spring envelope extreme analysis
    amplitudes = [abs(p["amplitude_mps"]) for p in all_peaks]
    max_max = float(np.max(amplitudes)) if amplitudes else 0.0
    min_max = float(np.min(amplitudes)) if amplitudes else 0.0

    # Sort peaks by absolute amplitude for data reduction
    sorted_peaks = sorted(all_peaks, key=lambda p: abs(p["amplitude_mps"]), reverse=True)
    spring_peaks = sorted_peaks[:6]  # 6 largest peaks (Spring tide proxies)
    neap_peaks = sorted_peaks[-6:] if len(sorted_peaks) >= 12 else sorted_peaks[6:]  # 6 smallest peaks (Neap tide proxies)

    # Put them back into chronological order
    spring_peaks = sorted(spring_peaks, key=lambda p: p["peak_time"])
    neap_peaks = sorted(neap_peaks, key=lambda p: p["peak_time"])

    return {
        "cell_id": f"cell_{lat:.5f}_{lon:.5f}",
        "latitude": lat,
        "longitude": lon,
        "grid_indices": [int(y_idx), int(x_idx)],
        "principal_flow_angle_deg": float(principal_angle_deg),
        "principal_flow_angle_rad": float(principal_angle_rad),
        "max_peak_mps": max_max,  # Spring tide proxy
        "min_peak_mps": min_max,  # Neap tide proxy
        "spring_peaks": spring_peaks,
        "neap_peaks": neap_peaks
    }


def find_first_peak_after(peaks_list: list, target_time: datetime) -> dict:
    """
    Finds the first positive flow peak (amplitude_mps > 0) chronologically after target_time.
    """
    target_utc = target_time.replace(tzinfo=timezone.utc) if target_time.tzinfo is None else target_time.astimezone(timezone.utc)
    chronological_peaks = sorted(peaks_list, key=lambda p: p["peak_time"])

    for p in chronological_peaks:
        peak_time = pd.to_datetime(p["peak_time"]).replace(tzinfo=timezone.utc)
        if peak_time >= target_utc and p["amplitude_mps"] > 0:
            return p

    # Fallback to any positive peak if none matches after
    for p in chronological_peaks:
        if p["amplitude_mps"] > 0:
            return p

    return None


def plot_cell_analysis(ds: xr.Dataset, y_idx: int, x_idx: int, cell_analytics: dict, output_path: Path):
    """
    Generates a high-quality dual-axis verification plot of tidal current velocities on the left axis,
    and current bearing on the right axis.
    Displays Vloed and Eb horizontal reference bearing lines.
    Saves plot as PNG.
    """
    times = pd.to_datetime(ds['time'].values)
    uo = ds['uo'][:, y_idx, x_idx].values
    vo = ds['vo'][:, y_idx, x_idx].values

    v_magnitude = np.sqrt(uo**2 + vo**2)
    angle_rad = cell_analytics["principal_flow_angle_rad"]
    v_parallel, v_perpendicular = project_to_principal_axis(uo, vo, angle_rad)

    # Calculate current direction/bearings over time
    bearings = [get_bearing_deg(u, v) if not (np.isnan(u) or np.isnan(v)) else np.nan for u, v in zip(uo, vo)]

    fig, ax1 = plt.subplots(figsize=(14, 6))

    # Left Axis: Velocities
    ax1.plot(times, v_magnitude, label=r"$|V|$", color="black", alpha=0.25, linewidth=1.1)
    ax1.plot(times, v_parallel, label=r"$V_{\parallel}$", color="royalblue", linewidth=1.7)
    ax1.plot(times, v_perpendicular, label=r"$V_{\perp}$", color="mediumseagreen", linestyle="--", alpha=0.55)
    ax1.set_ylabel("Velocity (m/s)", color="black", fontsize=10)
    ax1.tick_params(axis='y', labelcolor="black")

    # Right Axis: Bearings in degrees
    ax2 = ax1.twinx()
    ax2.scatter(times, bearings, label=r"$\alpha$", color="orange", s=2, alpha=0.4, zorder=1)
    ax2.set_ylabel("Direction (Degrees True North)", color="orange", fontsize=10)
    ax2.tick_params(axis='y', labelcolor="orange")
    ax2.set_ylim(0, 360)

    # Draw horizontal Flood/Eb reference bearing lines
    flood_angle = cell_analytics["principal_flow_angle_deg"]
    eb_angle = (flood_angle + 180) % 360

    ax2.axhline(flood_angle, color="orange", linestyle="-.", linewidth=0.8, alpha=0.5)
    ax2.axhline(eb_angle, color="darkgoldenrod", linestyle="-.", linewidth=0.8, alpha=0.5)

    # Add text labels on right-hand edge
    ax2.text(times[-1], flood_angle, f" {flood_angle:.1f}° Flood", color="orange", va="center", fontsize=8, ha="left")
    ax2.text(times[-1], eb_angle, f" {eb_angle:.1f}° Eb", color="darkgoldenrod", va="center", fontsize=8, ha="left")

    # Cycle markings dual anchors
    all_peaks = cell_analytics.get("spring_peaks", []) + cell_analytics.get("neap_peaks", [])
    begin_peak = cell_analytics.get("calibration", {}).get("begin_peak_ref")
    end_peak = cell_analytics.get("calibration", {}).get("end_peak_ref")

    if begin_peak:
        p1_time = pd.to_datetime(begin_peak["peak_time"])
        ax1.scatter(
            p1_time, begin_peak["amplitude_mps"], color="crimson", s=120, zorder=6, marker="o",
            label="Begin"
        )
        ax1.axvline(p1_time, color="crimson", linestyle="-.", alpha=0.45)

    if end_peak:
        p2_time = pd.to_datetime(end_peak["peak_time"])
        ax1.scatter(
            p2_time, end_peak["amplitude_mps"], color="crimson", s=120, zorder=6, marker="o",
            label="End"
        )
        ax1.axvline(p2_time, color="crimson", linestyle="-.", alpha=0.45)

    ax1.axhline(0, color="gray", linewidth=0.8, linestyle="-", alpha=0.4)

    # Plot title
    title_label = output_path.stem.split("_verify_cell_")[-1].replace("_", " ").title()
    plt.title(f"{title_label} [{cell_analytics['latitude']:.5f}N, {cell_analytics['longitude']:.5f}E]",
              fontsize=12, fontweight="bold")

    ax1.set_xlabel("Time (UTC)", fontsize=10)
    ax1.grid(True, linestyle="--", alpha=0.2)

    # Legende at the bottom center
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(
        lines1 + lines2, labels1 + labels2,
        loc="lower center",
        bbox_to_anchor=(0.5, -0.22),
        ncol=6,
        frameon=True,
        facecolor="white",
        edgecolor="none",
        fontsize=9
    )

    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()
    log.info(f"Visual verification plot saved to: {output_path.name}")


def process_nc_file(
    nc_path: Path,
    nwmn_start_dt: datetime,
    nwmn_end_dt: datetime,
    lunarperiod_d: float,
    tidalperiod_h: float,
    geom_to_filter: BaseGeometry = None,
    force_recalculate: bool = False,
    focal_positions: list[Position] = None):
    """
    Processes a Copernicus CMEMS NetCDF file, runs spatial and temporal analysis,
    checks caching to skip if up-to-date, applies land cell masking, and generates
    reduced size analysis JSON database companions and visual verification plots.
    """
    nc_path = Path(nc_path)
    out_json_path = nc_path.parent / f"{nc_path.stem}_analysis.json"
    metadata_path = nc_path.with_suffix(".json")

    # Caching check: Skip if up-to-date and force_recalculate is False
    if not force_recalculate and out_json_path.exists():
        nc_mtime = nc_path.stat().st_mtime
        meta_mtime = metadata_path.stat().st_mtime if metadata_path.exists() else 0
        analysis_mtime = out_json_path.stat().st_mtime
        if analysis_mtime > nc_mtime and analysis_mtime > meta_mtime:
            log.info(f"Skipping processing: {out_json_path.name} is newer than source NC and metadata.")
            return out_json_path

    log.info(f"Processing NetCDF: {nc_path.name}")
    ds = xr.open_dataset(nc_path)

    # 1. Grid Verification
    grid_meta = verify_grid_metadata(ds)

    # 2. Cell spatial classifications (Land/Boundary/Water mapping)
    status_mask, is_boundary_mask = classify_grid_cells(ds)

    # Generate GeoJSON Polygons and GPX Waypoints of centroids for style verification
    lat_coord = 'latitude' if 'latitude' in ds.coords else 'lat'
    lon_coord = 'longitude' if 'longitude' in ds.coords else 'lon'
    lats = ds[lat_coord].values
    lons = ds[lon_coord].values
    d_lat = np.mean(np.diff(lats)) if len(lats) > 1 else 0.01
    d_lon = np.mean(np.diff(lons)) if len(lons) > 1 else 0.02
    generate_gis_files(nc_path, ds, status_mask, d_lat, d_lon)

    # 3. Vectorised grid PCA computation (Oostwaartse Aligned)
    log.info("Pre-computing localized tidal ellipse principal axes using vectorised PCA...")
    principal_angles_rad = calculate_grid_principal_angles(ds)

    if geom_to_filter:
        log.info("Applying spatial filter geometry...")
        matching_cells = get_cells_in_geometry(ds, geom_to_filter)
        log.info(f"Found {len(matching_cells)} matching cells within geometry.")
    else:
        matching_cells = []
        for y_idx in range(len(lats)):
            for x_idx in range(len(lons)):
                matching_cells.append((y_idx, x_idx, float(lats[y_idx]), float(lons[x_idx])))

    # 4. Analyze Cells with land-masking and reduced JSON database compilation
    cells_analytics_rich = {}
    stripped_cells_analytics = {}
    skipped_land_cells = 0

    for y_idx, x_idx, lat, lon in matching_cells:
        # Check land status
        if status_mask[y_idx, x_idx] == 0:  # 0: Land
            skipped_land_cells += 1
            continue

        angle_rad = principal_angles_rad[y_idx, x_idx]
        cell_rich_data = analyse_grid_cell(
            ds, y_idx, x_idx, angle_rad, nwmn_start_dt, nwmn_end_dt, lunarperiod_d, tidalperiod_h
        )

        cell_id = cell_rich_data["cell_id"]
        cells_analytics_rich[cell_id] = cell_rich_data

        # Determine Begin/End Anchors for calibration
        spring_peaks = cell_rich_data.get("spring_peaks", [])
        neap_peaks = cell_rich_data.get("neap_peaks", [])
        all_peaks = spring_peaks + neap_peaks

        begin_peak = find_first_peak_after(all_peaks, nwmn_start_dt)
        end_peak = find_first_peak_after(all_peaks, nwmn_end_dt)

        if begin_peak and end_peak:
            t_begin = pd.to_datetime(begin_peak["peak_time"]).replace(tzinfo=timezone.utc)
            nwmn_start_utc = nwmn_start_dt.replace(tzinfo=timezone.utc)
            tidal_age_lag = (t_begin - nwmn_start_utc).total_seconds() / 86400.0

            # Cache peak details in rich data dictionary specifically for rendering on plot
            cell_rich_data["calibration"] = {
                "begin_peak_ref": begin_peak,
                "end_peak_ref": end_peak
            }

            # Stripped database representation (extreme size reduction > 99%)
            stripped_cells_analytics[cell_id] = {
                "cell_id": cell_id,
                "latitude": lat,
                "longitude": lon,
                "is_boundary": bool(is_boundary_mask[y_idx, x_idx]),
                "principal_flow_angle_deg": cell_rich_data["principal_flow_angle_deg"],
                "calibration": {
                    "begin_time": begin_peak["peak_time"],
                    "begin_amplitude_mps": begin_peak["amplitude_mps"],
                    "begin_lunar_phase_deg": begin_peak["lunar_phase_deg"],
                    "end_time": end_peak["peak_time"],
                    "end_amplitude_mps": end_peak["amplitude_mps"],
                    "end_lunar_phase_deg": end_peak["lunar_phase_deg"],
                    "tidal_age_lag_days": float(tidal_age_lag)
                }
            }
        else:
            # If anchors can't be resolved, skip from stripped database
            pass

    log.info(f"Processed {len(stripped_cells_analytics)} water/boundary cells.")

    output_meta = {
        "source_file": nc_path.name,
        "processed_at": datetime.now(timezone.utc).isoformat(),
        "grid_metadata": grid_meta,
        "num_cells": len(stripped_cells_analytics),
        "cells": stripped_cells_analytics
    }

    # Save output metadata
    with open(out_json_path, "w") as f:
        json.dump(output_meta, f, indent=2)

    log.info(f"Successfully processed and generated analytics JSON: {out_json_path.name}")

    # 5. Generate visual verification plot for selected focal coordinates
    # Filters out boundary shoreline/wet-dry grid cells from snaps pool to avoid wrijving distortion!
    if focal_positions and cells_analytics_rich:
        valid_cells = [c for c in stripped_cells_analytics.values() if not c["is_boundary"]]
        if not valid_cells:
            # Fallback to all water cells if no open water exists
            valid_cells = list(stripped_cells_analytics.values())

        valid_coords = np.array([[c["latitude"], c["longitude"]] for c in valid_cells])
        valid_ids = [c["cell_id"] for c in valid_cells]

        for f_pos in focal_positions:
            f_lat, f_lon = f_pos.lat, f_pos.lon

            # Find closest cell from strictly validated pool
            dist = (valid_coords[:, 0] - f_lat)**2 + (valid_coords[:, 1] - f_lon)**2
            closest_idx = np.argmin(dist)
            closest_cell_id = valid_ids[closest_idx]

            cell_data_rich = cells_analytics_rich[closest_cell_id]
            y_idx, x_idx = cell_data_rich["grid_indices"]

            # make as safe filename for plot - ensuring all spaces and weird characters are replaced
            pos_label = "".join(c if c.isalnum() or c in ('-', '_') else '_' for c in str(f_pos))
            plot_name = f"{nc_path.stem}_verify_cell_{pos_label}.png"
            plot_path = nc_path.parent / plot_name

            plot_cell_analysis(ds, y_idx, x_idx, cell_data_rich, plot_path)

    return out_json_path


def process_catalog(
    catalog: pd.DataFrame,
    *,
    geom_to_filter: BaseGeometry = None,
    force_recalculate: bool = False,
    focal_positions: list[Position] = None):
    """
    Helper function to process all NetCDF files listed in the CMEMSDataManager catalog
    using their specific astronomical metadata parameters.
    Processes files in chronological descending order (Newest -> Oldest) so the most recent data
    completes first if interrupted.
    """
    log.info(f"Batch processing {len(catalog)} files from catalog...")

    # Catalog sorting: Newest New Moon Start to Oldest New Moon Start
    catalog_sorted = catalog.sort_values(by="nwmn_start_dt", ascending=False)

    for idx, row in catalog_sorted.iterrows():
        # Resolve data file path
        data_file_name = row["data_file"]
        if not data_file_name:
            continue

        nc_path: Path = Path(data_file_name)
        if not nc_path.exists():
            log.warning(f"File listed in catalog does not exist on disk: {nc_path}")
            continue

        # Parse astronomical parameters
        nwmn_start = pd.to_datetime(row["nwmn_start_dt"])
        nwmn_end = pd.to_datetime(row["nwmn_end_dt"])
        lunarperiod_d = float(row["lunarperiod_d"])
        tidalperiod_h = float(row["tidalperiod_h"])

        process_nc_file(
            nc_path=nc_path,
            nwmn_start_dt=nwmn_start,
            nwmn_end_dt=nwmn_end,
            lunarperiod_d=lunarperiod_d,
            tidalperiod_h=tidalperiod_h,
            geom_to_filter=geom_to_filter,
            force_recalculate=force_recalculate,
            focal_positions=focal_positions
        )


if __name__ == "__main__":
    # Test script with dummy mock data
    import logging
    logging.basicConfig(level=logging.INFO)
    start_dt = datetime(2026, 8, 10, tzinfo=timezone.utc)
    end_dt = datetime(2026, 9, 8, tzinfo=timezone.utc)
    mock_nc = Path("/workspace/scratch/mock_tide.nc")
    if mock_nc.exists():
        koksijde_start = Position(51.11940, 2.62575)
        process_nc_file(
            nc_path=mock_nc,
            nwmn_start_dt=start_dt,
            nwmn_end_dt=end_dt,
            lunarperiod_d=29.53,
            tidalperiod_h=12.4206,
            force_recalculate=True,
            focal_positions=[koksijde_start]
        )
