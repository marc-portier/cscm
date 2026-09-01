"""
Support for analysis of Copernicus CMEMS data.
Fully adaptive spatial analysis using localized tidal ellipse principal axes (PCA),
incremental processing (caching), visual verification plotting, and direct catalog integration.
This script provides tools to analyze ocean currents, verify NetCDF grid parameters,
detect peak flow timings, compute offsets relative to lunar/tidal cycles, and filter
cells based on spatial geometries.
"""

import numpy as np
import pandas as pd
import xarray as xr
import matplotlib
matplotlib.use('Agg')  # Headless mode for sandboxed environments
import matplotlib.pyplot as plt
from datetime import datetime, timezone
from shapely.geometry import Point
from shapely.geometry.base import BaseGeometry
import json
import math
from pathlib import Path
from logging import getLogger
from cscm.model import Position


# Set up logging matching cscm logger standards
log = getLogger(__name__)

# Earth radius in km for coordinate distance calculations
EARTH_RADIUS_KM = 6371.0


def calculate_principal_axis(u: np.ndarray, v: np.ndarray) -> float:
    """
    Computes the principal axis of a 2D vector series (u, v) using covariance PCA.
    Returns the angle in radians of the dominant flow axis (major axis of the tidal ellipse).
    Aligns the axis to point Eastward (or Northward if purely vertical).
    """
    # Filter out NaNs
    mask = ~np.isnan(u) & ~np.isnan(v)
    u_clean = u[mask]
    v_clean = v[mask]

    if len(u_clean) < 2:
        return 0.0  # Default to East

    cov = np.cov(u_clean, v_clean)
    if cov.shape != (2, 2) or np.all(cov == 0):
        return 0.0

    eigenvalues, eigenvectors = np.linalg.eigh(cov)
    # The major axis corresponds to the largest eigenvalue
    major_idx = np.argmax(eigenvalues)
    major_vector = eigenvectors[:, major_idx]

    # Angle of the principal axis in radians
    angle_rad = np.arctan2(major_vector[1], major_vector[0])

    # "Oostwaartse Vloed" alignment rule:
    # Tide, as time, flows to the east, forced by the spinning Earth, moving under the tidal bulge.
    # Therefore, the principal axis should be oriented such that the Eastward component is positive.
    # Ensure the projection axis always has a positive Eastward component (cos(angle_rad) > 0).
    # If it is purely North-South, align it with a positive Northward component (sin(angle_rad) > 0).
    cos_val = np.cos(angle_rad)
    if cos_val < 0 or (np.isclose(cos_val, 0) and np.sin(angle_rad) < 0):
        angle_rad += np.pi

    return float(angle_rad % (2 * np.pi))


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

    dt_s: float = (t_utc - s_utc).total_seconds()
    total_cycle_s = (e_utc - s_utc).total_seconds()

    # Lunar phase angle
    lunar_phase = (dt_s / total_cycle_s) * 360.0

    # Nominal tidal phase (cycles of exact tidalperiod_h)
    t_period_s = tidalperiod_h * 3600.0
    nominal_tidal_phase = ((dt_s % t_period_s) / t_period_s) * 360.0

    return {
        "lunar_phase_deg": float(lunar_phase % 360.0),
        "nominal_tidal_phase_deg": float(nominal_tidal_phase % 360.0),
        "offset_days": float(dt_s / 86400.0),
        "offset_seconds": float(dt_s)
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
        nwmn_start_dt: datetime,
        nwmn_end_dt: datetime,
        lunarperiod_d: float,
        tidalperiod_h: float) -> dict:
    """
    Processes the time series of a single grid cell adaptively.
    Computes cell-specific principal tidal ellipse axis and projects currents onto it.
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

    # Compute principal axis of flow for this specific grid cell using PCA
    principal_angle_rad = calculate_principal_axis(uo, vo)
    principal_angle_deg = (math.degrees(principal_angle_rad)) % 360.0

    # Project vectors onto cell's major and minor tidal axes
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


def plot_cell_analysis(ds: xr.Dataset, y_idx: int, x_idx: int, cell_analytics: dict, output_path: Path):
    """
    Generates a high-quality dual-axis verification plot of tidal current velocities (Pythagoras magnitude,
    major parallel flow axis, minor transverse axis) on the left axis, and current bearing on the right axis.
    Displays the maximum spring tide peak timing. Saves plot as PNG.
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

    # Plot velocities on left Y axis
    ax1.plot(times, v_magnitude, label="Nominal Speed (Magnitude)", color="black", alpha=0.3, linewidth=1.2)
    ax1.plot(times, v_parallel, label="Major Flow Speed (Projected Parallel)", color="royalblue", linewidth=1.8)
    ax1.plot(times, v_perpendicular, label="Minor Flow Speed (Orthogonal Transverse)", color="mediumseagreen", linewidth=1.2)
    ax1.set_ylabel("Velocity (m/s)", color="black", fontsize=10)
    ax1.tick_params(axis='y', labelcolor="black")

    # Plot current bearings on right Y axis
    ax2 = ax1.twinx()
    ax2.scatter(times, bearings, label="Current Direction (Bearing)", color="orange", s=3, alpha=0.5, zorder=1)
    ax2.set_ylabel("Direction (Degrees True North)", color="orange", fontsize=10)
    ax2.tick_params(axis='y', labelcolor="orange")
    ax2.set_ylim(0, 360)

    # Highlight the absolute largest Spring Tide peak
    spring_peaks = cell_analytics.get("spring_peaks", [])
    if spring_peaks:
        largest_peak = max(spring_peaks, key=lambda p: abs(p["amplitude_mps"]))
        peak_time = pd.to_datetime(largest_peak["peak_time"])
        ax1.scatter(peak_time, largest_peak["amplitude_mps"], color="crimson", s=100, zorder=6, marker="o", 
                    label=f"Max Spring Peak ({largest_peak['amplitude_mps']:.2f} m/s)")
        ax1.axvline(peak_time, color="crimson", linestyle="-.", alpha=0.4, label="Spring Peak Alignment Marker")

    ax1.axhline(0, color="gray", linewidth=0.8, linestyle="-", alpha=0.5)

    plt.title(f"Adaptive Tidal Profile - Cell [{cell_analytics['latitude']:.5f}N, {cell_analytics['longitude']:.5f}E]\n"
              f"Principal Flow Axis: {cell_analytics['principal_flow_angle_deg']:.1f}° True North",
              fontsize=12, fontweight="bold")
    ax1.set_xlabel("Time (UTC)", fontsize=10)
    ax1.grid(True, linestyle="--", alpha=0.3)

    # Combine legend curves
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper right", frameon=True, facecolor="white", edgecolor="none")

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

    # 2. Geometry Filter or cell compilation
    lat_coord = 'latitude' if 'latitude' in ds.coords else 'lat'
    lon_coord = 'longitude' if 'longitude' in ds.coords else 'lon'
    lats = ds[lat_coord].values
    lons = ds[lon_coord].values

    if geom_to_filter:
        log.info("Applying spatial filter geometry...")
        matching_cells = get_cells_in_geometry(ds, geom_to_filter)
        log.info(f"Found {len(matching_cells)} matching cells within geometry.")
    else:
        matching_cells = []
        for y_idx in range(len(lats)):
            for x_idx in range(len(lons)):
                matching_cells.append((y_idx, x_idx, float(lats[y_idx]), float(lons[x_idx])))

    # 3. Analyze Cells with land-masking
    cells_analytics = {}
    skipped_land_cells = 0
    for y_idx, x_idx, lat, lon in matching_cells:
        uo = ds['uo'][:, y_idx, x_idx].values
        vo = ds['vo'][:, y_idx, x_idx].values

        # Fast land-masking check: skip cell if all values are NaN or constant zeros
        if np.all(np.isnan(uo)) or np.all(uo == 0.0) or np.all(np.isnan(vo)) or np.all(vo == 0.0):
            skipped_land_cells += 1
            continue

        cell_data = analyse_grid_cell(ds, y_idx, x_idx, nwmn_start_dt, nwmn_end_dt, lunarperiod_d, tidalperiod_h)

        # Skip static dry cells with negligible tidal currents (noise threshold < 0.01 m/s)
        if cell_data["max_peak_mps"] < 0.01:
            skipped_land_cells += 1
            continue

        cells_analytics[cell_data["cell_id"]] = cell_data

    log.info(f"Land masking completed: analyzed {len(cells_analytics)} water cells, skipped {skipped_land_cells} dry/static cells.")

    output_meta = {
        "source_file": nc_path.name,
        "processed_at": datetime.now(timezone.utc).isoformat(),
        "grid_metadata": grid_meta,
        "num_cells": len(cells_analytics),
        "skipped_land_cells": skipped_land_cells,
        "cells": cells_analytics
    }

    # Save output metadata
    with open(out_json_path, "w") as f:
        json.dump(output_meta, f, indent=2)

    log.info(f"Successfully processed and generated analytics JSON: {out_json_path.name}")

    # 4. Generate visual verification plot for selected focal coordinates
    if focal_positions:
        for f_idx, f_pos in enumerate(focal_positions):
            f_lat, f_lon = f_pos.lat, f_pos.lon
            f_name: str = str(f_pos.name) if f_pos.name else f"focal_{f_idx+1}"
            f_name_safe: str = f_name.replace(" ", "_").lower()
            # Find closest grid indices
            dist = (lats[:, np.newaxis] - f_lat)**2 + (lons[np.newaxis, :] - f_lon)**2
            y_idx, x_idx = np.unravel_index(np.argmin(dist), dist.shape)
            closest_lat, closest_lon = float(lats[y_idx]), float(lons[x_idx])
            cell_id = f"cell_{closest_lat:.5f}_{closest_lon:.5f}"

            # Retrieve from cache if water cell, otherwise generate on-the-fly specifically for the plot!
            if cell_id in cells_analytics:
                plot_name = f"{nc_path.stem}_verify_cell_{f_name_safe}.png"
                plot_path = nc_path.parent / plot_name
                plot_cell_analysis(ds, y_idx, x_idx, cells_analytics[cell_id], plot_path)
            else:
                log.info(f"Focal position {f_pos.name} closest cell {cell_id} was filtered as land/static. Calculating specifically for visual diagnostic...")
                try:
                    cell_data_for_plot = analyse_grid_cell(ds, y_idx, x_idx, nwmn_start_dt, nwmn_end_dt, lunarperiod_d, tidalperiod_h)
                    plot_name = f"{nc_path.stem}_verify_cell_{f_name_safe}.png"
                    plot_path = nc_path.parent / plot_name
                    plot_cell_analysis(ds, y_idx, x_idx, cell_data_for_plot, plot_path)
                except Exception as e:
                    log.warning(f"Could not generate visual verification plot for focal position {f_pos.name}: {e}")

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


# worskapce scratch test script for local development and verification
if __name__ == "__main__":
    # Test script with dummy mock data
    import logging
    logging.basicConfig(level=logging.INFO)
    start_dt = datetime(2026, 8, 10, tzinfo=timezone.utc)
    end_dt = datetime(2026, 9, 8, tzinfo=timezone.utc)
    mock_nc = Path("/workspace/scratch/mock_tide.nc")
    if mock_nc.exists():
        # Process the mock file with focal plotting at Koksijde start
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
