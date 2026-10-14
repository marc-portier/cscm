#!/usr/bin/env python3
"""
Data Retrieval Script for Coastal Current Profile v8.
Responsibility:
- Load lifeguard post geographical configuration.
- Classify CMEMS grid cells (Land=0, Boundary=1, Water=2) via cscm.current.cmems.analyse.
- Select the nearest full-water cell (status_mask == 2) to eliminate artificial border dampening.
- Extract hydrodynamic uo, vo forecast for the requested date and time window.
- Calculate speed, flow bearings, relative canvas angles, and detect tidal extremes.
- Parameterize horizontal axis scale (v_max_mps=1.5 m/s default), generating dynamic ticks & benchmarks.
- Export context contract to YAML (data_to_plot_v8.yaml).
"""

import argparse
from datetime import datetime
import math
from pathlib import Path
import numpy as np
import pandas as pd
import xarray as xr
import yaml

from cscm.current.cmems.analyse import classify_grid_cells

HIST_DIR = Path(__file__).resolve().parent
REPO_ROOT = HIST_DIR.parents[3]
YAML_PATH = REPO_ROOT / "src" / "cscm" / "resources" / "be_lifeguard_posts.yaml"
CMEMS_DIR = REPO_ROOT / "src" / "cscm" / "current" / "cmems" / "data_store"

OUTPUT_YAML = HIST_DIR / "data_to_plot_v8.yaml"


def find_latest_cmems_nc() -> Path:
    nc_files = sorted(CMEMS_DIR.glob("*.nc"))
    if not nc_files:
        raise FileNotFoundError(f"Geen NetCDF (.nc) bestanden gevonden in {CMEMS_DIR}")
    return nc_files[-1]


def load_post_config(municipality_key="bredene", post_key="post_4"):
    with open(YAML_PATH, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    muni = cfg.get("municipalities", {}).get(municipality_key, {})
    post = muni.get("posts", {}).get(post_key, {})

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

    # Filter strictly for full water cells
    dist_water = np.where(status_mask == 2, dist, np.inf)
    y_idx, x_idx = np.unravel_index(np.argmin(dist_water), dist_water.shape)

    return {
        "y_idx": int(y_idx),
        "x_idx": int(x_idx),
        "lat": float(lats[y_idx]),
        "lon": float(lons[x_idx]),
        "dist_m": float(dist[y_idx, x_idx]),
    }


def generate_layout(n_slots: int, v_max_mps: float = 1.5):
    """
    Computes dynamic vertical layout coordinates, scale, axis ticks,
    and swimmer benchmark guidelines.
    """
    y_start = 220
    dy = 19.5
    y_end = y_start + (n_slots - 1) * dy

    grid_y_bottom = y_end + 30
    benchmark_y_bottom = y_end + 25
    swimmer_y = y_end + 53
    insight_y = swimmer_y + 110
    legend_y = insight_y + 80
    footer_y = legend_y + 94
    total_height = footer_y + 20

    # Total usable horizontal span per side (from center spine 425/495 to edge 95/825) is 330px
    span_px = 330.0
    scale_px_per_mps = round(span_px / v_max_mps, 2)

    # Dynamic Ticks (steps of 0.5 m/s)
    ticks = []
    step = 0.5
    current = step
    while current <= v_max_mps + 0.001:
        # Ebb tick (left side of spine X=425)
        ebb_x = round(425.0 - current * scale_px_per_mps, 1)
        ebb_lbl = f"-{current:.1f} m/s" if math.isclose(current, v_max_mps, rel_tol=1e-3) else f"-{current:.1f}"
        ticks.append({
            "val": -round(current, 2),
            "x": ebb_x,
            "label": ebb_lbl,
        })

        # Flood tick (right side of spine X=495)
        flood_x = round(495.0 + current * scale_px_per_mps, 1)
        flood_lbl = f"+{current:.1f} m/s" if math.isclose(current, v_max_mps, rel_tol=1e-3) else f"+{current:.1f}"
        ticks.append({
            "val": round(current, 2),
            "x": flood_x,
            "label": flood_lbl,
        })

        current += step

    # Sort ticks left-to-right (from negative/left to positive/right)
    ticks.sort(key=lambda t: t["val"])

    # Swimmer Benchmarks
    benchmark_definitions = [
        {"speed": 0.5, "width": 1.5, "stroke": "#93c5fd", "ebb_stroke": "#c7d2fe"},
        {"speed": 1.0, "width": 2.0, "stroke": "#38bdf8", "ebb_stroke": "#818cf8"},
        {"speed": 1.5, "width": 2.0, "stroke": "#0284c7", "ebb_stroke": "#4f46e5"},
    ]
    benchmarks = []
    for b in benchmark_definitions:
        if b["speed"] <= v_max_mps + 0.01:
            benchmarks.append({
                "speed": b["speed"],
                "width": b["width"],
                "stroke": b["stroke"],
                "ebb_stroke": b["ebb_stroke"],
                "flood_x": round(495.0 + b["speed"] * scale_px_per_mps, 1),
                "ebb_x": round(425.0 - b["speed"] * scale_px_per_mps, 1),
            })

    flood_grad_x2 = round(495.0 + v_max_mps * scale_px_per_mps, 1)
    ebb_grad_x2 = round(425.0 - v_max_mps * scale_px_per_mps, 1)

    return {
        "v_max_mps": float(v_max_mps),
        "scale_px_per_mps": scale_px_per_mps,
        "flood_grad_x2": flood_grad_x2,
        "ebb_grad_x2": ebb_grad_x2,
        "ticks": ticks,
        "benchmarks": benchmarks,
        "total_height": int(math.ceil(total_height)),
        "grid_y_bottom": round(grid_y_bottom, 1),
        "benchmark_y_bottom": round(benchmark_y_bottom, 1),
        "swimmer_y": round(swimmer_y, 1),
        "insight_y": round(insight_y, 1),
        "legend_y": round(legend_y, 1),
        "footer_y": round(footer_y, 1),
    }


def fetch_and_prepare_data(
    target_date="2026-10-11",
    start_time="07:30",
    end_time="20:30",
    v_max_mps=1.5,
    municipality_key="bredene",
    post_key="post_4",
):
    geo = load_post_config(municipality_key, post_key)
    nc_path = find_latest_cmems_nc()
    ds = xr.open_dataset(nc_path)

    # 1. Locate nearest open water cell (status == 2)
    cell = find_nearest_water_cell(ds, geo["lat"], geo["lon"])

    # 2. Slice temporal window
    slice_start = f"{target_date}T{start_time}:00"
    slice_end = f"{target_date}T{end_time}:00"
    data_slice = ds.sel(time=slice(slice_start, slice_end)).isel(
        latitude=cell["y_idx"], longitude=cell["x_idx"]
    )

    times = pd.to_datetime(data_slice["time"].values)
    uo_vals = data_slice["uo"].values
    vo_vals = data_slice["vo"].values

    records = []
    for t_dt, u, v in zip(times, uo_vals, vo_vals):
        speed = float(np.hypot(u, v))
        flow_bearing = float((np.degrees(np.arctan2(u, v))) % 360)
        # Relative canvas angle (-180 to +180)
        canvas_angle = float(
            (flow_bearing - geo["alongshore_right"] + 180) % 360 - 180
        )
        is_flood = abs(canvas_angle) <= 90.0
        signed_v = speed if is_flood else -speed

        records.append({
            "dt": t_dt,
            "time_str": t_dt.strftime("%H:%M"),
            "hour": t_dt.hour,
            "minute": t_dt.minute,
            "speed": speed,
            "signed_v": signed_v,
            "flow_bearing": flow_bearing,
            "canvas_angle": canvas_angle,
            "is_flood": is_flood,
        })

    ds.close()

    # 3. Detect tidal peaks & slack water
    flood_records = [r for r in records if r["is_flood"]]
    ebb_records = [r for r in records if not r["is_flood"]]

    pfc_rec = max(flood_records, key=lambda r: r["speed"]) if flood_records else None
    pec_rec = max(ebb_records, key=lambda r: r["speed"]) if ebb_records else None

    # Detect kenteringen (sign switches or minimal velocity)
    kentering_times = set()
    for i in range(1, len(records) - 1):
        prev_r, curr_r, next_r = records[i - 1], records[i], records[i + 1]
        if prev_r["is_flood"] != curr_r["is_flood"]:
            k_rec = curr_r if curr_r["speed"] < prev_r["speed"] else prev_r
            kentering_times.add(k_rec["time_str"])
        elif curr_r["speed"] < 0.10 and curr_r["speed"] <= prev_r["speed"] and curr_r["speed"] <= next_r["speed"]:
            kentering_times.add(curr_r["time_str"])

    y_start = 220
    dy = 19.5
    slots = []

    for i, r in enumerate(records):
        y = y_start + i * dy
        time_str = r["time_str"]
        m_int = r["minute"]
        h_int = r["hour"]

        is_pfc = (pfc_rec and time_str == pfc_rec["time_str"])
        is_pec = (pec_rec and time_str == pec_rec["time_str"])
        is_kentering = (time_str in kentering_times)

        slots.append({
            "time": time_str,
            "hour_label": f"{h_int}h" if m_int == 0 else None,
            "minute": m_int,
            "quarter_type": m_int // 15,
            "y": round(y, 1),
            "v": round(r["signed_v"], 2),
            "speed": round(r["speed"], 2),
            "angle": round(r["canvas_angle"], 1),
            "flow_bearing": round(r["flow_bearing"], 1),
            "h_taw": 2.5,  # Neutral placeholder pending MDK integration
            "is_pfc": is_pfc,
            "is_pec": is_pec,
            "is_kentering": is_kentering,
            "is_hw": False,
            "is_lw": False,
            "is_marked": is_pfc or is_pec or is_kentering,
        })

    layout = generate_layout(len(slots), v_max_mps=v_max_mps)

    # Format date and headlines
    dt_obj = datetime.strptime(target_date, "%Y-%m-%d")
    days_nl = ["Maandag", "Dinsdag", "Woensdag", "Donderdag", "Vrijdag", "Zaterdag", "Zondag"]
    months_nl = [
        "", "Januari", "Februari", "Maart", "April", "Mei", "Juni",
        "Juli", "Augustus", "September", "Oktober", "November", "December"
    ]
    date_formatted = f"{days_nl[dt_obj.weekday()]} {dt_obj.day} {months_nl[dt_obj.month]} {dt_obj.year}"

    pfc_str = f"{pfc_rec['time_str']} ({pfc_rec['speed']:.2f} m/s)" if pfc_rec else "--:--"
    pec_str = f"{pec_rec['time_str']} ({pec_rec['speed']:.2f} m/s)" if pec_rec else "--:--"
    k_str = ", ".join(sorted(kentering_times)) if kentering_times else "rond kentering"

    insight = {
        "headline": f'Piek Vloed: <tspan font-weight="800" fill="#0284c7">{pfc_str}</tspan> • Piek Eb: <tspan font-weight="800" fill="#4f46e5">{pec_str}</tspan>',
        "detail": f"Springtij-piek overschrijdt 1.0 m/s (kruissnelheid competitief zwemmer). Kenteringen om {k_str}. Berekend op open zee-cel ({cell['dist_m']:.0f}m offshore).",
    }

    elapsed_h = (len(slots) - 1) * 0.25

    return {
        "layout": layout,
        "meta": {
            "version": "v8",
            "project_title": "CSCM KUST-STROMINGSPROFIEL",
            "location_name": f"{geo['muni_name']} — Strandpost {geo['post_number']}",
            "date_str": date_formatted,
            "time_window": f"{start_time} – {end_time} ({elapsed_h:.1f}u Dagvenster)",
            "seaward_bearing_deg": geo["seaward_bearing"],
            "north_angle": geo["north_angle"],
            "coast_left_label": "[FR] FRANKRIJK • EBBESTROOM (ZW)",
            "coast_right_label": "VLOEDSTROOM (NO) • NEDERLAND [NL]",
            "source_label": f"CSCM • CMEMS 1.5km Open Zee ({cell['dist_m']:.0f}m offshore) &amp; MDK",
            "grid_cell": cell,
        },
        "slots": slots,
        "water_level": None,
        "insight": insight,
    }


def main():
    parser = argparse.ArgumentParser(description="Fetch CMEMS current data for coastal profile v8.")
    parser.add_argument("--date", default="2026-10-11", help="Target date YYYY-MM-DD")
    parser.add_argument("--start", default="07:30", help="Start time HH:MM")
    parser.add_argument("--end", default="20:30", help="End time HH:MM")
    parser.add_argument("--vmax", type=float, default=1.5, help="Maximum velocity on axis in m/s (default: 1.5)")
    parser.add_argument("--muni", default="bredene", help="Municipality key")
    parser.add_argument("--post", default="post_4", help="Post key")
    args = parser.parse_args()

    data = fetch_and_prepare_data(
        target_date=args.date,
        start_time=args.start,
        end_time=args.end,
        v_max_mps=args.vmax,
        municipality_key=args.muni,
        post_key=args.post,
    )

    with open(OUTPUT_YAML, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, sort_keys=False)

    print(f"Data retrieved and exported to: {OUTPUT_YAML}")
    print(f"Cell distance offshore: {data['meta']['grid_cell']['dist_m']:.0f}m")
    print(f"Axis v_max: {data['layout']['v_max_mps']} m/s (Scale: {data['layout']['scale_px_per_mps']} px/mps)")
    pfc = next((s for s in data["slots"] if s["is_pfc"]), None)
    if pfc:
        print(f"Peak Flood Current: {pfc['speed']} m/s at {pfc['time']}")


if __name__ == "__main__":
    main()
