#!/usr/bin/env python3
"""
Data Retrieval Script for Coastal Current Profile v12 (Multi-Station & Spring/Neap Comparison).

Supported Scenarios (v12 Suite):
- 12a: Bredene Strandpost 4 • Zaterdag 24 Okt 2026 • Springtij (Operational Forecast)
- 12b: Bredene Strandpost 4 • Zaterdag 17 Okt 2026 • Doodtij (Measured Gauge Observations)
- 12c: Nieuwpoort-Bad Post 2 • Zaterdag 24 Okt 2026 • Springtij (Operational Forecast)
- 12d: Nieuwpoort-Bad Post 2 • Zaterdag 17 Okt 2026 • Doodtij (Measured Gauge Observations)
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
from cscm.current.cmems.retrieve import CmemsCurrentManager
from cscm.tide.be.hic import HicClient

HIST_DIR = Path(__file__).resolve().parent
REPO_ROOT = HIST_DIR.parents[4]
YAML_PATH = REPO_ROOT / "src" / "cscm" / "resources" / "be-full-coast-locations.yaml"
CMEMS_DIR = REPO_ROOT / "src" / "cscm" / "current" / "cmems" / "data_store"

SCENARIO_CONFIGS = {
    "12a": {
        "muni_key": "bredene",
        "post_key": "post_4",
        "date": "2026-10-24",
        "station_code": "OST",
        "tide_lag_min": 7.0,
        "is_forecast": True,
        "regime_label": "Springtij (Verval ~4.5m)",
        "regime_color": "#0284c7",
        "post_display": "Bredene — Strandpost 4 (Droogen Opganck)",
        "title_size": 32,
    },
    "12b": {
        "muni_key": "bredene",
        "post_key": "post_4",
        "date": "2026-10-17",
        "station_code": "OST",
        "tide_lag_min": 7.0,
        "is_forecast": False,
        "regime_label": "Doodtij (Verval ~3.1m)",
        "regime_color": "#4f46e5",
        "post_display": "Bredene — Strandpost 4 (Droogen Opganck)",
        "title_size": 32,
    },
    "12c": {
        "muni_key": "nieuwpoort",
        "post_key": "post_2",
        "date": "2026-10-24",
        "station_code": "NPT",
        "tide_lag_min": 0.0,
        "is_forecast": True,
        "regime_label": "Springtij (Verval ~4.8m)",
        "regime_color": "#0284c7",
        "post_display": "Nieuwpoort-Bad — Strandpost 2 (Veurnestraat HP)",
        "title_size": 30,
    },
    "12d": {
        "muni_key": "nieuwpoort",
        "post_key": "post_2",
        "date": "2026-10-17",
        "station_code": "NPT",
        "tide_lag_min": 0.0,
        "is_forecast": False,
        "regime_label": "Doodtij (Verval ~3.3m)",
        "regime_color": "#4f46e5",
        "post_display": "Nieuwpoort-Bad — Strandpost 2 (Veurnestraat HP)",
        "title_size": 30,
    },
}


def find_or_retrieve_cmems_nc(target_dt: datetime) -> Path:
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

    print(f"Target date {target_dt.date()} not in local cache; updating via CmemsCurrentManager...")
    dm = CmemsCurrentManager()
    dm.update_cmems_data(limit=1)

    nc_files = sorted(CMEMS_DIR.glob("*.nc"))
    if not nc_files:
        raise FileNotFoundError(f"No NetCDF (.nc) files found in {CMEMS_DIR} after update")
    return nc_files[-1]


def load_post_config(municipality_key: str, post_key: str):
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
        "muni_name": muni.get("name", municipality_key.capitalize()),
        "post_name": post.get("name", post_key),
        "post_number": post.get("number", post.get("code", 1)),
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
            "flood_x": 495.0 + 0.5 * scale_px_per_mps,
            "ebb_x": 425.0 - 0.5 * scale_px_per_mps,
            "y": benchmark_y_bottom + 32.0,
            "bg": "#f0fdf4",
            "border": "#86efac",
            "color": "#16a34a",
        },
        {
            "speed": 1.0,
            "speed_str": "1.0 m/s",
            "kmh_str": "3.6 km/h",
            "label": "Getrainde zwemmer",
            "sub": "kustnorm",
            "flood_x": 495.0 + 1.0 * scale_px_per_mps,
            "ebb_x": 425.0 - 1.0 * scale_px_per_mps,
            "y": benchmark_y_bottom + 62.0,
            "bg": "#fefce8",
            "border": "#fde047",
            "color": "#ca8a04",
        },
        {
            "speed": 1.5,
            "speed_str": "1.5 m/s",
            "kmh_str": "5.4 km/h",
            "label": "Competitie / Redder",
            "sub": "elite",
            "flood_x": 495.0 + 1.5 * scale_px_per_mps,
            "ebb_x": 425.0 - 1.5 * scale_px_per_mps,
            "y": benchmark_y_bottom + 92.0,
            "bg": "#fef2f2",
            "border": "#fca5a5",
            "color": "#dc2626",
        },
    ]

    ticks = []
    benchmarks = []
    speed_steps = [0.25, 0.5, 0.75, 1.0, 1.25, 1.5]
    for spd in speed_steps:
        if spd <= v_max_mps + 0.01:
            ticks.append({
                "val": spd,
                "label": f"+{spd:.2f}" if spd != int(spd) else f"+{spd:.1f}",
                "x": round(495.0 + spd * scale_px_per_mps, 1),
            })
            ticks.append({
                "val": -spd,
                "label": f"-{spd:.2f}" if spd != int(spd) else f"-{spd:.1f}",
                "x": round(425.0 - spd * scale_px_per_mps, 1),
            })

    for spd, stroke, ebb_stroke, width in [
        (0.5, "#16a34a", "#16a34a", 1.2),
        (1.0, "#ca8a04", "#ca8a04", 1.4),
        (1.5, "#dc2626", "#dc2626", 1.2),
    ]:
        if spd <= v_max_mps + 0.01:
            benchmarks.append({
                "speed": spd,
                "flood_x": round(495.0 + spd * scale_px_per_mps, 1),
                "ebb_x": round(425.0 - spd * scale_px_per_mps, 1),
                "stroke": stroke,
                "ebb_stroke": ebb_stroke,
                "width": width,
            })

    callouts_bottom = swimmer_callouts[-1]["y"] + 24.0
    legend_y = round(callouts_bottom + 16.0, 1)
    footer_y = round(legend_y + 110.0 + 20.0, 1)
    total_height = round(footer_y + 30.0, 1)

    return {
        "n_slots": n_slots,
        "v_max_mps": v_max_mps,
        "scale_px_per_mps": round(scale_px_per_mps, 2),
        "flood_grad_x2": round(495.0 + v_max_mps * scale_px_per_mps, 1),
        "ebb_grad_x2": round(425.0 - v_max_mps * scale_px_per_mps, 1),
        "grid_y_bottom": round(y_end + 12.0, 1),
        "benchmark_y_bottom": round(benchmark_y_bottom, 1),
        "ticks": sorted(ticks, key=lambda t: t["x"]),
        "benchmarks": benchmarks,
        "swimmer_callouts": swimmer_callouts,
        "legend_y": legend_y,
        "footer_y": footer_y,
        "total_height": total_height,
    }


def fetch_and_prepare_variant(variant_key: str):
    cfg = SCENARIO_CONFIGS[variant_key]
    print(f"\n========================================================")
    print(f"Fetching Data for Variant {variant_key}: {cfg['post_display']}")
    print(f"Date: {cfg['date']} • {cfg['regime_label']}")
    print(f"========================================================")

    geo = load_post_config(cfg["muni_key"], cfg["post_key"])
    tz_local = ZoneInfo(geo["timezone"])

    start_time = "07:30"
    end_time = "20:30"
    target_date = cfg["date"]
    v_max_mps = 1.5

    dt_local_start = datetime.strptime(f"{target_date} {start_time}", "%Y-%m-%d %H:%M").replace(tzinfo=tz_local)
    dt_local_end = datetime.strptime(f"{target_date} {end_time}", "%Y-%m-%d %H:%M").replace(tzinfo=tz_local)
    tz_abbrev = dt_local_start.tzname() or "LT"

    dt_utc_start = dt_local_start.astimezone(timezone.utc)
    dt_utc_end = dt_local_end.astimezone(timezone.utc)

    # 1. CMEMS Current Data
    nc_path = find_or_retrieve_cmems_nc(dt_utc_start)
    print(f"Reading CMEMS dataset: {nc_path.name}")
    ds = xr.open_dataset(nc_path)
    cell = find_nearest_water_cell(ds, geo["lat"], geo["lon"])
    print(f"Selected offshore cell: idx=({cell['y_idx']}, {cell['x_idx']}), distance={cell['distance_m']:.0f}m")

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

    # 2. HIC Water Levels
    hic = HicClient()
    stn_code = cfg["station_code"]
    tide_lag_minutes = cfg["tide_lag_min"]
    is_forecast = cfg["is_forecast"]
    tide_src = "forecast" if is_forecast else "observed"

    print(f"Fetching HIC {tide_src} water levels for {stn_code}...")
    query_start = dt_utc_start - timedelta(hours=3)
    query_end = dt_utc_end + timedelta(hours=3)

    try:
        df_hic = hic.get_water_levels(stn_code, query_start, query_end, source=tide_src)
    except Exception as e:
        print(f"Primary tide query failed ({e}); falling back to astro...")
        df_hic = hic.get_water_levels(stn_code, query_start, query_end, source="astro")

    if df_hic.empty:
        print("Empty tide DataFrame, fallback to astro...")
        df_hic = hic.get_water_levels(stn_code, query_start, query_end, source="astro")

    df_hic = df_hic.sort_values(by="timestamp").reset_index(drop=True)
    hic_timestamps = np.array([ts.timestamp() for ts in df_hic["timestamp"]])
    hic_levels = df_hic["water_level_m_taw"].values

    # Interpolate water levels for each slot with alongshore lag
    for r in current_records:
        if len(hic_timestamps) > 1:
            t_eval = (r["dt_utc"] - timedelta(minutes=tide_lag_minutes)).timestamp()
            h_interp = float(np.interp(t_eval, hic_timestamps, hic_levels))
        else:
            h_interp = 2.45
        r["h_taw"] = round(h_interp, 2)

    # 3. Current Extrema & Kenteringen
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

    # 4. Build Slots and Water Curve Geometry
    y_start = 220.0
    dy = 19.5
    slots = []
    water_points = []
    msl = 2.45
    base_x = round(460.0 + (0.0 - msl) * 135.0, 1)

    for i, r in enumerate(current_records):
        y = round(y_start + i * dy, 1)
        time_str = r["time_str"]
        m_int = r["minute"]
        h_int = r["hour"]

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

    layout = generate_layout(len(slots), v_max_mps=v_max_mps)

    dt_obj = datetime.strptime(target_date, "%Y-%m-%d")
    days_nl = ["Maandag", "Dinsdag", "Woensdag", "Donderdag", "Vrijdag", "Zaterdag", "Zondag"]
    months_nl = [
        "", "Januari", "Februari", "Maart", "April", "Mei", "Juni",
        "Juli", "Augustus", "September", "Oktober", "November", "December"
    ]
    date_formatted = f"{days_nl[dt_obj.weekday()]} {dt_obj.day} {months_nl[dt_obj.month]} {dt_obj.year}"

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
    src_tide_label = "HIC KiWIS KT-Last" if is_forecast else "HIC KiWIS O.05 (meting)"
    src_comment = f"{stn_code} +{tide_lag_minutes:.0f}m" if tide_lag_minutes > 0 else f"{stn_code}"

    contract = {
        "layout": layout,
        "meta": {
            "version": f"v{variant_key}",
            "project_title": "CSCM KUST-STROMINGSPROFIEL (DAGVERWACHTING)",
            "location_name": cfg["post_display"],
            "title_size": cfg["title_size"],
            "date_str": date_formatted,
            "regime_label": cfg["regime_label"],
            "regime_color": cfg["regime_color"],
            "time_window": f"{start_time} – {end_time} {tz_abbrev} ({elapsed_h:.1f}u Dagvenster)",
            "timezone": geo["timezone"],
            "target_date": target_date,
            "seaward_bearing_deg": geo["seaward_bearing"],
            "north_angle": geo["north_angle"],
            "alongshore_right": geo["alongshore_right"],
            "alongshore_left": geo["alongshore_left"],
            "source_currents": f"CMEMS 1.5km 2D PT15M ({nc_path.name})",
            "source_water_levels": f"{src_tide_label} ({src_comment})",
            "source_label": f"Model: CMEMS 1.5km 2D PT15M • Getij: {src_tide_label} ({src_comment})",
            "selected_cell": cell,
        },
        "slots": slots,
        "water_level": water_level,
        "legend_events": legend_events,
    }

    yaml_out = HIST_DIR / f"data_to_plot_v{variant_key}.yaml"
    with open(yaml_out, "w", encoding="utf-8") as f:
        yaml.dump(contract, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
    print(f"Saved YAML data contract: {yaml_out}")
    return contract


def main():
    parser = argparse.ArgumentParser(description="Fetch data for Coastal Current Profile v12 Suite")
    parser.add_argument("--variant", choices=["12a", "12b", "12c", "12d", "all"], default="all")
    args = parser.parse_args()

    targets = ["12a", "12b", "12c", "12d"] if args.variant == "all" else [args.variant]
    for key in targets:
        fetch_and_prepare_variant(key)


if __name__ == "__main__":
    main()
