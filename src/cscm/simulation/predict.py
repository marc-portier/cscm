# src/cscm/simulation/predict.py

import json
import math
from datetime import datetime, timezone, timedelta
from pathlib import Path
from logging import getLogger
from typing import Optional, Union, List

import numpy as np
import pandas as pd
import xarray as xr
import matplotlib
matplotlib.use('Agg')  # Headless mode for sandboxed environments
import matplotlib.pyplot as plt
from shapely.geometry import Point, Polygon, MultiPolygon
import shapely.wkt

from cscm.model import Position
from cscm.current.cmems.analyse import classify_grid_cells, project_to_principal_axis
from cscm.simulation.jobs import JobCalcConfig, JobColorsConfig, JobLabelsConfig

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
            # Squeeze and slice for speed if dataset is huge, but interp on the 3D grid is clean
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
    Vindt de getijdenpieken nabij focal_pos binnen start_time en end_time.

    Berekent de parallelle snelheid puur op basis van de Pythagoras-grootte
    gecombineerd met het teken van de oostwaartse stroomcomponent (uo).
    """
    lat_col = 'latitude' if 'latitude' in ds.coords else 'lat'
    lon_col = 'longitude' if 'longitude' in ds.coords else 'lon'
    lats = ds[lat_col].values
    lons = ds[lon_col].values
    times = ds['time'].values

    # 1. Vind de dichtstbijzijnde actieve grid-cel
    dist = (lats[:, np.newaxis] - focal_pos.lat)**2 + (lons[np.newaxis, :] - focal_pos.lon)**2
    y_idx, x_idx = np.unravel_index(np.argmin(dist), dist.shape)

    uo = ds['uo'][:, y_idx, x_idx].values
    vo = ds['vo'][:, y_idx, x_idx].values

    # Filter droge cellen/land
    u_clean = uo[~np.isnan(uo)]
    if len(u_clean) < 2:
        log.error("Geselecteerde startpositie ligt op land. Kan getijdenpieken niet bepalen.")
        return []

    # 2. Pythagoras grootte * teken van de oostwaartse component (oostwaartse stroming = vloedstroom)
    v_magnitude = np.sqrt(uo**2 + vo**2)
    v_sign = np.sign(uo)
    v_parallel = v_magnitude * v_sign

    # 3. Verzamel potentiële pieken (local extrema)
    pfc_candidates = []
    pec_candidates = []
    min_peak_threshold = 0.1  # Negeer ruis rond de 0 m/s >> code werkt dus enkel in gebieden met voldoende stroming

    for t_idx in range(1, len(v_parallel) - 1):
        v_prev = v_parallel[t_idx - 1]
        v_curr = v_parallel[t_idx]
        v_next = v_parallel[t_idx + 1]

        if np.isnan(v_prev) or np.isnan(v_curr) or np.isnan(v_next):
            continue

        # Maxima (Vloedstroom / PFC / PVS)
        if v_prev < v_curr > v_next and v_curr > min_peak_threshold:
            peak_time = pd.to_datetime(times[t_idx]).replace(tzinfo=timezone.utc)
            if start_time <= peak_time <= end_time:
                pfc_candidates.append({
                    "time": peak_time,
                    "type": "PFC",
                    "velocity_mps": float(v_curr)
                })

        # Minima (Ebstroom / PEC / PES)
        elif v_prev > v_curr < v_next and v_curr < -min_peak_threshold:
            peak_time = pd.to_datetime(times[t_idx]).replace(tzinfo=timezone.utc)
            if start_time <= peak_time <= end_time:
                pec_candidates.append({
                    "time": peak_time,
                    "type": "PEC",
                    "velocity_mps": float(v_curr)
                })

    # 4. Filter dubbele pieken (temporal dead-time van minimaal 4 uur)
    def filter_adjacent_peaks(candidates: list, min_spacing_hours: float = 4.0) -> list:
        # Sorteer eerst op de sterkste absolute snelheid
        sorted_by_strength = sorted(candidates, key=lambda x: abs(x["velocity_mps"]), reverse=True)
        filtered = []

        for cand in sorted_by_strength:
            too_close = False
            for accepted in filtered:
                time_diff_h = abs((cand["time"] - accepted["time"]).total_seconds()) / 3600.0
                if time_diff_h < min_spacing_hours:
                    too_close = True
                    break
            if not too_close:
                filtered.append(cand)

        # Sorteer het resultaat chronologisch
        return sorted(filtered, key=lambda x: x["time"])

    filtered_pfc = filter_adjacent_peaks(pfc_candidates, min_spacing_hours=4.0)
    filtered_pec = filter_adjacent_peaks(pec_candidates, min_spacing_hours=4.0)

    # Voeg vloed en eb samen en sorteer chronologisch
    detected_peaks = sorted(filtered_pfc + filtered_pec, key=lambda x: x["time"])

    log.info(f"Getijdedetectie (Pythagoras): {len(detected_peaks)} stabiele pieken overgebleven.")
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

    # Intrinsic swimmer speed (1.0 m/s as defined in the plan)
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

        # Don't step coordinate at the final point
        if elapsed >= duration_sec:
            break

        # Calculate combined movement components
        v_eff_east = v_swimmer_east + u_c
        v_eff_north = v_swimmer_north + v_c

        # WGS84 physical degree offsets
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
    <desc>Simulated 6h Coast Swim Track</desc>
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
    df_list: list,
    day_label: str,
    output_path: Path,
    status_mask: np.ndarray,
    lats: np.ndarray,
    lons: np.ndarray,
    model: CmemsForecastCurrentsModel,
    mussel_farm_wkt: Optional[str] = None,
    coastline_wkt_path: Optional[Path] = None,
    obstructions_wkt_path: Optional[Path] = None,
    colors_cfg: Optional[JobColorsConfig] = None,
    labels_cfg: Optional[JobLabelsConfig] = None
) -> None:
    """
    Generates a beautiful daily map plot showing the test swim trajectories
    overlaid with a Visgraat (fishbone) representation of tidal vectors along the intended course.
    Auto-zooms to the bounding box of the trajectories + 1500m outset buffer.
    """
    plt.figure(figsize=(11, 10))

    # Calculate trajectories bounding box using start, actual track, and backbone ends
    all_lats = []
    all_lons = []
    for df, tide_type, start_dt, calc_cfg in df_list:
        # 1. Voeg de werkelijke (afgedreven) routepunten toe
        all_lats.extend(df['lat'].values)
        all_lons.extend(df['lon'].values)

        # 2. Voeg de ruggengraat-uiteinden toe (start en geprojecteerd einde)
        start_lat = df['lat'][0]
        start_lon = df['lon'][0]
        all_lats.append(start_lat)
        all_lons.append(start_lon)

        duration_s = calc_cfg.duration_hours * 3600.0
        bearing_rad = math.radians(calc_cfg.bearing_deg)
        v_swimmer_east = 1.0 * math.sin(bearing_rad)
        v_swimmer_north = 1.0 * math.cos(bearing_rad)

        end_lat = start_lat + (v_swimmer_north * duration_s) / 111132.0
        end_lon = start_lon + (v_swimmer_east * (duration_s / (111132.0 * math.cos(math.radians(start_lat)))))

        all_lats.append(end_lat)
        all_lons.append(end_lon)

    min_lat, max_lat = min(all_lats), max(all_lats)
    min_lon, max_lon = min(all_lons), max(all_lons)

    # Outset buffer of 1500m (approx 0.0135 degrees latitude/longitude)
    buffer_deg = 0.0135
    map_min_lat = min_lat - buffer_deg
    map_max_lat = max_lat + buffer_deg
    map_min_lon = min_lon - buffer_deg
    map_max_lon = max_lon + buffer_deg

    # 1. Background Grid Plotting
    # Status levels: 0: Land (brown #54360f @ 75%), 1: Boundary (grey #C0C0C0 @ 15%), 2: Water (blue #0087d6 @ 10%)
    # Render layers separately to respect specific opacities cleanly
    water_mask = np.where(status_mask == 2, 2, np.nan)
    plt.pcolormesh(
        lons, lats, water_mask,
        cmap=matplotlib.colors.ListedColormap(['#0087d6']),
        alpha=0.10, zorder=1, shading='auto'
    )

    boundary_mask = np.where(status_mask == 1, 1, np.nan)
    plt.pcolormesh(
        lons, lats, boundary_mask,
        cmap=matplotlib.colors.ListedColormap(['#C0C0C0']),
        alpha=0.15, zorder=1, shading='auto'
    )

    land_mask = np.where(status_mask == 0, 0, np.nan)
    plt.pcolormesh(
        lons, lats, land_mask,
        cmap=matplotlib.colors.ListedColormap(['#54360f']),
        alpha=0.75, zorder=1, shading='auto'
    )

    # Draw strakke thin black border contour around cells
    plt.contour(lons, lats, status_mask, levels=[0.5, 1.5], colors='black', linewidths=0.5, alpha=0.3, zorder=2)

    # 2. Vloeiende Kustlijn WKT Plotting
    log.info(f"Rendering coastline from {coastline_wkt_path.absolute}")
    if coastline_wkt_path and coastline_wkt_path.exists():
        try:
            log.info(f"Loading coastline data from: {coastline_wkt_path.name}")
            coast_df = pd.read_csv(coastline_wkt_path)
            log.info(f"Loaded {len(coast_df)} coastline geometries from CSV.")
            for _, row in coast_df.iterrows():
                geom_str = None
                for col in ["WKT", "wkt", "geometry", "Geometry", "geom", "Geom"]:
                    if col in row:
                        geom_str = row[col]
                        break
                if not geom_str and len(row) > 0:
                    geom_str = row.iloc[0]

                if geom_str and isinstance(geom_str, str):
                    geom = shapely.wkt.loads(geom_str)
                    if isinstance(geom, (Polygon, MultiPolygon)):
                        if hasattr(geom, "geoms"):
                            polys = geom.geoms
                        else:
                            polys = [geom]

                        for poly in polys:
                            x, y = poly.exterior.xy
                            plt.fill(x, y, color="#5ede55", alpha=0.75, zorder=3)
                            plt.plot(x, y, color='black', linewidth=1.2, zorder=4)
                    else:
                        x, y = geom.xy
                        plt.plot(x, y, color='black', linewidth=1.5, zorder=4)
            log.info(f"Successfully rendered custom coastline from: {coastline_wkt_path.name}")
        except Exception as e:
            log.warning(f"Could not load custom coastline WKT: {e}")

    # 3. Obstructions WKT Plotting
    log.info(f"Rendering obstructions from {obstructions_wkt_path.absolute() if obstructions_wkt_path else 'N/A'}")
    if obstructions_wkt_path and obstructions_wkt_path.exists():
        log.info(f"Rendering custom obstructions from: {obstructions_wkt_path.name}")
        try:
            obs_df = pd.read_csv(obstructions_wkt_path)
            log.info(f"Loaded {len(obs_df)} obstruction geometries from CSV.")
            for idx, row in obs_df.iterrows():
                geom_str = None
                for col in ["WKT", "wkt", "geometry", "Geometry", "geom", "Geom"]:
                    if col in row:
                        geom_str = row[col]
                        break
                if not geom_str and len(row) > 0:
                    geom_str = row.iloc[0]

                if geom_str and isinstance(geom_str, str):
                    geom = shapely.wkt.loads(geom_str)
                    if isinstance(geom, (Polygon, MultiPolygon)):
                        if hasattr(geom, "geoms"):
                            polys = geom.geoms
                        else:
                            polys = [geom]
                        for poly in polys:
                            x, y = poly.exterior.xy
                            # Pink fill #f33bfe, 35% opaque, stroke 100% opaque
                            plt.fill(x, y, color='#f33bfe', alpha=0.35, hatch='//', edgecolor='#f33bfe',
                                     linewidth=1.2, zorder=5)
            log.info(f"Rendered custom obstructions from: {obstructions_wkt_path.name}")
        except Exception as e:
            log.warning(f"Failed to render custom obstructions CSV: {e}")

    # 4. Trajectory Plotting with Fishbone (Visgraat)
    default_styles = {
        "PFC": {"color": "royalblue", "label": "PFC (Flood)"},
        "PEC": {"color": "forestgreen", "label": "PEC (Ebb)"}
    }

    for idx, (df, tide_type, start_dt, calc_cfg) in enumerate(df_list):
        # Determine sequence colors dynamically
        if colors_cfg:
            run_color = colors_cfg.actuals[idx % len(colors_cfg.actuals)].strip()
            spine_color = colors_cfg.spines[idx % len(colors_cfg.spines)].strip()
        else:
            style = default_styles.get(tide_type, {"color": "gray"})
            run_color = style["color"]
            spine_color = "gold" if tide_type == "PFC" else "magenta"

        # Trajectories are always solid lines as requested
        line_style = "-"
        label_tide = "PFC (Flood)" if tide_type == "PFC" else "PEC (Ebb)" if tide_type == "PEC" else tide_type

        # Local time formatting (CEST UTC+2)
        local_dt = start_dt + timedelta(hours=2)
        local_time_str = local_dt.strftime('%H:%M')
        label = f"{label_tide} ({local_time_str} CEST, max {df.iloc[-1]['v_magnitude']:.2f} m/s)"

        # Plot full actual trajectory
        plt.plot(df['lon'], df['lat'], color=run_color, linestyle=line_style,
                 linewidth=2.2, label=label, zorder=6)

        # Direction annotation arrow on the actual trajectory
        mid_idx = len(df) // 2
        plt.annotate("", xy=(df.iloc[mid_idx+1]['lon'], df.iloc[mid_idx+1]['lat']),
                     xytext=(df.iloc[mid_idx]['lon'], df.iloc[mid_idx]['lat']),
                     arrowprops=dict(arrowstyle="->", color=run_color, lw=2.2), zorder=7)

        # --- Visgraat backbone (Ruggengraat / Intended Course) ---
        start_lat = df.iloc[0]['lat']
        start_lon = df.iloc[0]['lon']
        duration_s = calc_cfg.duration_hours * 3600.0
        bearing_rad = math.radians(calc_cfg.bearing_deg)

        # Intended swimmer speed is 1.0 m/s
        v_swimmer_east = 1.0 * math.sin(bearing_rad)
        v_swimmer_north = 1.0 * math.cos(bearing_rad)

        # Plot intended backbone line (thin dotted)
        delta_lat_dr = (v_swimmer_north * duration_s) / 111132.0
        delta_lon_dr = (v_swimmer_east * duration_s) / (111132.0 * math.cos(math.radians(start_lat)))
        end_lat = start_lat + delta_lat_dr
        end_lon = start_lon + delta_lon_dr

        plt.plot([start_lon, end_lon], [start_lat, end_lat],
                 color=run_color, linestyle=":", linewidth=1.1, alpha=0.55,
                 label="Intended Course (Backbone)" if idx == 0 else "", zorder=4)

        # Plot backbone navigation details label
        spine_format = labels_cfg.spine if (labels_cfg and labels_cfg.spine) else "bearing|duration|totaldistance"
        parts = []
        for f in spine_format.split("|"):
            f = f.strip().lower()
            if f == "type":
                parts.append(label_tide)
            elif f == "bearing":
                parts.append(f"{calc_cfg.bearing_deg:.0f}°")
            elif f == "duration":
                parts.append(f"{calc_cfg.duration_hours:.1f}h")
            elif f == "speed":
                parts.append("1.0 m/s")
            elif f == "totaldistance":
                parts.append("21.6 km")
            elif f == "ribdistance":
                parts.append("15 min")
        spine_label_text = " | ".join(parts) if parts else ""

        if spine_label_text:
            # Shift the navigation label away from the spine to avoid overlap with the rib markers.
            # by 900m (~15 min at 1mps should be beyond max mps of current + some margin)
            shift_m = 900.0
            ortho_rad = bearing_rad + math.pi / 2.0
            shift_lat = (shift_m * math.cos(ortho_rad)) / 111132.0
            shift_lon = (shift_m * math.sin(ortho_rad)) / (111132.0 * math.cos(math.radians(start_lat + 0.5 * delta_lat_dr)))

            mid_lat = start_lat + 0.5 * delta_lat_dr + shift_lat
            mid_lon = start_lon + 0.5 * delta_lon_dr + shift_lon
            dx_deg = end_lon - start_lon
            dy_deg = end_lat - start_lat
            angle_deg = math.degrees(math.atan2(dy_deg, dx_deg))
            # Keep text readable (not upside down)
            if angle_deg > 90:
                angle_deg -= 180
            elif angle_deg < -90:
                angle_deg += 180

            plt.text(mid_lon, mid_lat, spine_label_text,
                     color=run_color, fontsize=8, fontweight='bold',
                     rotation=angle_deg, ha='center', va='center',
                     bbox=dict(boxstyle="round,pad=0.2", facecolor="white", edgecolor="none", alpha=0.85),
                     zorder=7)

        # --- Visgraat ribs (Graten om de 15' = 900s) ---
        interval_s = 900.0  # 15 minutes
        num_intervals = int(duration_s / interval_s)
        ribs_format = labels_cfg.ribs if (labels_cfg and labels_cfg.ribs) else "deviationspeed"

        for k in range(1, num_intervals + 1):
            elapsed_s = k * interval_s
            lat_k = start_lat + (v_swimmer_north * elapsed_s) / 111132.0
            lon_k = start_lon + (v_swimmer_east * elapsed_s) / (111132.0 * math.cos(math.radians(lat_k)))

            target_time = start_dt + timedelta(seconds=elapsed_s)
            u_c, v_c = model.get_current_vector(Position(lat_k, lon_k), target_time)

            # Rib stroomvector displacement over 15 minutes (900 seconds)
            delta_lat_rib = (v_c * 900.0) / 111132.0
            delta_lon_rib = (u_c * 900.0) / (111132.0 * math.cos(math.radians(lat_k)))

            # Plot rib lines (no arrowheads/quivers as requested!)
            plt.plot([lon_k, lon_k + delta_lon_rib], [lat_k, lat_k + delta_lat_rib],
                     color=spine_color, linewidth=1.1, alpha=0.85, zorder=5)

            # Draw small solid dot at the end of the rib line
            plt.scatter(lon_k + delta_lon_rib, lat_k + delta_lat_rib,
                        color=spine_color, s=12, edgecolors='none', zorder=5)

            # Plot rib label at the exact opposite side of the backbone line
            rib_speed = math.sqrt(u_c**2 + v_c**2)
            rib_dist_m = rib_speed * 900.0

            r_parts = []
            for rf in ribs_format.split("|"):
                rf = rf.strip().lower()
                if rf == "deviationdistance":
                    r_parts.append(f"{int(round(rib_dist_m))}m")
                elif rf == "deviationspeed":
                    r_parts.append(f"{rib_speed:.2f}")

            rib_label_text = " / ".join(r_parts) if r_parts else f"{rib_speed:.2f}"

            # Calculate opposite position for label
            opp_u = -u_c
            opp_v = -v_c
            opp_len = math.sqrt(opp_u**2 + opp_v**2)
            if opp_len > 0.005:
                # Offset in degrees (~0.0022 deg is roughly 220m visual margin)
                offset_deg = 0.0022
                text_lon = lon_k + (opp_u / opp_len) * offset_deg
                text_lat = lat_k + (opp_v / opp_len) * offset_deg
            else:
                text_lon = lon_k - 0.002
                text_lat = lat_k - 0.001

            plt.text(text_lon, text_lat, rib_label_text,
                     color=spine_color, fontsize=7, fontweight='bold',
                     ha='center', va='center',
                     bbox=dict(boxstyle="round,pad=0.15", facecolor="white", edgecolor="none", alpha=0.7),
                     zorder=6)

    # Plot start point marker based on labeled positions str()
    first_calc = df_list[0][3]
    start_label = str(first_calc.from_pos)
    start_lon = first_calc.from_pos.lon
    start_lat = first_calc.from_pos.lat

    plt.scatter(start_lon, start_lat, color='gold', edgecolor='black', s=200, marker='*',
                label=start_label, zorder=8)

    # Focus map limits
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
