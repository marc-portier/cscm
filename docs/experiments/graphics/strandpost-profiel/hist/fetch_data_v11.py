#!/usr/bin/env python3
"""
Data Retrieval Script for Coastal Current Profile v11 (Live Forecast Standard).

Key Responsibilities:
- Retrieve CMEMS hydrodynamic forecast currents for the operational daytime window (today + 1).
- Fetch operational water level forecasts for Oostende (KT-Last + KT-HW/LW) via HIC Waterinfo (KiWIS) using HicClient.
- Apply validated alongshore phase lag (+7 minutes for Bredene Strandpost 4).
- Detect High Water, Low Water, Peak Flood (PFC), Peak Ebb (PEC), and slack water turns.
- Compute water curve geometry (line_d, area_d) filled from 0m TAW baseline on left.
- Export complete template contract to data_to_plot_v11.yaml.
"""

import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
import xarray as xr
import yaml

from cscm.current.cmems.analyse import classify_grid_cells
from cscm.current.cmems.retrieve import CMEMSDataManager
from cscm.tide.hic import HicClient

HIST_DIR = Path(__file__).resolve().parent
REPO_ROOT = HIST_DIR.parents[4]
YAML_PATH = REPO_ROOT / "src" / "cscm" / "resources" / "be_lifeguard_posts.yaml"
CMEMS_DIR = REPO_ROOT / "src" / "cscm" / "current" / "cmems" / "data_store"

OUTPUT_YAML = HIST_DIR / "data_to_plot_v11.yaml"


def find_or_retrieve_cmems_nc(target_dt: datetime) -> Path:
    """
    Finds a NetCDF file in CMEMS_DIR that covers target_dt.
    If none is found or files are missing, invokes CMEMSDataManager to update
    the local cache using credentials from .env.
    """
    nc_files = sorted(CMEMS_DIR.glob("*.nc"))
    for nc_path in reversed(nc_files):
        try:
            with xr.open_dataset(nc_path) as ds:
                t_min = pd.to_datetime(ds.time.values[0]).tz_localize(None)
                t_max = pd.to_datetime(ds.time.values[-1]).tz_localize(None)
                target_naive = target_dt.replace(tzinfo=None)
                if t_min <= target_naive <= t_max:
                    return nc_path
        except Exception:
            continue

    # Not covered by existing files: trigger central CMEMSDataManager retrieval
    print(f"Target date {target_dt.date()} not in local cache; updating via CMEMSDataManager...")
    dm = CMEMSDataManager()
    dm.update_cmems_data(limit=1)

    nc_files = sorted(CMEMS_DIR.glob("*.nc"))
    if not nc_files:
        raise FileNotFoundError(f"No NetCDF (.nc) files found in {CMEMS_DIR} after update")
    return nc_files[-1]


def load_post_config(municipality_key="bredene", post_key="post_4"):
    with open(YAML_PATH, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    muni = cfg.get("municipalities", {}).get(municipality_key, {})
    post = muni.get("posts", {}).get(post_key, {})

    tz_str = muni.get(
        "timezone",
        cfg.get("metadata", {}).get("timezone", "Europe/Brussels"),
    )

    seaward_bearing = muni.get(
        "seaward_bearing_deg",
        cfg.get("metadata", {}).get("seaward_bearing_deg", 335.0),
    )

    north_angle = (360.0 - seaward_bearing) % 360.0
    alongshore_right = (seaward_bearing + 90.0) % 360.0
    alongshore_left = (seaward_bearing - 90.0) % 360.0

    return {
        "muni_name": muni.get("name", "Bredene"),
        "post_name": post.get("name", "Droogen Opganck"),
        "post_number": post.get("number", 4),
        "lat": post.get("lat", 51.2542),
        "lon": post.get("lon", 2.9740),
        "timezone": tz_str,
        "seaward_bearing": seaward_bearing,
        "north_angle": north_angle,
        "alongshore_right": alongshore_right,
        "alongshore_left": alongshore_left,
        "tidal_cycle_hours": cfg.get("metadata", {}).get("tidal_cycle_hours", 12.42),
    }


def find_nearest_water_cell(ds: xr.Dataset, target_lat: float, target_lon: float):
    """
    Finds nearest cell with status_mask == 2 (Water with no land neighbors),
    bypassing border cells that suffer from coastal artificial damping.
    """
    status_mask, _ = classify_grid_cells(ds)
    lats = ds["latitude"].values
    lons = ds["longitude"].values

    lon_2d, lat_2d = np.meshgrid(lons, lats)
    d_lat = (lat_2d - target_lat) * 111320
    d_lon = (lon_2d - target_lon) * 111320 * np.cos(np.radians(target_lat))
    dist = np.hypot(d_lat, d_lon)

    dist_water = np.where(status_mask == 2, dist, np.inf)
    y_idx, x_idx = np.unravel_index(np.argmin(dist_water), dist_water.shape)

    return {
        "y_idx": int(y_idx),
        "x_idx": int(x_idx),
        "lat": float(lats[y_idx]),
        "lon": float(lons[x_idx]),
        "distance_m": float(dist_water[y_idx, x_idx]),
    }


def generate_layout(n_slots, v_max_mps=1.5):
    y_start = 220.0
    dy = 19.5
    y_end = y_start + (n_slots - 1) * dy

    benchmark_y_bottom = y_end + 20.0
    scale_px_per_mps = 330.0 / v_max_mps

    swimmer_callouts = [
        {
            "speed": 0.5,
            "speed_str": "0.5 m/s",
            "kmh_str": "1.8 km/h",
            "label": "Recreatieve zwemmer",
            "sub": "startniveau",
            "color": "#15803d",
            "bg": "#f0fdf4",
            "border": "#22c55e",
            "ebb_x": round(425.0 - 0.5 * scale_px_per_mps, 1),
            "flood_x": round(495.0 + 0.5 * scale_px_per_mps, 1),
            "y": round(benchmark_y_bottom + 18.0, 1),
        },
        {
            "speed": 1.0,
            "speed_str": "1.0 m/s",
            "kmh_str": "3.6 km/h",
            "label": "Competitief amateur",
            "sub": "kruissnelheid",
            "color": "#0284c7",
            "bg": "#eff6ff",
            "border": "#38bdf8",
            "ebb_x": round(425.0 - 1.0 * scale_px_per_mps, 1),
            "flood_x": round(495.0 + 1.0 * scale_px_per_mps, 1),
            "y": round(benchmark_y_bottom + 46.0, 1),
        },
        {
            "speed": 1.5,
            "speed_str": "1.5 m/s",
            "kmh_str": "5.4 km/h",
            "label": "Olympisch atleet",
            "sub": "wereldtop",
            "color": "#ea580c",
            "bg": "#fff7ed",
            "border": "#fb923c",
            "ebb_x": round(425.0 - 1.5 * scale_px_per_mps, 1),
            "flood_x": round(495.0 + 1.5 * scale_px_per_mps, 1),
            "y": round(benchmark_y_bottom + 74.0, 1),
        },
    ]
    swimmer_callouts = [c for c in swimmer_callouts if c["speed"] <= v_max_mps + 1e-4]

    legend_y = benchmark_y_bottom + 104.0
    footer_y = legend_y + 126.0
    total_height = int(footer_y + 35.0)

    flood_grad_x2 = round(495.0 + 1.5 * scale_px_per_mps, 1)
    ebb_grad_x2 = round(425.0 - 1.5 * scale_px_per_mps, 1)

    ticks = []
    step = 0.5
    val = step
    while val <= v_max_mps + 0.01:
        flood_x = round(495.0 + val * scale_px_per_mps, 1)
        ticks.append({
            "val": round(val, 2),
            "x": flood_x,
            "label": f"+{val:.1f} m/s" if abs(val - v_max_mps) < 0.05 else f"+{val:.1f}",
        })
        ebb_x = round(425.0 - val * scale_px_per_mps, 1)
        ticks.append({
            "val": round(-val, 2),
            "x": ebb_x,
            "label": f"-{val:.1f} m/s" if abs(val - v_max_mps) < 0.05 else f"-{val:.1f}",
        })
        val += step

    ticks.sort(key=lambda t: t["val"])

    benchmark_definitions = [
        {"speed": 0.5, "width": 1.5, "stroke": "#93c5fd", "ebb_stroke": "#c7d2fe"},
        {"speed": 1.0, "width": 2.0, "stroke": "#38bdf8", "ebb_stroke": "#818cf8"},
        {"speed": 1.5, "width": 2.0, "stroke": "#0284c7", "ebb_stroke": "#4f46e5"},
    ]
    benchmarks = []
    for b in benchmark_definitions:
        if b["speed"] <= v_max_mps + 1e-4:
            benchmarks.append({
                "speed": b["speed"],
                "width": b["width"],
                "stroke": b["stroke"],
                "ebb_stroke": b["ebb_stroke"],
                "flood_x": round(495.0 + b["speed"] * scale_px_per_mps, 1),
                "ebb_x": round(425.0 - b["speed"] * scale_px_per_mps, 1),
            })

    return {
        "v_max_mps": v_max_mps,
        "scale_px_per_mps": scale_px_per_mps,
        "flood_grad_x2": flood_grad_x2,
        "ebb_grad_x2": ebb_grad_x2,
        "benchmark_y_bottom": benchmark_y_bottom,
        "grid_y_bottom": benchmark_y_bottom,
        "swimmer_callouts": swimmer_callouts,
        "legend_y": legend_y,
        "footer_y": footer_y,
        "total_height": total_height,
        "ticks": ticks,
        "benchmarks": benchmarks,
    }


def fetch_and_prepare_data(
    target_date="2026-10-16",
    start_time="07:30",
    end_time="20:30",
    v_max_mps=1.5,
    municipality_key="bredene",
    post_key="post_4",
    tide_lag_minutes=7.0,
):
    geo = load_post_config(municipality_key, post_key)
    tz_local = ZoneInfo(geo["timezone"])

    # 1. Parse operational window in LOCAL time, convert to UTC for queries
    dt_local_start = datetime.strptime(f"{target_date} {start_time}", "%Y-%m-%d %H:%M").replace(tzinfo=tz_local)
    dt_local_end = datetime.strptime(f"{target_date} {end_time}", "%Y-%m-%d %H:%M").replace(tzinfo=tz_local)
    tz_abbrev = dt_local_start.tzname() or "LT"

    dt_utc_start = dt_local_start.astimezone(timezone.utc)
    dt_utc_end = dt_local_end.astimezone(timezone.utc)

    # 2. CMEMS Current Data
    nc_path = find_or_retrieve_cmems_nc(dt_utc_start)
    print(f"Reading CMEMS dataset: {nc_path.name}")
    ds = xr.open_dataset(nc_path)
    cell = find_nearest_water_cell(ds, geo["lat"], geo["lon"])

    slice_start = dt_utc_start.strftime("%Y-%m-%dT%H:%M:00")
    slice_end = dt_utc_end.strftime("%Y-%m-%dT%H:%M:00")
    data_slice = ds.sel(time=slice(slice_start, slice_end)).isel(
        latitude=cell["y_idx"], longitude=cell["x_idx"]
    )

    times_raw = pd.to_datetime(data_slice["time"].values)
    uo_vals = data_slice["uo"].values
    vo_vals = data_slice["vo"].values

    current_records = []
    for t_raw, u, v in zip(times_raw, uo_vals, vo_vals):
        t_utc = t_raw.to_pydatetime().replace(tzinfo=timezone.utc)
        t_local = t_utc.astimezone(tz_local)

        speed = float(np.hypot(u, v))
        flow_bearing = float((np.degrees(np.arctan2(u, v))) % 360)
        canvas_angle = float(
            (flow_bearing - geo["alongshore_right"] + 180) % 360 - 180
        )
        is_flood = abs(canvas_angle) <= 90.0
        signed_v = speed if is_flood else -speed

        current_records.append({
            "dt_local": t_local,
            "dt_utc": t_utc,
            "time_str": t_local.strftime("%H:%M"),
            "hour": t_local.hour,
            "minute": t_local.minute,
            "speed": speed,
            "signed_v": signed_v,
            "flow_bearing": flow_bearing,
            "canvas_angle": canvas_angle,
            "is_flood": is_flood,
        })
    ds.close()

    # 3. HIC Operational Water Level Forecast for Oostende (KT-Last) with +7 min shift for Bredene
    hic = HicClient()
    print("Fetching HIC KT-Last forecast for Oostende...")
    # Buffer query window by 2 hours on each side to interpolate boundary slots smoothly
    query_start = dt_utc_start - timedelta(hours=2)
    query_end = dt_utc_end + timedelta(hours=2)
    df_hic = hic.get_water_levels("OST", query_start, query_end, source="forecast")
    if df_hic.empty:
        print("Fallback to astronomical Astro.05 prediction...")
        df_hic = hic.get_water_levels("OST", query_start, query_end, source="astro")

    if not df_hic.empty:
        df_hic = df_hic.sort_values(by="timestamp").reset_index(drop=True)
        hic_timestamps = np.array([ts.timestamp() for ts in df_hic["timestamp"]])
        hic_levels = df_hic["water_level_m_taw"].values
    else:
        hic_timestamps = np.array([])
        hic_levels = np.array([])

    # Interpolate water levels for each slot with +7 min lag
    for r in current_records:
        if len(hic_timestamps) > 1:
            t_eval = (r["dt_utc"] - timedelta(minutes=tide_lag_minutes)).timestamp()
            h_interp = float(np.interp(t_eval, hic_timestamps, hic_levels))
        else:
            h_interp = 2.50
        r["h_taw"] = round(h_interp, 2)

    # 4. Current Extrema & Slack Water Detection
    flood_records = [r for r in current_records if r["is_flood"]]
    ebb_records = [r for r in current_records if not r["is_flood"]]

    local_flood_peaks = []
    for i in range(1, len(current_records) - 1):
        if current_records[i]["is_flood"]:
            if (
                current_records[i]["speed"] >= current_records[i - 1]["speed"]
                and current_records[i]["speed"] >= current_records[i + 1]["speed"]
            ):
                local_flood_peaks.append(current_records[i])

    local_ebb_peaks = []
    for i in range(1, len(current_records) - 1):
        if not current_records[i]["is_flood"]:
            if (
                current_records[i]["speed"] >= current_records[i - 1]["speed"]
                and current_records[i]["speed"] >= current_records[i + 1]["speed"]
            ):
                local_ebb_peaks.append(current_records[i])

    pfc_rec = (
        max(local_flood_peaks, key=lambda r: r["speed"])
        if local_flood_peaks
        else (max(flood_records, key=lambda r: r["speed"]) if flood_records else None)
    )
    pec_rec = (
        max(local_ebb_peaks, key=lambda r: r["speed"])
        if local_ebb_peaks
        else (max(ebb_records, key=lambda r: r["speed"]) if ebb_records else None)
    )

    kentering_times = set()
    for i in range(1, len(current_records) - 1):
        prev_r, curr_r, next_r = current_records[i - 1], current_records[i], current_records[i + 1]
        if prev_r["is_flood"] != curr_r["is_flood"]:
            k_rec = curr_r if curr_r["speed"] < prev_r["speed"] else prev_r
            kentering_times.add(k_rec["time_str"])
        elif curr_r["speed"] < 0.10 and curr_r["speed"] <= prev_r["speed"] and curr_r["speed"] <= next_r["speed"]:
            kentering_times.add(curr_r["time_str"])

    # 5. Build Slots and Water Curve Geometry
    y_start = 220.0
    dy = 19.5
    slots = []
    water_points = []
    msl = 2.45  # Standard Belgian coastal MSL (~2.45m TAW)
    base_x = round(460.0 + (0.0 - msl) * 135.0, 1)  # 0m TAW reference baseline on left (129.2px)

    for i, r in enumerate(current_records):
        y = round(y_start + i * dy, 1)
        time_str = r["time_str"]
        m_int = r["minute"]
        h_int = r["hour"]

        # Water level x coordinate
        wx = round(460.0 + (r["h_taw"] - msl) * 135.0, 1)
        water_points.append((wx, y))

        is_pfc = bool(pfc_rec and time_str == pfc_rec["time_str"])
        is_pec = bool(pec_rec and time_str == pec_rec["time_str"])
        is_kentering = (time_str in kentering_times)

        slots.append({
            "time": time_str,
            "hour_label": f"{h_int}h" if m_int == 0 else None,
            "minute": m_int,
            "quarter_type": m_int // 15,
            "y": y,
            "v": round(r["signed_v"], 2),
            "speed": round(r["speed"], 2),
            "angle": round(r["canvas_angle"], 1),
            "flow_bearing": round(r["flow_bearing"], 1),
            "h_taw": r["h_taw"],
            "is_pfc": is_pfc,
            "is_pec": is_pec,
            "is_kentering": is_kentering,
            "is_hw": False,
            "is_lw1": False,
            "is_lw2": False,
            "is_lw": False,
            "is_marked": is_pfc or is_pec or is_kentering,
        })

    # High Water Peak & Low Water Extremes
    hw_idx = int(np.argmax([s["h_taw"] for s in slots]))
    slots[hw_idx]["is_hw"] = True
    slots[hw_idx]["is_marked"] = True
    hw_slot = slots[hw_idx]
    hw_wx = round(460.0 + (hw_slot["h_taw"] - msl) * 135.0, 1)

    lw_idx = int(np.argmin([s["h_taw"] for s in slots]))
    slots[lw_idx]["is_lw1"] = True
    slots[lw_idx]["is_lw"] = True
    slots[lw_idx]["is_marked"] = True
    lw1_slot = slots[lw_idx]
    lw1_wx = round(460.0 + (lw1_slot["h_taw"] - msl) * 135.0, 1)

    # SVG Path generation
    line_d = "M " + " L ".join(f"{pt[0]} {pt[1]}" for pt in water_points)
    area_d = (
        f"M {base_x} {water_points[0][1]} "
        + " ".join(f"L {pt[0]} {pt[1]}" for pt in water_points)
        + f" L {base_x} {water_points[-1][1]} Z"
    )

    water_level = {
        "line_d": line_d,
        "area_d": area_d,
        "hw": {
            "x": hw_wx,
            "y": hw_slot["y"],
            "height": f"{hw_slot['h_taw']:.2f} m",
            "time": hw_slot["time"],
        },
        "lw1": {
            "x": lw1_wx,
            "y": lw1_slot["y"],
            "height": f"{lw1_slot['h_taw']:.2f} m",
            "time": lw1_slot["time"],
        },
        "lw2": None,
    }

    # 6. Combined Swimmer & Lifeguard Insights
    layout = generate_layout(len(slots), v_max_mps=v_max_mps)

    dt_obj = datetime.strptime(target_date, "%Y-%m-%d")
    days_nl = ["Maandag", "Dinsdag", "Woensdag", "Donderdag", "Vrijdag", "Zaterdag", "Zondag"]
    months_nl = [
        "", "Januari", "Februari", "Maart", "April", "Mei", "Juni",
        "Juli", "Augustus", "September", "Oktober", "November", "December"
    ]
    date_formatted = f"{days_nl[dt_obj.weekday()]} {dt_obj.day} {months_nl[dt_obj.month]} {dt_obj.year}"

    pfc_str = f"{pfc_rec['time_str']}" if pfc_rec else "--:--"
    pfc_spd = f"{pfc_rec['speed']:.2f} m/s" if pfc_rec else ""
    pec_str = f"{pec_rec['time_str']}" if pec_rec else "--:--"
    pec_spd = f"{pec_rec['speed']:.2f} m/s" if pec_rec else ""
    k_str = ", ".join(sorted(kentering_times)) if kentering_times else "rond kentering"

    # Time lag between PFC and HW
    if pfc_rec:
        pfc_dt = datetime.strptime(pfc_rec["time_str"], "%H:%M")
        hw_dt = datetime.strptime(hw_slot["time"], "%H:%M")
        diff_min = int((hw_dt - pfc_dt).total_seconds() / 60)
        if diff_min > 0:
            diff_text = f"{diff_min} min vóór Hoogwater ({hw_slot['time']} {tz_abbrev})"
        elif diff_min == 0:
            diff_text = f"exact gelijktijdig met Hoogwater ({hw_slot['time']} {tz_abbrev})"
        else:
            diff_text = f"{abs(diff_min)} min na Hoogwater ({hw_slot['time']} {tz_abbrev})"
    else:
        diff_text = f"vóór Hoogwater ({hw_slot['time']} {tz_abbrev})"

    insight = {
        "headline": f'Piek Vloedstroom ({pfc_str} {tz_abbrev}, {pfc_spd}) valt <tspan font-weight="800" fill="#0284c7">{diff_text}</tspan>!',
    }

    legend_events = {
        "pfc": {
            "time": pfc_rec["time_str"] if pfc_rec else "--:--",
            "val": f"+{pfc_rec['speed']:.2f} m/s" if pfc_rec else "",
        },
        "hw": {
            "time": hw_slot["time"],
            "val": f"{water_level['hw']['height']}",
        },
        "kenteringen": sorted(list(kentering_times)),
        "pec": {
            "time": pec_rec["time_str"] if pec_rec else "--:--",
            "val": f"-{pec_rec['speed']:.2f} m/s" if pec_rec else "",
        },
        "lw": {
            "time": lw1_slot["time"],
            "val": f"{water_level['lw1']['height']}",
        },
    }

    elapsed_h = (len(slots) - 1) * 0.25

    return {
        "layout": layout,
        "meta": {
            "version": "v11",
            "project_title": "CSCM KUST-STROMINGSPROFIEL (DAGVERWACHTING)",
            "location_name": f"{geo['muni_name']} — Strandpost {geo['post_number']}",
            "date_str": date_formatted,
            "time_window": f"{start_time} – {end_time} {tz_abbrev} ({elapsed_h:.1f}u Dagvenster)",
            "timezone": geo["timezone"],
            "target_date": target_date,
            "seaward_bearing_deg": geo["seaward_bearing"],
            "north_angle": geo["north_angle"],
            "alongshore_right": geo["alongshore_right"],
            "alongshore_left": geo["alongshore_left"],
            "source_currents": f"CMEMS 1.5km 2D PT15M ({nc_path.name})",
            "source_water_levels": "HIC Waterinfo KiWIS KT-Last (Oostende Haven +7 min kustverschuiving)",
            "source_label": f"Model: CMEMS 1.5km 2D PT15M • Getij: HIC KiWIS KT-Last (Oostende +{tide_lag_minutes:.0f}m)",
            "selected_cell": cell,
        },
        "slots": slots,
        "water_level": water_level,
        "insight": insight,
        "legend_events": legend_events,
    }


def main():
    parser = argparse.ArgumentParser(description="Fetch and prepare data contract for Coastal Current Profile v11")
    parser.add_argument("--date", default="2026-10-16", help="Target date YYYY-MM-DD (default: 2026-10-16)")
    parser.add_argument("--start", default="07:30", help="Day start time HH:MM (default: 07:30)")
    parser.add_argument("--end", default="20:30", help="Day end time HH:MM (default: 20:30)")
    parser.add_argument("--vmax", type=float, default=1.5, help="Max velocity scale in m/s (default: 1.5)")
    parser.add_argument("--lag", type=float, default=7.0, help="Tidal phase lag in minutes relative to Oostende (default: 7.0)")
    args = parser.parse_args()

    data = fetch_and_prepare_data(
        target_date=args.date,
        start_time=args.start,
        end_time=args.end,
        v_max_mps=args.vmax,
        tide_lag_minutes=args.lag,
    )

    with open(OUTPUT_YAML, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    print(f"Successfully generated data contract: {OUTPUT_YAML}")


if __name__ == "__main__":
    main()
