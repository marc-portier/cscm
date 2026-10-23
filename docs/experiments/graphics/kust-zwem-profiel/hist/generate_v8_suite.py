#!/usr/bin/env python3
"""
Coastal Swim Trajectory Profile Suite v8 (Sat 24 Oct 2026).

Unified architecture generating 5 operational scenarios from one single pipeline:
- 8a: Bredene P4 ➔ Vosseslag ➔ Bredene P4 (6.0 km) • Start 09:00 CEST (Ochtend Kentering & Vroege Vloed)
- 8b: Bredene P4 ➔ Vosseslag ➔ Bredene P4 (6.0 km) • Start 13:00 CEST (Piekvloed Heen & Kentering Terug)
- 8c: Bredene P4 ➔ Vosseslag ➔ Bredene P4 (6.0 km) • Start 17:00 CEST (Eb Tegenstroom Heen & Eb-Surf Terug)
- 8d: Nieuwpoort-Bad ➔ Oostende Kursaal (15.0 km) • Start 10:30 CEST (Piekvloed-Surf • Point-to-Point)
- 8e: De Panne Leopold I ➔ Oostende Kursaal (30.0 km) • Start 09:00 CEST (Volledige Vloed-Expeditie • Point-to-Point)

Key Design Features:
- Universal 8-Leg Visual Rhythm across both return and point-to-point journeys.
- Spine Current Ribs ("stromingsgraten") on every checkpoint spine at 10-minute intervals.
- Full-scale vector balance cards spanning underneath each leg.
- Finish table ordered from fastest (1.4 m/s, top, blue) to slowest (0.6 m/s, bottom, orange).
- Start-window impact (+/- 30 min) quantified at the finish.
- 10-Minute Isochrones with clean boundary labeling.
- Discrete 25m alongshore kinematics using real CMEMS currents and HIC KiWIS forecast.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import argparse
import math
import subprocess
import sys
import numpy as np
import pandas as pd
import yaml

HIST_DIR = Path(__file__).resolve().parent
if str(HIST_DIR) not in sys.path:
    sys.path.insert(0, str(HIST_DIR))

from cscm.broker import get_broker
from kinematics import AlongshoreTrajectoryCalculator, Checkpoint


def poly_to_path(pts):
    if not pts:
        return ""
    return "M " + " L ".join(f"{p[0]:.1f} {p[1]:.1f}" for p in pts)


def format_duration_h_mm(min_val: float) -> str:
    h = int(min_val // 60)
    m = int(round(min_val % 60))
    if m == 60:
        h += 1
        m = 0
    if h > 0:
        return f"{h}u{m:02d}'"
    return f"{m}'"


def format_delta_h_mm(delta_m: float) -> str:
    sign = "+" if delta_m > 0.05 else ("-" if delta_m < -0.05 else "")
    abs_m = abs(delta_m)
    h = int(abs_m // 60)
    m = int(round(abs_m % 60))
    if m == 60:
        h += 1
        m = 0
    if h > 0:
        return f"{sign}{h}:{m:02d}'"
    elif abs_m > 0.05:
        return f"{sign}{m}'"
    return "0'"


SCENARIOS = {
    "8a": {
        "is_return": True,
        "title": "Traject: Bredene Post 4 ➔ Vosseslag ➔ Bredene Post 4 (6.0 km)",
        "subtitle": "Zaterdag 24 Oktober 2026 • Start 09:00 CEST (Ochtend Kentering & Vroege Vloed • Gebalanceerd) • 10' Isochronen",
        "theme": "Ochtend Kentering & Vroege Vloed • Gebalanceerd",
        "start_time_cest": "09:00",
        "start_hour_utc": 7,
        "start_min_utc": 0,
        "total_distance_km": 6.0,
        "turn_km": 3.0,
        "raw_checkpoints": [
            ("Bredene P4 (Start)",   0.00, 51.24989, 2.96226, "out",      105),
            ("",                     0.75, 51.25330, 2.97156, "out",      230),
            ("",                     1.50, 51.25721, 2.98033, "out",      355),
            ("",                     2.25, 51.26129, 2.98890, "out",      480),
            ("Vosseslag (Aankomst)", 3.00, 51.26538, 2.99748, "out_turn", 605),
            ("Vosseslag (Vertrek)",  3.00, 51.26538, 2.99748, "ret_turn", 685),
            ("",                     3.75, 51.26129, 2.98890, "ret",      810),
            ("",                     4.50, 51.25721, 2.98033, "ret",      935),
            ("",                     5.25, 51.25330, 2.97156, "ret",      1060),
            ("Bredene P4 (Finish)",  6.00, 51.24989, 2.96226, "ret",      1185),
        ],
    },
    "8b": {
        "is_return": True,
        "title": "Traject: Bredene Post 4 ➔ Vosseslag ➔ Bredene Post 4 (6.0 km)",
        "subtitle": "Zaterdag 24 Oktober 2026 • Start 13:00 CEST (Piekvloed Heenweg & Kentering Terugweg • Snelle Heenweg) • 10' Isochronen",
        "theme": "Piekvloed Heenweg & Kentering Terugweg • Snelle Heenweg",
        "start_time_cest": "13:00",
        "start_hour_utc": 11,
        "start_min_utc": 0,
        "total_distance_km": 6.0,
        "turn_km": 3.0,
        "raw_checkpoints": [
            ("Bredene P4 (Start)",   0.00, 51.24989, 2.96226, "out",      105),
            ("",                     0.75, 51.25330, 2.97156, "out",      230),
            ("",                     1.50, 51.25721, 2.98033, "out",      355),
            ("",                     2.25, 51.26129, 2.98890, "out",      480),
            ("Vosseslag (Aankomst)", 3.00, 51.26538, 2.99748, "out_turn", 605),
            ("Vosseslag (Vertrek)",  3.00, 51.26538, 2.99748, "ret_turn", 685),
            ("",                     3.75, 51.26129, 2.98890, "ret",      810),
            ("",                     4.50, 51.25721, 2.98033, "ret",      935),
            ("",                     5.25, 51.25330, 2.97156, "ret",      1060),
            ("Bredene P4 (Finish)",  6.00, 51.24989, 2.96226, "ret",      1185),
        ],
    },
    "8c": {
        "is_return": True,
        "title": "Traject: Bredene Post 4 ➔ Vosseslag ➔ Bredene Post 4 (6.0 km)",
        "subtitle": "Zaterdag 24 Oktober 2026 • Start 17:00 CEST (Eb Tegenstroom Heen & Eb-Surf Terug • Snelle Terugweg) • 10' Isochronen",
        "theme": "Eb Tegenstroom Heen & Eb-Surf Terug • Snelle Terugweg",
        "start_time_cest": "17:00",
        "start_hour_utc": 15,
        "start_min_utc": 0,
        "total_distance_km": 6.0,
        "turn_km": 3.0,
        "raw_checkpoints": [
            ("Bredene P4 (Start)",   0.00, 51.24989, 2.96226, "out",      105),
            ("",                     0.75, 51.25330, 2.97156, "out",      230),
            ("",                     1.50, 51.25721, 2.98033, "out",      355),
            ("",                     2.25, 51.26129, 2.98890, "out",      480),
            ("Vosseslag (Aankomst)", 3.00, 51.26538, 2.99748, "out_turn", 605),
            ("Vosseslag (Vertrek)",  3.00, 51.26538, 2.99748, "ret_turn", 685),
            ("",                     3.75, 51.26129, 2.98890, "ret",      810),
            ("",                     4.50, 51.25721, 2.98033, "ret",      935),
            ("",                     5.25, 51.25330, 2.97156, "ret",      1060),
            ("Bredene P4 (Finish)",  6.00, 51.24989, 2.96226, "ret",      1185),
        ],
    },
    "8d": {
        "is_return": False,
        "title": "Traject: Nieuwpoort-Bad ➔ Oostende Kursaal (15.0 km • Point-to-Point)",
        "subtitle": "Zaterdag 24 Oktober 2026 • Start 10:30 CEST (Piekvloed-Surf • Springtij Verval ~4.8m) • 10' Isochronen",
        "theme": "Nieuwpoort ➔ Oostende (15k) • Optimale Piekvloed-Surf",
        "start_time_cest": "10:30",
        "start_hour_utc": 8,
        "start_min_utc": 30,
        "total_distance_km": 15.0,
        "turn_km": None,
        # 8 legs of 1.875 km (9 checkpoints across 1080px track)
        "raw_checkpoints": [
            ("Nieuwpoort P2 (Start)",    0.00,  51.1492, 2.7165, "out", 105.0),
            ("Lombardsijde Strand",      1.88,  51.1710, 2.7560, "out", 240.0),
            ("Westende P12",             3.75,  51.1715, 2.7743, "out", 375.0),
            ("Middelkerke Krokodiel",    5.62,  51.1772, 2.7880, "out", 510.0),
            ("Middelkerke Casino",       7.50,  51.1873, 2.8109, "out", 645.0),
            ("Middelkerke Carlton",      9.38,  51.1920, 2.8230, "out", 780.0),
            ("Raversijde P1",           11.25,  51.2077, 2.8594, "out", 915.0),
            ("Mariakerke P4",           13.12,  51.2189, 2.8827, "out", 1050.0),
            ("Oostende Kursaal (Finish)",15.00, 51.2321, 2.9101, "out", 1185.0),
        ],
    },
    "8e": {
        "is_return": False,
        "title": "Traject: De Panne Leopold I ➔ Oostende Kursaal (30.0 km • Point-to-Point)",
        "subtitle": "Zaterdag 24 Oktober 2026 • Start 09:00 CEST (Volledige Vloed-Expeditie • Springtij Verval ~4.8m) • 10' Isochronen",
        "theme": "De Panne ➔ Oostende (30k) • Maximale Vloed-Benutting",
        "start_time_cest": "09:00",
        "start_hour_utc": 7,
        "start_min_utc": 0,
        "total_distance_km": 30.0,
        "turn_km": None,
        # 8 legs of 3.75 km (9 checkpoints across 1080px track)
        "raw_checkpoints": [
            ("De Panne R1 (Start)",      0.00,  51.1001, 2.5781, "out", 105.0),
            ("Sint-Idesbald P1",         3.75,  51.1121, 2.6111, "out", 240.0),
            ("Koksijde Zouaven",         7.50,  51.1235, 2.6381, "out", 375.0),
            ("Oostduinkerke P8",        11.25,  51.1352, 2.6748, "out", 510.0),
            ("Nieuwpoort P1",           15.00,  51.1506, 2.7196, "out", 645.0),
            ("Westende Rotonde",        18.75,  51.1750, 2.7827, "out", 780.0),
            ("Middelkerke Silt",        22.50,  51.1890, 2.8148, "out", 915.0),
            ("Raversijde P1",           26.25,  51.2077, 2.8594, "out", 1050.0),
            ("Oostende Kursaal (Finish)",30.00, 51.2321, 2.9101, "out", 1185.0),
        ],
    },
}


def generate_variant(var_id: str):
    cfg = SCENARIOS[var_id]
    print("=" * 72)
    print(f"CSCM Kustzwem-Profiel Suite v{var_id}")
    print(f"{cfg['title']}")
    print(f"{cfg['subtitle']}")
    print("=" * 72)

    is_return = cfg["is_return"]
    t_start_utc = datetime(2026, 10, 24, cfg["start_hour_utc"], cfg["start_min_utc"], tzinfo=timezone.utc)
    t_end_query = datetime(2026, 10, 24, 23, 0, tzinfo=timezone.utc)

    broker = get_broker()

    # 1. Geometry & Coordinate Setup
    width = 1420
    height = 1004
    y_spine_top = 170.0
    y_spine_bottom = 790.0
    scale_v = 40.0
    iso_step_min = 10

    raw_checkpoints = cfg["raw_checkpoints"]
    tot_km = cfg["total_distance_km"]

    checkpoints_yaml = []
    kinematics_cps_out = []
    kinematics_cps_ret = []

    if is_return:
        x_heen = [105.0, 230.0, 355.0, 480.0, 605.0]
        x_terug = [685.0, 810.0, 935.0, 1060.0, 1185.0]
        x_mid_turn = 645.0

        def s_to_x_heen(s_km: float) -> float:
            return 105.0 + (s_km / 3.0) * (605.0 - 105.0)

        def s_to_x_terug(s_km: float) -> float:
            return 685.0 + ((3.0 - s_km) / 3.0) * (1185.0 - 685.0)

        for idx, (name, km_tot, lat, lon, leg, x_pos) in enumerate(raw_checkpoints):
            s_km = km_tot if km_tot <= 3.0 else (6.0 - km_tot)
            checkpoints_yaml.append({
                "idx": idx,
                "km_tot": f"{km_tot:.2f}",
                "label": f"{km_tot:.2f} km",
                "name": name,
                "s_km": float(s_km),
                "lat": lat,
                "lon": lon,
                "leg": leg,
                "x": float(x_pos),
            })
            cp_obj = Checkpoint(idx=idx, name=name or f"CP {idx}", s_km=float(s_km), lat=lat, lon=lon)
            if idx <= 4:
                kinematics_cps_out.append(cp_obj)
            else:
                kinematics_cps_ret.append(cp_obj)

    else:
        # Point-to-Point (8 legs, 9 checkpoints across x=105 to x=1185)
        x_start = 105.0
        x_finish = 1185.0
        track_width = x_finish - x_start

        def s_to_x_p2p(s_km: float) -> float:
            return x_start + (s_km / tot_km) * track_width

        for idx, (name, s_km, lat, lon, leg, x_pos) in enumerate(raw_checkpoints):
            checkpoints_yaml.append({
                "idx": idx,
                "km_tot": f"{s_km:.2f}",
                "label": f"{s_km:.1f} km",
                "name": name,
                "s_km": float(s_km),
                "lat": lat,
                "lon": lon,
                "leg": leg,
                "x": float(x_pos),
            })
            kinematics_cps_out.append(Checkpoint(idx=idx, name=name, s_km=float(s_km), lat=lat, lon=lon))

    # 2. HIC KiWIS Tide Extremes
    tide_res = broker.query(
        "tide",
        station="OST",
        start_time=datetime(2026, 10, 24, 6, 0, tzinfo=timezone.utc),
        end_time=t_end_query,
        source="forecast",
        time_offset_minutes=0.0,
    )
    df_tide = tide_res.to_dataframe()
    hw_row = df_tide.loc[df_tide["water_level_m_taw"].idxmax()]
    lw_row = df_tide.loc[df_tide["water_level_m_taw"].idxmin()]
    hw_local = hw_row.timestamp + pd.Timedelta(hours=2)
    lw_local = lw_row.timestamp + pd.Timedelta(hours=2)

    # 3. CMEMS Currents
    coords_unique = list(set((cp["lat"], cp["lon"]) for cp in checkpoints_yaml))
    curr_res = broker.query(
        "current",
        positions=coords_unique,
        start_time=t_start_utc - timedelta(hours=1),
        end_time=t_end_query,
        avoid_boundary_damping=True,
    )
    df_curr = curr_res.to_dataframe()
    unique_cells = df_curr[["lat", "lon"]].drop_duplicates().values

    def current_lookup_fn(lat: float, lon: float, t_utc: datetime) -> tuple[float, float]:
        dists = [math.hypot(lat - c[0], lon - c[1]) for c in unique_cells]
        best_cell = unique_cells[int(np.argmin(dists))]
        sub = df_curr[(df_curr["lat"] == best_cell[0]) & (df_curr["lon"] == best_cell[1])].sort_values("timestamp")
        if sub.empty:
            return (0.0, 0.0)

        times_sec = sub["timestamp"].apply(lambda t: t.timestamp()).values
        target_sec = t_utc.timestamp()
        u_east = float(np.interp(target_sec, times_sec, sub["current_speed_eastward_m_s"].values))
        v_north = float(np.interp(target_sec, times_sec, sub["current_speed_northward_m_s"].values))
        return (u_east, v_north)

    # 4. Alongshore Kinematics for Nominal Swimmer (1.0 m/s)
    calc_out = AlongshoreTrajectoryCalculator(checkpoints=kinematics_cps_out, ds_step_m=25.0)

    if is_return:
        traj_out_nom = calc_out.calculate_trajectory(1.0, t_start_utc, current_lookup_fn)
        calc_ret = AlongshoreTrajectoryCalculator(checkpoints=kinematics_cps_ret, ds_step_m=25.0)
        traj_ret_nom = calc_ret.calculate_trajectory(1.0, traj_out_nom.finish_time_utc, current_lookup_fn)

        total_nominal_sec = traj_out_nom.total_duration_sec + traj_ret_nom.total_duration_sec
        total_nominal_min = total_nominal_sec / 60.0
        nominal_finish_utc = traj_ret_nom.finish_time_utc
        all_legs_nom = traj_out_nom.legs + traj_ret_nom.legs

        # Reference swimmer interpolation
        s_heen_ref = [p[0] for p in traj_out_nom.trajectory_points]
        t_heen_ref = [(p[1] - t_start_utc).total_seconds() / 60.0 for p in traj_out_nom.trajectory_points]
        s_terug_ref = [p[0] for p in traj_ret_nom.trajectory_points]
        t_terug_ref = [(p[1] - t_start_utc).total_seconds() / 60.0 for p in traj_ret_nom.trajectory_points]
        s_terug_rev = list(reversed(s_terug_ref))
        t_terug_rev = list(reversed(t_terug_ref))

        def get_t_ref_heen(s_km: float) -> float:
            return float(np.interp(s_km, s_heen_ref, t_heen_ref))

        def get_t_ref_terug(s_km: float) -> float:
            return float(np.interp(s_km, s_terug_rev, t_terug_rev))

        nominal_cp_times = traj_out_nom.checkpoint_times_utc + traj_ret_nom.checkpoint_times_utc

    else:
        traj_nom = calc_out.calculate_trajectory(1.0, t_start_utc, current_lookup_fn)
        total_nominal_sec = traj_nom.total_duration_sec
        total_nominal_min = total_nominal_sec / 60.0
        nominal_finish_utc = traj_nom.finish_time_utc
        all_legs_nom = traj_nom.legs

        s_ref = [p[0] for p in traj_nom.trajectory_points]
        t_ref = [(p[1] - t_start_utc).total_seconds() / 60.0 for p in traj_nom.trajectory_points]

        def get_t_ref_p2p(s_km: float) -> float:
            return float(np.interp(s_km, s_ref, t_ref))

        nominal_cp_times = traj_nom.checkpoint_times_utc

    nominal_finish_local = nominal_finish_utc + timedelta(hours=2)
    print(f"  Nominal (1.0 m/s): {total_nominal_min:.1f} min ({total_nominal_min/60:.2f} h) | Finish: {nominal_finish_local.strftime('%H:%M')} CEST")

    # 5. Fast Trajectory Scan Across 9 Speeds
    fan_speeds = [0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4]
    deltas = []
    fan_trajs = {}

    for v in fan_speeds:
        if is_return:
            t_o = calc_out.calculate_trajectory(v, t_start_utc, current_lookup_fn)
            t_r = calc_ret.calculate_trajectory(v, t_o.finish_time_utc, current_lookup_fn)
            tot_sec = t_o.total_duration_sec + t_r.total_duration_sec
            delta_m = (tot_sec - total_nominal_sec) / 60.0
            deltas.append(delta_m)
            fan_trajs[v] = (t_o, t_r, tot_sec)
        else:
            t_v = calc_out.calculate_trajectory(v, t_start_utc, current_lookup_fn)
            tot_sec = t_v.total_duration_sec
            delta_m = (tot_sec - total_nominal_sec) / 60.0
            deltas.append(delta_m)
            fan_trajs[v] = (t_v, tot_sec)

    max_up_min = max(35.0, abs(min(deltas)), 30.0)
    max_down_min = max(35.0, max(deltas), 30.0)
    total_time_spread = max_up_min + max_down_min
    pad_top = 22.0
    pad_bottom = 22.0
    H_avail = y_spine_bottom - y_spine_top - (pad_top + pad_bottom)  # 576.0 px

    scale_t = min(5.0, H_avail / total_time_spread)
    slack = H_avail - total_time_spread * scale_t
    y_ref = (y_spine_top + pad_top + slack / 2.0) + max_up_min * scale_t
    print(f"  Calibrated scale_t = {scale_t:.2f} px/min, dynamic y_ref = {y_ref:.1f} (delta range: {min(deltas):+.1f} to {max(deltas):+.1f} min)")

    # 6. Nominal Schedule
    nominal_schedule_yaml = []
    nom_times_min = []
    for cp, cp_time_utc in zip(checkpoints_yaml, nominal_cp_times):
        loc_time = cp_time_utc + timedelta(hours=2)
        t_min = (cp_time_utc - t_start_utc).total_seconds() / 60.0
        nom_times_min.append(t_min)
        nominal_schedule_yaml.append({
            "km": cp["label"],
            "name": cp["name"],
            "time": loc_time.strftime("%H:%M"),
            "t_min": round(t_min, 1),
        })

    # 7. Leg Breakdown (8 Legs for ALL variants)
    leg_breakdown_yaml = []
    for idx, leg in enumerate(all_legs_nom):
        leg_idx = idx + 1
        leg_t_start_min = (leg.t_start_utc - t_start_utc).total_seconds() / 60.0
        leg_t_end_min = (leg.t_end_utc - t_start_utc).total_seconds() / 60.0
        direction = "out" if (is_return and leg_idx <= 4) or not is_return else "ret"
        leg_breakdown_yaml.append({
            "leg_idx": leg_idx,
            "name": f"Leg {leg_idx}/8",
            "direction": direction,
            "from_km": float(leg.from_km),
            "to_km": float(leg.to_km),
            "t_start_min": float(leg_t_start_min),
            "t_end_min": float(leg_t_end_min),
            "dt_min": float(leg.dt_min),
            "dist_swimmer_m": float(leg.dist_swimmer_m),
            "dist_current_m": float(leg.dist_current_m),
            "u_avg_mps": float(leg.u_avg_mps),
            "is_tailwind": bool(leg.is_tailwind),
            "is_flood": bool(leg.is_flood),
        })

    # 8. Curves for 9-isotach fan
    fan_colors = {
        0.6: "#ea580c", 0.7: "#f97316", 0.8: "#f59e0b", 0.9: "#84cc16",
        1.0: "#16a34a", 1.1: "#10b981", 1.2: "#06b6d4", 1.3: "#0ea5e9", 1.4: "#2563eb",
    }
    speeds_analyzed_yaml = []
    curves_yaml = []

    for v in fan_speeds:
        delta_m = (fan_trajs[v][-1] - total_nominal_sec) / 60.0
        tot_min = fan_trajs[v][-1] / 60.0
        delta_str = format_delta_h_mm(delta_m)

        if is_return:
            t_o, t_r, tot_sec = fan_trajs[v]
            fin_local = t_r.finish_time_utc + timedelta(hours=2)

            pts_heen = []
            for s_km, t_utc in t_o.trajectory_points:
                t_val = (t_utc - t_start_utc).total_seconds() / 60.0
                t_r_ref = get_t_ref_heen(s_km)
                px = s_to_x_heen(s_km)
                py = min(y_spine_bottom - 6.0, max(y_spine_top, y_ref + (t_val - t_r_ref) * scale_t))
                pts_heen.append([round(px, 1), round(py, 1)])

            pts_terug = []
            for s_km, t_utc in t_r.trajectory_points:
                t_val = (t_utc - t_start_utc).total_seconds() / 60.0
                t_r_ref = get_t_ref_terug(s_km)
                px = s_to_x_terug(s_km)
                py = min(y_spine_bottom - 6.0, max(y_spine_top, y_ref + (t_val - t_r_ref) * scale_t))
                pts_terug.append([round(px, 1), round(py, 1)])

            curves_yaml.append({
                "speed_mps": float(v),
                "color": fan_colors[v],
                "lw": 3.0 if v == 1.0 else 1.5,
                "opacity": 1.0 if v == 1.0 else 0.88,
                "pts_heen": pts_heen,
                "pts_terug": pts_terug,
                "last_py": min(y_spine_bottom - 8.0, pts_terug[-1][1] if pts_terug else y_ref),
            })
        else:
            t_v, tot_sec = fan_trajs[v]
            fin_local = t_v.finish_time_utc + timedelta(hours=2)

            pts = []
            for s_km, t_utc in t_v.trajectory_points:
                t_val = (t_utc - t_start_utc).total_seconds() / 60.0
                t_r_ref = get_t_ref_p2p(s_km)
                px = s_to_x_p2p(s_km)
                py = min(y_spine_bottom - 6.0, max(y_spine_top, y_ref + (t_val - t_r_ref) * scale_t))
                pts.append([round(px, 1), round(py, 1)])

            curves_yaml.append({
                "speed_mps": float(v),
                "color": fan_colors[v],
                "lw": 3.0 if v == 1.0 else 1.5,
                "opacity": 1.0 if v == 1.0 else 0.88,
                "pts": pts,
                "last_py": min(y_spine_bottom - 8.0, pts[-1][1] if pts else y_ref),
            })

        speeds_analyzed_yaml.append({
            "speed_mps": float(v),
            "color": fan_colors[v],
            "eta_finish": fin_local.strftime("%H:%M"),
            "delta_min": delta_str,
            "total_time_min": round(tot_min, 1),
            "total_time_str": format_duration_h_mm(tot_min),
        })

    # Sort speeds analyzed from fastest (1.4 m/s) to slowest (0.6 m/s) to match visual curve order!
    speeds_table_ordered = sorted(speeds_analyzed_yaml, key=lambda s: s["speed_mps"], reverse=True)

    # 9. Starttijd-Venster (±30 min)
    t_start_early = t_start_utc - timedelta(minutes=30)
    t_start_late = t_start_utc + timedelta(minutes=30)

    if is_return:
        t_out_early = calc_out.calculate_trajectory(1.0, t_start_early, current_lookup_fn)
        t_ret_early = calc_ret.calculate_trajectory(1.0, t_out_early.finish_time_utc, current_lookup_fn)
        t_out_late = calc_out.calculate_trajectory(1.0, t_start_late, current_lookup_fn)
        t_ret_late = calc_ret.calculate_trajectory(1.0, t_out_late.finish_time_utc, current_lookup_fn)

        fin_early_local = t_ret_early.finish_time_utc + timedelta(hours=2)
        fin_late_local = t_ret_late.finish_time_utc + timedelta(hours=2)
        tot_early_sec = t_out_early.total_duration_sec + t_ret_early.total_duration_sec
        tot_late_sec = t_out_late.total_duration_sec + t_ret_late.total_duration_sec

        env_heen_top = [[round(s_to_x_heen(s_km), 1), round(y_ref + ((t_utc - t_start_utc).total_seconds()/60.0 - get_t_ref_heen(s_km)) * scale_t, 1)] for s_km, t_utc in t_out_early.trajectory_points]
        env_heen_bot = [[round(s_to_x_heen(s_km), 1), round(y_ref + ((t_utc - t_start_utc).total_seconds()/60.0 - get_t_ref_heen(s_km)) * scale_t, 1)] for s_km, t_utc in t_out_late.trajectory_points]
        env_terug_top = [[round(s_to_x_terug(s_km), 1), round(y_ref + ((t_utc - t_start_utc).total_seconds()/60.0 - get_t_ref_terug(s_km)) * scale_t, 1)] for s_km, t_utc in t_ret_early.trajectory_points]
        env_terug_bot = [[round(s_to_x_terug(s_km), 1), round(y_ref + ((t_utc - t_start_utc).total_seconds()/60.0 - get_t_ref_terug(s_km)) * scale_t, 1)] for s_km, t_utc in t_ret_late.trajectory_points]

        poly_env_heen = " ".join(f"{p[0]},{p[1]}" for p in env_heen_top) + " " + " ".join(f"{p[0]},{p[1]}" for p in reversed(env_heen_bot))
        poly_env_terug = " ".join(f"{p[0]},{p[1]}" for p in env_terug_top) + " " + " ".join(f"{p[0]},{p[1]}" for p in reversed(env_terug_bot))

        envelope_yaml = {
            "poly_env_heen": poly_env_heen,
            "poly_env_terug": poly_env_terug,
            "env_heen_top": env_heen_top,
            "env_heen_bot": env_heen_bot,
            "env_terug_top": env_terug_top,
            "env_terug_bot": env_terug_bot,
            "fin_early_time": fin_early_local.strftime("%H:%M"),
            "fin_late_time": fin_late_local.strftime("%H:%M"),
            "fin_early_delta_str": format_delta_h_mm((tot_early_sec - total_nominal_sec) / 60.0),
            "fin_late_delta_str": format_delta_h_mm((tot_late_sec - total_nominal_sec) / 60.0),
        }
    else:
        t_early = calc_out.calculate_trajectory(1.0, t_start_early, current_lookup_fn)
        t_late = calc_out.calculate_trajectory(1.0, t_start_late, current_lookup_fn)

        fin_early_local = t_early.finish_time_utc + timedelta(hours=2)
        fin_late_local = t_late.finish_time_utc + timedelta(hours=2)
        tot_early_sec = t_early.total_duration_sec
        tot_late_sec = t_late.total_duration_sec

        env_top = [[round(s_to_x_p2p(s_km), 1), round(y_ref + ((t_utc - t_start_utc).total_seconds()/60.0 - get_t_ref_p2p(s_km)) * scale_t, 1)] for s_km, t_utc in t_early.trajectory_points]
        env_bot = [[round(s_to_x_p2p(s_km), 1), round(y_ref + ((t_utc - t_start_utc).total_seconds()/60.0 - get_t_ref_p2p(s_km)) * scale_t, 1)] for s_km, t_utc in t_late.trajectory_points]
        poly_env = " ".join(f"{p[0]},{p[1]}" for p in env_top) + " " + " ".join(f"{p[0]},{p[1]}" for p in reversed(env_bot))

        envelope_yaml = {
            "poly_env": poly_env,
            "env_top": env_top,
            "env_bot": env_bot,
            "fin_early_time": fin_early_local.strftime("%H:%M"),
            "fin_late_time": fin_late_local.strftime("%H:%M"),
            "fin_early_delta_str": format_delta_h_mm((tot_early_sec - total_nominal_sec) / 60.0),
            "fin_late_delta_str": format_delta_h_mm((tot_late_sec - total_nominal_sec) / 60.0),
        }

    # 10. Isochrones (10-Minute Resolution)
    isochrones_yaml = []
    iso_max_m = int(math.ceil(max(deltas) + total_nominal_min + 35.0))

    if is_return:
        s_fine_heen = np.linspace(0.0, 3.0, 60)
        s_fine_terug = np.linspace(3.0, 0.0, 60)
        for m in range(-30, iso_max_m, iso_step_min):
            t_clock_utc = t_start_utc + timedelta(minutes=m)
            t_clock_local = t_clock_utc + timedelta(hours=2)
            t_label = t_clock_local.strftime("%H:%M")

            pts_h = []
            for s_km in s_fine_heen:
                t_r = get_t_ref_heen(float(s_km))
                py = y_ref + (m - t_r) * scale_t
                px = s_to_x_heen(float(s_km))
                if y_spine_top - 4.0 <= py <= y_spine_bottom + 4.0:
                    pts_h.append([round(px, 1), round(py, 1)])

            pts_t = []
            for s_km in s_fine_terug:
                t_r = get_t_ref_terug(float(s_km))
                py = y_ref + (m - t_r) * scale_t
                px = s_to_x_terug(float(s_km))
                if y_spine_top - 4.0 <= py <= y_spine_bottom + 4.0:
                    pts_t.append([round(px, 1), round(py, 1)])

            py_turn = y_ref + (m - t_heen_ref[-1]) * scale_t
            has_turn_bridge = bool((len(pts_h) > 0 and len(pts_t) > 0) and (y_spine_top <= py_turn <= y_spine_bottom))

            if len(pts_h) >= 2 or len(pts_t) >= 2:
                isochrones_yaml.append({
                    "time": t_label,
                    "minute_rel": m,
                    "pts_h": pts_h,
                    "pts_t": pts_t,
                    "py_turn": round(py_turn, 1),
                    "has_turn_bridge": has_turn_bridge,
                })
    else:
        s_fine = np.linspace(0.0, tot_km, 120)
        for m in range(-30, iso_max_m, iso_step_min):
            t_clock_utc = t_start_utc + timedelta(minutes=m)
            t_clock_local = t_clock_utc + timedelta(hours=2)
            t_label = t_clock_local.strftime("%H:%M")

            pts = []
            for s_km in s_fine:
                t_r = get_t_ref_p2p(float(s_km))
                py = y_ref + (m - t_r) * scale_t
                px = s_to_x_p2p(float(s_km))
                if y_spine_top - 4.0 <= py <= y_spine_bottom + 4.0:
                    pts.append([round(px, 1), round(py, 1)])

            if len(pts) >= 2:
                isochrones_yaml.append({
                    "time": t_label,
                    "minute_rel": m,
                    "pts": pts,
                })

    # 11. Vertical Current Staven along Spines ("Stromingsgraten")
    spine_data_yaml = []
    for cp_idx, cp in enumerate(checkpoints_yaml):
        cx = cp["x"]
        lat = cp["lat"]
        lon = cp["lon"]
        t_nom = nom_times_min[cp_idx]
        is_out = cp["leg"] in ["out", "out_turn"]

        bars = []
        for m in range(-30, iso_max_m, iso_step_min):
            py = y_ref + (m - t_nom) * scale_t
            if y_spine_top <= py <= y_spine_bottom:
                t_sample_utc = t_start_utc + timedelta(minutes=m)
                u_east, v_north = current_lookup_fn(lat, lon, t_sample_utc)

                bearing = 65.0 if is_out else 245.0
                u_fwd = calc_out.project_current_alongshore(u_east, v_north, bearing)
                u_raw = calc_out.project_current_alongshore(u_east, v_north, 65.0)

                is_nominal = bool(abs(py - y_ref) < 3.5)
                is_flood = bool(u_raw >= 0)
                base_col = "#0284c7" if is_flood else "#4338ca"
                bar_len = abs(u_fwd) * scale_v

                if u_fwd >= 0:
                    x_b = cx
                else:
                    x_b = cx - bar_len

                bars.append({
                    "clock_min": m,
                    "py": round(py, 1),
                    "u_fwd": round(float(u_fwd), 3),
                    "u_raw": round(float(u_raw), 3),
                    "is_nominal": is_nominal,
                    "is_out": is_out,
                    "is_flood": is_flood,
                    "base_col": base_col,
                    "bar_len": round(float(bar_len), 1),
                    "x_b": round(float(x_b), 1),
                })

        spine_data_yaml.append({
            "idx": cp_idx,
            "checkpoint": cp,
            "cx": cx,
            "t_nom": round(t_nom, 1),
            "bars": bars,
        })

    # 12. Write YAML Data Contract
    contract_data = {
        "meta": {
            "variant": var_id,
            "title": cfg["title"],
            "subtitle": cfg["subtitle"],
            "theme": cfg["theme"],
            "is_return": is_return,
            "total_distance_km": float(tot_km),
            "start_time_cest": cfg["start_time_cest"],
            "scale_t_px_per_min": float(scale_t),
            "iso_step_min": int(iso_step_min),
            "total_nominal_min": float(total_nominal_min),
            "nominal_finish_cest": nominal_finish_local.strftime("%H:%M"),
            "nominal_duration_str": format_duration_h_mm(total_nominal_min),
            "hw_time_cest": hw_local.strftime("%H:%M"),
            "hw_height_m": float(hw_row.water_level_m_taw),
            "lw_time_cest": lw_local.strftime("%H:%M"),
            "lw_height_m": float(lw_row.water_level_m_taw),
        },
        "checkpoints": checkpoints_yaml,
        "nominal_schedule": nominal_schedule_yaml,
        "leg_breakdown": leg_breakdown_yaml,
        "envelope": envelope_yaml,
        "isochrones": isochrones_yaml,
        "spine_data": spine_data_yaml,
        "curves": curves_yaml,
        "speeds_analyzed": speeds_analyzed_yaml,
    }

    yaml_filename = HIST_DIR / f"data_to_plot_v{var_id}.yaml"
    svg_filename = HIST_DIR / f"ontwerp-kustzwem-profiel-v{var_id}.svg"
    png_filename = HIST_DIR / f"ontwerp-kustzwem-profiel-v{var_id}.png"

    with open(yaml_filename, "w", encoding="utf-8") as f:
        yaml.dump(contract_data, f, sort_keys=False, allow_unicode=True)
    print(f"  Dumped contract: {yaml_filename}")

    # 13. Render Unified SVG
    svg = []
    svg.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="100%" height="100%" style="background-color: #ffffff; font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, Helvetica, Arial, sans-serif;">')
    svg.append('  <defs>')
    svg.append('    <filter id="softShadow" x="-10%" y="-10%" width="120%" height="120%">')
    svg.append('      <feDropShadow dx="0" dy="2" stdDeviation="3" flood-opacity="0.08"/>')
    svg.append('    </filter>')
    svg.append('    <filter id="badgeShadow" x="-15%" y="-15%" width="130%" height="130%">')
    svg.append('      <feDropShadow dx="0" dy="2.5" stdDeviation="3.5" flood-opacity="0.14"/>')
    svg.append('    </filter>')
    svg.append('    <pattern id="whiteCrossHatch" width="6" height="6" patternTransform="rotate(45 0 0)" patternUnits="userSpaceOnUse">')
    svg.append('      <line x1="0" y1="0" x2="0" y2="6" stroke="#ffffff" stroke-width="1.3" opacity="0.95"/>')
    svg.append('      <line x1="0" y1="0" x2="6" y2="0" stroke="#ffffff" stroke-width="1.3" opacity="0.95"/>')
    svg.append('    </pattern>')
    svg.append('    <linearGradient id="envelopeGrad" x1="0" y1="0" x2="0" y2="1">')
    svg.append('      <stop offset="0%" stop-color="#10b981" stop-opacity="0.03"/>')
    svg.append('      <stop offset="50%" stop-color="#10b981" stop-opacity="0.20"/>')
    svg.append('      <stop offset="100%" stop-color="#10b981" stop-opacity="0.03"/>')
    svg.append('    </linearGradient>')
    svg.append('  </defs>')

    svg.append(f'  <rect x="0" y="0" width="{width}" height="{height}" fill="#ffffff"/>')

    # Return Leg Background Shading (Only for Return Journeys 8a, 8b, 8c)
    if is_return:
        svg.append(f'  <rect x="{x_mid_turn}" y="80" width="{1370 - x_mid_turn}" height="730" rx="10" fill="#f8fafc" stroke="#e2e8f0" stroke-width="1.2"/>')

    # Header
    hw_str = f"HW {hw_local.strftime('%H:%M CEST')} ({hw_row.water_level_m_taw:.2f}m TAW)"
    lw_str = f"LW {lw_local.strftime('%H:%M CEST')} ({lw_row.water_level_m_taw:.2f}m TAW)"

    clean_title = cfg["title"].replace("&", "&amp;")
    clean_subtitle = cfg["subtitle"].replace("&", "&amp;")

    svg.append('  <!-- ================= HEADER ================= -->')
    svg.append('  <g id="header" transform="translate(0, 24)">')
    svg.append(f'    <text x="{width/2}" y="0" font-size="11" font-weight="800" fill="#0284c7" letter-spacing="1.5" text-anchor="middle">CSCM • KUSTZWEM-TRAJECTPROFIEL</text>')
    svg.append(f'    <text x="{width/2}" y="24" font-size="22" font-weight="900" fill="#0f172a" text-anchor="middle">{clean_title}</text>')
    svg.append(f'    <text x="{width/2}" y="44" font-size="12" font-weight="600" fill="#64748b" text-anchor="middle">{clean_subtitle}</text>')

    # Tide Badges in Top Corners
    svg.append('    <g transform="translate(45, 8)">')
    svg.append('      <rect x="0" y="0" width="230" height="26" rx="5" fill="#f0f9ff" stroke="#bae6fd" stroke-width="1.0"/>')
    svg.append(f'      <text x="12" y="17" font-size="10.5" font-weight="800" fill="#0369a1">🌊 {hw_str}</text>')
    svg.append('    </g>')
    svg.append(f'    <g transform="translate({width - 275}, 8)">')
    svg.append('      <rect x="0" y="0" width="230" height="26" rx="5" fill="#f8fafc" stroke="#cbd5e1" stroke-width="1.0"/>')
    svg.append(f'      <text x="12" y="17" font-size="10.5" font-weight="800" fill="#475569">🌊 {lw_str}</text>')
    svg.append('    </g>')
    svg.append('  </g>')

    # Perspective / Direction Banners
    svg.append('  <!-- ================= PERSPECTIVE BANNERS ================= -->')
    if is_return:
        w_out = (x_mid_turn - 12) - 45
        svg.append(f'  <g id="banner_out" transform="translate(45, 80)">')
        svg.append(f'    <rect x="0" y="0" width="{w_out}" height="32" rx="6" fill="#f0f9ff" stroke="#bae6fd" stroke-width="1.2"/>')
        svg.append('    <text x="14" y="21" font-size="11.5" font-weight="800" fill="#0369a1">➔ ZWEMRICHTING OOST [NL]</text>')
        svg.append(f'    <text x="{w_out - 14}" y="21" font-size="11" font-weight="800" fill="#0284c7" text-anchor="end">RECHTS = MEESTROOM (VLOEDSTROOM ➔)</text>')
        svg.append('  </g>')

        w_ret = 1370 - (x_mid_turn + 12)
        svg.append(f'  <g id="banner_ret" transform="translate({x_mid_turn + 12}, 80)">')
        svg.append(f'    <rect x="0" y="0" width="{w_ret}" height="32" rx="6" fill="#f1f5f9" stroke="#cbd5e1" stroke-width="1.2"/>')
        svg.append('    <text x="14" y="21" font-size="11.5" font-weight="800" fill="#334155">⬅ ZWEMRICHTING WEST [FR]</text>')
        svg.append(f'    <text x="{w_ret - 14}" y="21" font-size="11" font-weight="800" fill="#4338ca" text-anchor="end">RECHTS = MEESTROOM (EBSTROOM ➔)</text>')
        svg.append('  </g>')

        # Turnaround Buffer Corridor
        svg.append(f'  <line x1="{x_mid_turn}" y1="120" x2="{x_mid_turn}" y2="{y_spine_bottom + 15}" stroke="#ef4444" stroke-width="1.8" stroke-dasharray="4,4" opacity="0.6"/>')
        svg.append(f'  <g transform="translate({x_mid_turn}, 168)">')
        svg.append('    <rect x="-16" y="-42" width="32" height="84" rx="16" fill="#ef4444" filter="url(#badgeShadow)"/>')
        svg.append('    <text x="0" y="-24" font-size="14" font-weight="900" fill="#ffffff" text-anchor="middle">↺</text>')
        svg.append('    <text x="0" y="-10" font-size="9" font-weight="900" fill="#ffffff" text-anchor="middle">180°</text>')
        svg.append('    <text x="0" y="4" font-size="8" font-weight="900" fill="#ffffff" text-anchor="middle">KEER</text>')
        svg.append('    <text x="0" y="16" font-size="8" font-weight="900" fill="#ffffff" text-anchor="middle">PUNT</text>')
        svg.append('    <text x="0" y="32" font-size="7.5" font-weight="800" fill="#fecaca" text-anchor="middle">3.00k</text>')
        svg.append('  </g>')

    else:
        w_p2p = 1185.0 - 105.0
        svg.append(f'  <g id="banner_p2p" transform="translate(105, 80)">')
        svg.append(f'    <rect x="0" y="0" width="{w_p2p}" height="32" rx="6" fill="#f0fdf4" stroke="#bbf7d0" stroke-width="1.2"/>')
        svg.append('    <text x="14" y="21" font-size="11.5" font-weight="900" fill="#15803d">➔ ZWEMRICHTING NOORDOOST [NL] • MET DE VLOEDSTROOM MEE • STARTVENSTER ±30 MIN</text>')
        svg.append(f'    <text x="{w_p2p - 14}" y="21" font-size="11" font-weight="800" fill="#0284c7" text-anchor="end">RECHTS = MEESTROOM (VLOEDSTROOM ➔) • {tot_km:.1f} KM</text>')
        svg.append('  </g>')

    # Checkpoint Headers
    for cp_i, cp in enumerate(checkpoints_yaml):
        cx = cp["x"]
        is_turn = cp["leg"] in ["out_turn", "ret_turn"]
        lbl_color = "#ef4444" if is_turn else "#0f172a"
        t_nom = nominal_schedule_yaml[cp_i]["time"]

        anchor = "middle"
        if not is_return:
            anchor = "start" if cp_i == 0 else ("end" if cp_i == len(checkpoints_yaml)-1 else "middle")
        else:
            if cp["leg"] == "out_turn":
                anchor = "end"
            elif cp["leg"] == "ret_turn":
                anchor = "start"
            elif cp_i == 0:
                anchor = "start"
            elif cp_i == len(checkpoints_yaml) - 1:
                anchor = "end"

        svg.append(f'  <g transform="translate({cx}, 145)">')
        svg.append(f'    <text x="0" y="0" font-family="monospace" font-size="11" font-weight="900" fill="{lbl_color}" text-anchor="{anchor}">km {cp["km_tot"]}</text>')
        svg.append(f'    <g transform="translate(0, 16)">')
        svg.append('      <circle cx="-25" cy="-3.5" r="4.5" fill="none" stroke="#64748b" stroke-width="1.2"/>')
        svg.append('      <polyline points="-25,-6 -25,-3.5 -23,-3.5" fill="none" stroke="#64748b" stroke-width="1.1"/>')
        svg.append(f'      <text x="-16" y="0" font-family="monospace" font-size="10" font-weight="700" fill="#64748b" text-anchor="start">{t_nom}</text>')
        svg.append('    </g>')
        if cp["name"]:
            raw_name = cp["name"]
            name_col = "#ef4444" if is_turn else "#0284c7"
            if "(" in raw_name and ")" in raw_name:
                main_part = raw_name.split("(")[0].strip()
                sub_part = "(" + raw_name.split("(")[1]
                tag_col = "#15803d" if "Start" in sub_part else ("#ef4444" if ("Aankomst" in sub_part or "Vertrek" in sub_part) else "#0f172a")
                svg.append(f'    <text x="0" y="-23" font-size="9.5" font-weight="800" fill="{name_col}" text-anchor="{anchor}">{main_part}</text>')
                svg.append(f'    <text x="0" y="-12" font-size="8.5" font-weight="700" fill="{tag_col}" text-anchor="{anchor}">{sub_part}</text>')
            else:
                svg.append(f'    <text x="0" y="-16" font-size="9.5" font-weight="800" fill="{name_col}" text-anchor="{anchor}">{raw_name}</text>')
        svg.append('  </g>')

    # Start Window Envelope Shading (±30 min)
    svg.append('  <!-- ================= ENVELOPE SHADING ================= -->')
    if is_return:
        svg.append(f'  <polygon points="{envelope_yaml["poly_env_heen"]}" fill="url(#envelopeGrad)" stroke="none"/>')
        svg.append(f'  <polygon points="{envelope_yaml["poly_env_terug"]}" fill="url(#envelopeGrad)" stroke="none"/>')
        svg.append(f'  <path d="{poly_to_path(envelope_yaml["env_heen_top"])}" fill="none" stroke="#10b981" stroke-width="1.0" stroke-dasharray="3,3" opacity="0.65"/>')
        svg.append(f'  <path d="{poly_to_path(envelope_yaml["env_heen_bot"])}" fill="none" stroke="#10b981" stroke-width="1.0" stroke-dasharray="3,3" opacity="0.65"/>')
        svg.append(f'  <path d="{poly_to_path(envelope_yaml["env_terug_top"])}" fill="none" stroke="#10b981" stroke-width="1.0" stroke-dasharray="3,3" opacity="0.65"/>')
        svg.append(f'  <path d="{poly_to_path(envelope_yaml["env_terug_bot"])}" fill="none" stroke="#10b981" stroke-width="1.0" stroke-dasharray="3,3" opacity="0.65"/>')
    else:
        svg.append(f'  <polygon points="{envelope_yaml["poly_env"]}" fill="url(#envelopeGrad)" stroke="none"/>')
        svg.append(f'  <path d="{poly_to_path(envelope_yaml["env_top"])}" fill="none" stroke="#10b981" stroke-width="1.0" stroke-dasharray="3,3" opacity="0.65"/>')
        svg.append(f'  <path d="{poly_to_path(envelope_yaml["env_bot"])}" fill="none" stroke="#10b981" stroke-width="1.0" stroke-dasharray="3,3" opacity="0.65"/>')

    # Isochrones (10-minute resolution)
    svg.append('  <!-- ================= ISOCHRONES ================= -->')
    for iso in isochrones_yaml:
        if is_return:
            ph = poly_to_path(iso["pts_h"])
            pt = poly_to_path(iso["pts_t"])
            svg.append(f'  <path d="{ph}" fill="none" stroke="#cbd5e1" stroke-width="1.0" stroke-dasharray="3,4" opacity="0.85"/>')
            svg.append(f'  <path d="{pt}" fill="none" stroke="#cbd5e1" stroke-width="1.0" stroke-dasharray="3,4" opacity="0.85"/>')

            if iso["has_turn_bridge"]:
                p_end_h = iso["pts_h"][-1]
                p_start_t = iso["pts_t"][0]
                svg.append(f'  <path d="M {p_end_h[0]:.1f} {p_end_h[1]:.1f} C {x_mid_turn - 10} {iso["py_turn"]:.1f}, {x_mid_turn + 10} {iso["py_turn"]:.1f}, {p_start_t[0]:.1f} {p_start_t[1]:.1f}" fill="none" stroke="#fca5a5" stroke-width="1.4" stroke-dasharray="2,2"/>')

            # Left entry label (clear of opposing current bars)
            if len(iso["pts_h"]) > 1 and iso["pts_h"][0][0] <= x_heen[0] + 2 and y_spine_top <= iso["pts_h"][0][1] <= y_spine_bottom:
                y_e = iso["pts_h"][0][1]
                svg.append(f'  <line x1="58" y1="{y_e:.1f}" x2="{x_heen[0]}" y2="{y_e:.1f}" stroke="#cbd5e1" stroke-width="0.8" stroke-dasharray="2,2"/>')
                svg.append(f'  <text x="54" y="{y_e + 3.5:.1f}" font-family="monospace" font-size="9" font-weight="700" fill="#64748b" text-anchor="end">{iso["time"]}</text>')

            # Bottom entry label (verderop-naar-rechts verschijnende isochronen)
            if iso["minute_rel"] % 20 == 0:
                if len(iso["pts_h"]) > 1 and iso["pts_h"][0][1] >= y_spine_bottom - 5:
                    p0 = iso["pts_h"][0]
                    if x_heen[0] + 20 <= p0[0] <= x_heen[-1] - 20:
                        p1 = iso["pts_h"][min(5, len(iso["pts_h"])-1)]
                        angle = float(np.degrees(np.arctan2(p1[1] - p0[1], p1[0] - p0[0])))
                        svg.append(f'  <text x="{p0[0] + 10:.1f}" y="{p0[1] - 6:.1f}" font-family="monospace" font-size="8.5" font-weight="800" fill="#64748b" transform="rotate({angle:.1f} {p0[0]+10:.1f} {p0[1]-6:.1f})" paint-order="stroke" stroke="#ffffff" stroke-width="3">{iso["time"]}</text>')

                if len(iso["pts_t"]) > 1 and iso["pts_t"][0][1] >= y_spine_bottom - 5:
                    p0 = iso["pts_t"][0]
                    if x_terug[0] + 15 <= p0[0] <= x_terug[-1] - 20:
                        p1 = iso["pts_t"][min(5, len(iso["pts_t"])-1)]
                        angle = float(np.degrees(np.arctan2(p1[1] - p0[1], p1[0] - p0[0])))
                        svg.append(f'  <text x="{p0[0] + 10:.1f}" y="{p0[1] - 6:.1f}" font-family="monospace" font-size="8.5" font-weight="800" fill="#64748b" transform="rotate({angle:.1f} {p0[0]+10:.1f} {p0[1]-6:.1f})" paint-order="stroke" stroke="#ffffff" stroke-width="3">{iso["time"]}</text>')

            # Top exit label (verdwijnende isochronen bovenaan)
            if iso["minute_rel"] % 20 == 0:
                if len(iso["pts_h"]) > 1 and iso["pts_h"][-1][1] <= y_spine_top + 5:
                    p_exit = iso["pts_h"][-1]
                    if x_heen[0] + 20 <= p_exit[0] <= x_heen[-1] - 20:
                        p_prev = iso["pts_h"][max(0, len(iso["pts_h"])-6)]
                        angle = float(np.degrees(np.arctan2(p_exit[1] - p_prev[1], p_exit[0] - p_prev[0])))
                        svg.append(f'  <text x="{p_exit[0] - 8:.1f}" y="{p_exit[1] + 14:.1f}" font-family="monospace" font-size="8.5" font-weight="800" fill="#64748b" transform="rotate({angle:.1f} {p_exit[0]-8:.1f} {p_exit[1]+14:.1f})" paint-order="stroke" stroke="#ffffff" stroke-width="3">{iso["time"]}</text>')

                if len(iso["pts_t"]) > 1 and iso["pts_t"][-1][1] <= y_spine_top + 5:
                    p_exit = iso["pts_t"][-1]
                    if x_terug[0] + 20 <= p_exit[0] <= x_terug[-1] - 20:
                        p_prev = iso["pts_t"][max(0, len(iso["pts_t"])-6)]
                        angle = float(np.degrees(np.arctan2(p_exit[1] - p_prev[1], p_exit[0] - p_prev[0])))
                        svg.append(f'  <text x="{p_exit[0] - 8:.1f}" y="{p_exit[1] + 14:.1f}" font-family="monospace" font-size="8.5" font-weight="800" fill="#64748b" transform="rotate({angle:.1f} {p_exit[0]-8:.1f} {p_exit[1]+14:.1f})" paint-order="stroke" stroke="#ffffff" stroke-width="3">{iso["time"]}</text>')

        else:
            d_str = poly_to_path(iso["pts"])
            svg.append(f'  <path d="{d_str}" fill="none" stroke="#cbd5e1" stroke-width="1.0" stroke-dasharray="3,4" opacity="0.85"/>')

            # Left entry label (only when actually entering at left spine)
            p_entry = iso["pts"][0]
            if p_entry[0] <= x_start + 2 and y_spine_top <= p_entry[1] <= y_spine_bottom:
                y_e = p_entry[1]
                svg.append(f'  <line x1="58" y1="{y_e:.1f}" x2="{x_start}" y2="{y_e:.1f}" stroke="#cbd5e1" stroke-width="0.8" stroke-dasharray="2,2"/>')
                svg.append(f'  <text x="54" y="{y_e + 3.5:.1f}" font-family="monospace" font-size="9" font-weight="700" fill="#64748b" text-anchor="end">{iso["time"]}</text>')

            # Bottom entry label (verderop-naar-rechts verschijnende isochronen)
            if iso["minute_rel"] % 20 == 0 and len(iso["pts"]) > 1 and iso["pts"][0][1] >= y_spine_bottom - 5:
                p0 = iso["pts"][0]
                if x_start + 30 <= p0[0] <= x_finish - 30:
                    p1 = iso["pts"][min(5, len(iso["pts"])-1)]
                    angle = float(np.degrees(np.arctan2(p1[1] - p0[1], p1[0] - p0[0])))
                    svg.append(f'  <text x="{p0[0] + 10:.1f}" y="{p0[1] - 6:.1f}" font-family="monospace" font-size="8.5" font-weight="800" fill="#64748b" transform="rotate({angle:.1f} {p0[0]+10:.1f} {p0[1]-6:.1f})" paint-order="stroke" stroke="#ffffff" stroke-width="3">{iso["time"]}</text>')

            # Top exit label (verdwijnende isochronen bovenaan)
            if iso["minute_rel"] % 20 == 0 and len(iso["pts"]) > 1 and iso["pts"][-1][1] <= y_spine_top + 5:
                p_exit = iso["pts"][-1]
                if x_start + 30 <= p_exit[0] <= x_finish - 30:
                    p_prev = iso["pts"][max(0, len(iso["pts"])-6)]
                    angle = float(np.degrees(np.arctan2(p_exit[1] - p_prev[1], p_exit[0] - p_prev[0])))
                    svg.append(f'  <text x="{p_exit[0] - 8:.1f}" y="{p_exit[1] + 14:.1f}" font-family="monospace" font-size="8.5" font-weight="800" fill="#64748b" transform="rotate({angle:.1f} {p_exit[0]-8:.1f} {p_exit[1]+14:.1f})" paint-order="stroke" stroke="#ffffff" stroke-width="3">{iso["time"]}</text>')

    # Vertical Spines & Current Staven ("Stromingsgraten")
    svg.append('  <!-- ================= SPINES & STROMINGSGRATEN ================= -->')
    for s_info in spine_data_yaml:
        cx = s_info["cx"]
        cp = s_info["checkpoint"]
        is_turn = cp["leg"] in ["out_turn", "ret_turn"]
        spine_col = "#ef4444" if is_turn else "#94a3b8"

        svg.append(f'  <line x1="{cx}" y1="{y_spine_top}" x2="{cx}" y2="{y_spine_bottom}" stroke="{spine_col}" stroke-width="{1.8 if is_turn else 1.2}"/>')

        for b in s_info["bars"]:
            by = b["py"]
            bar_len = b["bar_len"]
            x_b = b["x_b"]
            base_col = b["base_col"]

            bar_h = 7.0
            y_bar = by - bar_h / 2.0
            stroke_attr = ' stroke="#0f172a" stroke-width="1.2"' if b["is_nominal"] else ""

            if bar_len > 0.5:
                w_b = max(1.0, bar_len)
                svg.append(f'  <rect x="{x_b:.1f}" y="{y_bar:.1f}" width="{w_b:.1f}" height="{bar_h}" rx="1.5" fill="{base_col}" opacity="0.9"{stroke_attr}/>')
                if not b["is_out"]:
                    svg.append(f'  <rect x="{x_b:.1f}" y="{y_bar:.1f}" width="{w_b:.1f}" height="{bar_h}" rx="1.5" fill="url(#whiteCrossHatch)"/>')

            svg.append(f'  <line x1="{cx - 2}" y1="{by:.1f}" x2="{cx + 2}" y2="{by:.1f}" stroke="#64748b" stroke-width="1"/>')

    # 9 Isotachs Curves
    svg.append('  <!-- ================= 9-ISOTACH FAN ================= -->')
    for crv in curves_yaml:
        if is_return:
            ph = poly_to_path(crv["pts_heen"])
            pt = poly_to_path(crv["pts_terug"])
            svg.append(f'  <path d="{ph}" fill="none" stroke="{crv["color"]}" stroke-width="{crv["lw"]}" stroke-linecap="round" opacity="{crv["opacity"]}"/>')
            svg.append(f'  <path d="{pt}" fill="none" stroke="{crv["color"]}" stroke-width="{crv["lw"]}" stroke-linecap="round" opacity="{crv["opacity"]}"/>')
        else:
            d_str = poly_to_path(crv["pts"])
            svg.append(f'  <path d="{d_str}" fill="none" stroke="{crv["color"]}" stroke-width="{crv["lw"]}" stroke-linecap="round" opacity="{crv["opacity"]}"/>')
            svg.append(f'  <circle cx="{crv["pts"][-1][0]:.1f}" cy="{crv["pts"][-1][1]:.1f}" r="3.5" fill="{crv["color"]}"/>')

    # Finish Table (Right Card) - Ordered Fastest (1.4, Top) to Slowest (0.6, Bottom)
    w_card = 185
    x_card = 1205
    y_card = 148

    svg.append('  <!-- ================= FINISH TABLE CARD ================= -->')
    svg.append(f'  <g id="finish_summary" transform="translate({x_card}, {y_card})">')
    svg.append(f'    <rect x="0" y="0" width="{w_card}" height="642" rx="8" fill="#f8fafc" stroke="#cbd5e1" stroke-width="1.2" filter="url(#softShadow)"/>')
    svg.append(f'    <rect x="0" y="0" width="{w_card}" height="38" rx="8" fill="#0f172a"/>')
    svg.append('    <text x="92" y="24" font-size="12" font-weight="900" fill="#ffffff" text-anchor="middle">FINISH &amp; TIJDSDUUR</text>')

    y_row = 52
    for sp in speeds_table_ordered:
        is_nom = (sp["speed_mps"] == 1.0)
        bg_col = "#dcfce7" if is_nom else ("#ffffff" if int(sp["speed_mps"]*10)%2==0 else "#f8fafc")
        border_col = "#86efac" if is_nom else "#e2e8f0"

        svg.append(f'    <g transform="translate(8, {y_row})">')
        svg.append(f'      <rect x="0" y="0" width="169" height="42" rx="5" fill="{bg_col}" stroke="{border_col}" stroke-width="1.0"/>')
        svg.append(f'      <circle cx="12" cy="21" r="5" fill="{sp["color"]}"/>')
        svg.append(f'      <text x="24" y="18" font-size="11" font-weight="900" fill="{sp["color"]}">{sp["speed_mps"]:.1f} m/s</text>')
        svg.append(f'      <text x="24" y="32" font-size="9.5" font-weight="700" fill="#64748b">tot: {sp["total_time_str"]}</text>')
        svg.append(f'      <text x="160" y="18" font-family="monospace" font-size="12" font-weight="900" fill="#0f172a" text-anchor="end">{sp["eta_finish"]}</text>')
        svg.append(f'      <text x="160" y="32" font-family="monospace" font-size="10" font-weight="800" fill="{"#15803d" if is_nom else "#64748b"}" text-anchor="end">{sp["delta_min"]}</text>')
        svg.append('    </g>')
        y_row += 46

    # Bottom of Finish Card: Start Window Impact (+/- 30 min)
    svg.append(f'    <g transform="translate(8, {y_row + 8})">')
    svg.append('      <rect x="0" y="0" width="169" height="132" rx="6" fill="#f0fdf4" stroke="#bbf7d0" stroke-width="1.2"/>')
    svg.append('      <text x="84" y="20" font-size="10.5" font-weight="900" fill="#16a34a" text-anchor="middle">STARTVENSTER (±30 MIN)</text>')
    svg.append('      <line x1="12" y1="28" x2="157" y2="28" stroke="#bbf7d0" stroke-width="1"/>')
    svg.append(f'      <text x="12" y="48" font-size="9.5" font-weight="700" fill="#0f172a">-30\' vertrek: <tspan font-weight="900" fill="#15803d">{envelope_yaml["fin_early_time"]}</tspan></text>')
    svg.append(f'      <text x="12" y="62" font-size="8.5" font-weight="600" fill="#64748b">Zwemduur {envelope_yaml["fin_early_delta_str"]} t.o.v. nom</text>')
    svg.append(f'      <text x="12" y="86" font-size="9.5" font-weight="700" fill="#0f172a">+30\' vertrek: <tspan font-weight="900" fill="#15803d">{envelope_yaml["fin_late_time"]}</tspan></text>')
    svg.append(f'      <text x="12" y="100" font-size="8.5" font-weight="600" fill="#64748b">Zwemduur {envelope_yaml["fin_late_delta_str"]} t.o.v. nom</text>')
    svg.append('    </g>')
    svg.append('  </g>')

    # 8 Vector Balance Ribbons ("Schaal-balken") Underneath Every Leg
    svg.append('  <!-- ================= 8 VECTOR BALANCE CARDS ================= -->')
    y_ribbon = 818.0
    h_box = 48.0

    for k, leg in enumerate(leg_breakdown_yaml):
        if is_return:
            if k < 4:
                x_l = x_heen[k]
                x_r = x_heen[k + 1]
                bg_col = "#ffffff"
            else:
                x_l = x_terug[k - 4]
                x_r = x_terug[k - 3]
                bg_col = "#f1f5f9"
            w_leg = x_r - x_l
            w_box = 115.0
        else:
            x_l = checkpoints_yaml[k]["x"]
            x_r = checkpoints_yaml[k + 1]["x"]
            w_leg = x_r - x_l
            w_box = min(w_leg - 10.0, 126.0)
            bg_col = "#ffffff"

        x_b = x_l + (w_leg - w_box) / 2.0
        x_mid_leg = (x_l + x_r) / 2.0

        svg.append(f'  <line x1="{x_mid_leg:.1f}" y1="{y_spine_bottom}" x2="{x_mid_leg:.1f}" y2="{y_ribbon}" stroke="#cbd5e1" stroke-width="0.9" stroke-dasharray="2,2"/>')
        svg.append(f'  <g transform="translate({x_b:.1f}, {y_ribbon})">')
        svg.append(f'    <rect x="0" y="0" width="{w_box}" height="{h_box}" rx="6" fill="{bg_col}" stroke="#cbd5e1" stroke-width="1.0" filter="url(#softShadow)"/>')

        d_w = leg["dist_swimmer_m"]
        d_u = leg["dist_current_m"]
        u_avg = leg["u_avg_mps"]
        dt_min = leg["dt_min"]
        is_flood = leg["is_flood"]
        cur_col = "#0284c7" if is_flood else "#4338ca"

        x_trk = 12.0
        y_trk = 7.0
        h_trk = 11.0
        w_bar_total = w_box - 24.0

        if d_u >= 0:
            scale_bar = w_bar_total / (d_w + d_u) if (d_w + d_u) > 0 else 1.0
            w_w = d_w * scale_bar
            w_u = d_u * scale_bar
            svg.append(f'    <rect x="{x_trk:.1f}" y="{y_trk}" width="{w_bar_total:.1f}" height="{h_trk}" rx="2" fill="#e2e8f0"/>')
            svg.append(f'    <rect x="{x_trk:.1f}" y="{y_trk}" width="{w_w:.1f}" height="{h_trk}" rx="2" fill="#16a34a"/>')
            svg.append(f'    <rect x="{x_trk + w_w:.1f}" y="{y_trk}" width="{w_u:.1f}" height="{h_trk}" rx="2" fill="{cur_col}"/>')
            if is_return and k >= 4:
                svg.append(f'    <rect x="{x_trk + w_w:.1f}" y="{y_trk}" width="{w_u:.1f}" height="{h_trk}" rx="2" fill="url(#whiteCrossHatch)"/>')
            cur_str = f"+{int(round(d_u))}m"
        else:
            w_w = w_bar_total
            scale_bar = w_bar_total / d_w if d_w > 0 else 1.0
            w_u = abs(d_u) * scale_bar
            x_tick = x_trk + w_bar_total - w_u
            svg.append(f'    <rect x="{x_trk:.1f}" y="{y_trk}" width="{w_bar_total:.1f}" height="{h_trk}" rx="2" fill="#e2e8f0"/>')
            svg.append(f'    <rect x="{x_trk:.1f}" y="{y_trk}" width="{w_w:.1f}" height="{h_trk}" rx="2" fill="#16a34a"/>')
            svg.append(f'    <rect x="{x_tick:.1f}" y="{y_trk}" width="{w_u:.1f}" height="{h_trk}" rx="2" fill="{cur_col}" fill-opacity="0.65"/>')
            if is_return and k >= 4:
                svg.append(f'    <rect x="{x_tick:.1f}" y="{y_trk}" width="{w_u:.1f}" height="{h_trk}" rx="2" fill="url(#whiteCrossHatch)"/>')
            if w_u >= 6.0:
                svg.append(f'    <polygon points="{x_trk + w_bar_total - 2:.1f},{y_trk + 2.5} {x_tick + 2:.1f},{y_trk + 5.5} {x_trk + w_bar_total - 2:.1f},{y_trk + 8.5}" fill="#ffffff" opacity="0.95"/>')
            svg.append(f'    <line x1="{x_tick:.1f}" y1="{y_trk - 2}" x2="{x_tick:.1f}" y2="{y_trk + h_trk + 2}" stroke="#0f172a" stroke-width="1.8"/>')
            cur_str = f"{int(round(d_u))}m"

        svg.append(f'    <text x="{w_box/2:.1f}" y="29" font-family="monospace" font-size="8.5" font-weight="800" text-anchor="middle"><tspan fill="#16a34a">{int(round(d_w))}m</tspan> <tspan fill="{cur_col}">{cur_str}</tspan></text>')
        svg.append(f'    <text x="{w_box/2:.1f}" y="40" font-family="monospace" font-size="8" font-weight="700" fill="#64748b" text-anchor="middle">u = {u_avg:+.2f} m/s • {dt_min:.1f}\'</text>')
        svg.append('  </g>')

    # Bottom Legend (Unified 1330px Bar)
    y_leg = 890.0
    w_leg = 1330.0
    x_leg = (width - w_leg) / 2.0

    svg.append('  <!-- ================= BOTTOM LEGEND ================= -->')
    svg.append(f'  <g id="bottom_legend" transform="translate({x_leg:.1f}, {y_leg})">')
    svg.append(f'    <rect x="0" y="0" width="{w_leg}" height="44" rx="8" fill="#f8fafc" stroke="#cbd5e1" stroke-width="1.2" filter="url(#softShadow)"/>')

    svg.append('    <g transform="translate(18, 16)">')
    svg.append('      <text x="0" y="10" font-size="10.5" font-weight="900" fill="#0f172a">Snelheid:</text>')
    x_strip = 58.0
    for sp_i, sp_info in enumerate(speeds_analyzed_yaml):
        svg.append(f'      <rect x="{x_strip + sp_i*9}" y="2" width="9" height="10" fill="{sp_info["color"]}"/>')
    svg.append(f'      <text x="{x_strip + 88}" y="10" font-size="9.5" font-weight="700" fill="#ea580c">0.6</text>')
    svg.append(f'      <text x="{x_strip + 110}" y="10" font-size="10" font-weight="900" fill="#16a34a">1.0 [Nom]</text>')
    svg.append(f'      <text x="{x_strip + 168}" y="10" font-size="9.5" font-weight="700" fill="#2563eb">1.4 m/s</text>')
    svg.append('    </g>')

    svg.append('    <g transform="translate(305, 16)">')
    svg.append('      <rect x="0" y="2" width="20" height="12" fill="url(#envelopeGrad)"/>')
    svg.append('      <line x1="0" y1="2" x2="20" y2="2" stroke="#10b981" stroke-width="1.0" stroke-dasharray="2,2"/>')
    svg.append('      <line x1="0" y1="14" x2="20" y2="14" stroke="#10b981" stroke-width="1.0" stroke-dasharray="2,2"/>')
    svg.append('      <text x="28" y="10" font-size="10" font-weight="800" fill="#0f172a">Startvenster: <tspan font-weight="600" fill="#64748b">±30\' marge</tspan></text>')
    svg.append('    </g>')

    svg.append('    <g transform="translate(540, 16)">')
    svg.append('      <text x="0" y="10" font-size="10.5" font-weight="900" fill="#0284c7">Vloed (ZW → NO):</text>')
    svg.append('      <rect x="110" y="2" width="14" height="10" rx="2" fill="#0284c7"/>')
    svg.append('      <text x="130" y="10" font-size="9.5" font-weight="700" fill="#64748b">stuwkracht</text>')

    svg.append('      <text x="215" y="10" font-size="10.5" font-weight="900" fill="#4338ca">Eb (NO → ZW):</text>')
    svg.append('      <rect x="310" y="2" width="14" height="10" rx="2" fill="#4338ca"/>')
    svg.append('      <text x="330" y="10" font-size="9.5" font-weight="700" fill="#64748b">tegenstroom</text>')
    svg.append('    </g>')

    svg.append('    <g transform="translate(980, 16)">')
    svg.append('      <line x1="0" y1="7" x2="24" y2="7" stroke="#94a3b8" stroke-width="1.2" stroke-dasharray="3,3"/>')
    svg.append(f'      <text x="32" y="10" font-size="10" font-weight="800" fill="#0f172a">Isochronen: <tspan font-weight="600" fill="#64748b">Lijnen gelijke tijd ({iso_step_min}\')</tspan></text>')
    svg.append('    </g>')
    svg.append('  </g>')

    # Footer
    svg.append('  <!-- Footer -->')
    svg.append('  <g id="footer" transform="translate(45, 972)">')
    svg.append('    <text x="0" y="0" font-size="11" font-weight="600" fill="#94a3b8">CSCM • Dynamisch Kustzwem-Trajectmodel • Copernicus CMEMS 2D &amp; HIC KiWIS Operational Forecasts (25m Grid)</text>')
    svg.append(f'    <text x="{w_leg}" y="0" font-size="11" font-weight="800" fill="#94a3b8" text-anchor="end">ONTWERP v8 (A3 LIGGEND)</text>')
    svg.append('  </g>')

    svg.append('</svg>')

    with open(svg_filename, "w", encoding="utf-8") as f:
        f.write("\n".join(svg))
    print(f"  Generated SVG: {svg_filename}")

    try:
        subprocess.run(["rsvg-convert", "-w", "2000", str(svg_filename), "-o", str(png_filename)], check=True)
        print(f"  Generated PNG: {png_filename}")
    except Exception as e:
        print(f"  Error converting to PNG: {e}")


def main():
    parser = argparse.ArgumentParser(description="Generate Coastal Swim Profile v8 Suite")
    parser.add_argument("--variant", choices=["8a", "8b", "8c", "8d", "8e", "all"], default="all")
    args = parser.parse_args()

    targets = ["8a", "8b", "8c", "8d", "8e"] if args.variant == "all" else [args.variant]
    for key in targets:
        generate_variant(key)
    print("\n" + "=" * 72)
    print(f"v8 Suite successfully generated for: {targets}")
    print("=" * 72)


if __name__ == "__main__":
    main()
