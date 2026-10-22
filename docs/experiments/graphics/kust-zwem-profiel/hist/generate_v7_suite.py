#!/usr/bin/env python3
"""
Multi-Variant Coastal Swim Trajectory Profile Suite v7 (Sat 24 Oct 2026).

Generates three distinct operational departure scenarios for the lifeguard/swimmer panel:
- Variant 7a: Start 09:00 CEST (Ochtend Kentering & Vroege Vloed • Gebalanceerd Traject)
- Variant 7b: Start 13:00 CEST (Piekvloed Heenweg & Kentering Terugweg • Snel Heen, Zwaar Terug)
- Variant 7c: Start 17:00 CEST (Eb Tegenstroom Heenweg & Ebstroom-Surf Terugweg • Zwaar Heen, Snelle Surf Terug)

Features:
- 10-Minute Isochrone Resolution (spacious and clear).
- Authentic Copernicus Marine (CMEMS) 2D hydrodynamics and HIC KiWIS tidal levels.
- Discrete 25m alongshore kinematics via hist/kinematics.py.
- Proportional vector cards, decoupled turnaround corridor, and white cross-hatching.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
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


def generate_variant(var_id: str, start_hour_cest: int, subtitle_theme: str):
    print("=" * 70)
    print(f"CSCM Kustzwem-Profiel Variant {var_id}: Start {start_hour_cest:02d}:00 CEST ({subtitle_theme})")
    print("=" * 70)

    start_hour_utc = start_hour_cest - 2
    t_start_utc = datetime(2026, 10, 24, start_hour_utc, 0, tzinfo=timezone.utc)
    t_end_query = datetime(2026, 10, 24, 23, 0, tzinfo=timezone.utc)

    broker = get_broker()

    # 1. Checkpoint definitions
    raw_checkpoints = [
        ("Bredene P4 (Start)", 0.00, 51.24989, 2.96226, "out", 105),
        ("",                   0.75, 51.25330, 2.97156, "out", 230),
        ("",                   1.50, 51.25721, 2.98033, "out", 355),
        ("",                   2.25, 51.26129, 2.98890, "out", 480),
        ("Vosseslag (Aankomst)", 3.00, 51.26538, 2.99748, "out_turn", 605),
        ("Vosseslag (Vertrek)",  3.00, 51.26538, 2.99748, "ret_turn", 685),
        ("",                   3.75, 51.26129, 2.98890, "ret", 810),
        ("",                   4.50, 51.25721, 2.98033, "ret", 935),
        ("",                   5.25, 51.25330, 2.97156, "ret", 1060),
        ("Bredene P4 (Finish)", 6.00, 51.24989, 2.96226, "ret", 1185),
    ]

    checkpoints_yaml = []
    kinematics_checkpoints = []
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
            "x": x_pos,
        })
        kinematics_checkpoints.append(Checkpoint(
            idx=idx,
            name=name or f"CP {idx}",
            s_km=float(s_km),
            lat=lat,
            lon=lon,
        ))

    # 2. HIC KiWIS Tide Extremes
    tide_res = broker.query(
        "tide",
        station="OST",
        start_time=datetime(2026, 10, 24, 6, 0, tzinfo=timezone.utc),
        end_time=t_end_query,
        source="forecast",
        time_offset_minutes=7.0,
    )
    df_tide = tide_res.to_dataframe()
    hw_row = df_tide.loc[df_tide["water_level_m_taw"].idxmax()]
    lw_row = df_tide.loc[df_tide["water_level_m_taw"].idxmin()]
    hw_local = hw_row.timestamp + pd.Timedelta(hours=2)
    lw_local = lw_row.timestamp + pd.Timedelta(hours=2)

    # 3. CMEMS Currents
    coords_unique = [
        (51.24989, 2.96226),
        (51.25330, 2.97156),
        (51.25721, 2.98033),
        (51.26129, 2.98890),
        (51.26538, 2.99748),
    ]
    curr_res = broker.query(
        "current",
        positions=coords_unique,
        start_time=datetime(2026, 10, 24, 5, 0, tzinfo=timezone.utc),
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

    # 4. Canvas Geometry & Dynamic Vertical Scaling
    width = 1420
    height = 1004
    y_spine_top = 170.0
    y_spine_bottom = 790.0
    matrix_height = y_spine_bottom - y_spine_top  # 620.0 px
    y_ref = 390.0
    scale_v = 40.0
    iso_step_min = 10  # 10-MINUTE ISOCHRONES!

    x_heen = [105.0, 230.0, 355.0, 480.0, 605.0]
    x_terug = [685.0, 810.0, 935.0, 1060.0, 1185.0]
    x_mid_turn = 645.0

    def s_to_x_heen(s_km: float) -> float:
        return 105.0 + (s_km / 3.0) * (605.0 - 105.0)

    def s_to_x_terug(s_km: float) -> float:
        return 685.0 + ((3.0 - s_km) / 3.0) * (1185.0 - 685.0)

    # 5. Run Alongshore Kinematics Calculator for Nominal Swimmer (1.0 m/s)
    calc_out = AlongshoreTrajectoryCalculator(checkpoints=kinematics_checkpoints[:5], ds_step_m=25.0)
    traj_out_nom = calc_out.calculate_trajectory(speed_mps=1.0, start_time_utc=t_start_utc, current_fn=current_lookup_fn)

    t_turn_utc = traj_out_nom.finish_time_utc
    calc_ret = AlongshoreTrajectoryCalculator(checkpoints=kinematics_checkpoints[5:], ds_step_m=25.0)
    traj_ret_nom = calc_ret.calculate_trajectory(speed_mps=1.0, start_time_utc=t_turn_utc, current_fn=current_lookup_fn)

    total_nominal_sec = traj_out_nom.total_duration_sec + traj_ret_nom.total_duration_sec
    total_nominal_min = total_nominal_sec / 60.0
    nominal_finish_utc = traj_ret_nom.finish_time_utc
    nominal_finish_local = nominal_finish_utc + timedelta(hours=2)

    print(f"  Outbound: {traj_out_nom.total_duration_min:.1f} min | Turn: {(t_turn_utc + timedelta(hours=2)).strftime('%H:%M:%S')} CEST")
    print(f"  Return:   {traj_ret_nom.total_duration_min:.1f} min | Finish: {nominal_finish_local.strftime('%H:%M:%S')} CEST")
    print(f"  Total:    {total_nominal_min:.1f} min")

    # Reference swimmer interpolation
    s_heen_ref = [p[0] for p in traj_out_nom.trajectory_points]
    t_heen_ref = [(p[1] - t_start_utc).total_seconds() / 60.0 for p in traj_out_nom.trajectory_points]

    def get_t_ref_heen(s_km: float) -> float:
        return float(np.interp(s_km, s_heen_ref, t_heen_ref))

    s_terug_ref = [p[0] for p in traj_ret_nom.trajectory_points]
    t_terug_ref = [(p[1] - t_start_utc).total_seconds() / 60.0 for p in traj_ret_nom.trajectory_points]
    s_terug_rev = list(reversed(s_terug_ref))
    t_terug_rev = list(reversed(t_terug_ref))

    def get_t_ref_terug(s_km: float) -> float:
        return float(np.interp(s_km, s_terug_rev, t_terug_rev))

    # Fast trajectory scan to calibrate scale_t across the fan
    fan_speeds = [0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4]
    deltas = []
    fan_trajs = {}
    for v in fan_speeds:
        t_o = calc_out.calculate_trajectory(speed_mps=v, start_time_utc=t_start_utc, current_fn=current_lookup_fn)
        t_r = calc_ret.calculate_trajectory(speed_mps=v, start_time_utc=t_o.finish_time_utc, current_fn=current_lookup_fn)
        tot_sec = t_o.total_duration_sec + t_r.total_duration_sec
        delta_m = (tot_sec - total_nominal_sec) / 60.0
        deltas.append(delta_m)
        fan_trajs[v] = (t_o, t_r, tot_sec)

    max_up_min = max(35.0, abs(min(deltas)))  # headroom for fastest
    max_down_min = max(35.0, max(deltas))     # headroom for slowest
    # Dynamic scale_t to fill matrix without overflowing below y_spine_bottom (790) or above y_spine_top (170)
    avail_down = y_spine_bottom - y_ref - 18.0  # 790 - 390 - 18 = 382 px
    avail_up = y_ref - y_spine_top - 18.0       # 390 - 170 - 18 = 202 px
    scale_t = min(5.0, avail_down / max_down_min, avail_up / max_up_min)
    print(f"  Calibrated scale_t = {scale_t:.2f} px/min (delta range: {min(deltas):+.1f} to {max(deltas):+.1f} min)")

    # Nominal schedule
    nominal_checkpoint_times = traj_out_nom.checkpoint_times_utc + traj_ret_nom.checkpoint_times_utc
    nominal_schedule_yaml = []
    nom_times_min = []
    for cp, cp_time_utc in zip(checkpoints_yaml, nominal_checkpoint_times):
        loc_time = cp_time_utc + timedelta(hours=2)
        t_min = (cp_time_utc - t_start_utc).total_seconds() / 60.0
        nom_times_min.append(t_min)
        nominal_schedule_yaml.append({
            "km": cp["label"],
            "name": cp["name"],
            "time": loc_time.strftime("%H:%M"),
            "t_min": round(t_min, 1),
        })

    # Leg breakdown
    all_legs = traj_out_nom.legs + traj_ret_nom.legs
    leg_breakdown_yaml = []
    for idx, leg in enumerate(all_legs):
        leg_idx = idx + 1
        leg_t_start_min = (leg.t_start_utc - t_start_utc).total_seconds() / 60.0
        leg_t_end_min = (leg.t_end_utc - t_start_utc).total_seconds() / 60.0
        leg_breakdown_yaml.append({
            "leg_idx": leg_idx,
            "name": f"Leg {leg_idx}/8",
            "direction": "out" if leg_idx <= 4 else "ret",
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

    # 6. Curves for 9-isotach fan
    fan_colors = {
        0.6: "#ea580c", 0.7: "#f97316", 0.8: "#f59e0b", 0.9: "#84cc16",
        1.0: "#16a34a", 1.1: "#10b981", 1.2: "#06b6d4", 1.3: "#0ea5e9", 1.4: "#2563eb",
    }
    speeds_analyzed_yaml = []
    curves_yaml = []
    for v in fan_speeds:
        t_o, t_r, tot_sec = fan_trajs[v]
        tot_min = tot_sec / 60.0
        fin_local = t_r.finish_time_utc + timedelta(hours=2)
        delta_m = (tot_sec - total_nominal_sec) / 60.0
        sign_str = "+" if delta_m > 0.05 else ("" if abs(delta_m) <= 0.05 else "-")
        delta_str = f"{sign_str}{abs(delta_m):.0f}'" if abs(delta_m) > 0.05 else "0'"

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

        speeds_analyzed_yaml.append({
            "speed_mps": float(v),
            "color": fan_colors[v],
            "eta_finish": fin_local.strftime("%H:%M"),
            "delta_min": delta_str,
            "total_time_min": round(tot_min, 1),
        })
        curves_yaml.append({
            "speed_mps": float(v),
            "color": fan_colors[v],
            "lw": 3.0 if v == 1.0 else 1.5,
            "opacity": 1.0 if v == 1.0 else 0.88,
            "pts_heen": pts_heen,
            "pts_terug": pts_terug,
            "last_py": min(y_spine_bottom - 8.0, pts_terug[-1][1] if pts_terug else y_ref),
        })

    # 7. Starttijd-Venster
    t_start_early = t_start_utc - timedelta(minutes=30)
    t_start_late = t_start_utc + timedelta(minutes=30)

    t_out_early = calc_out.calculate_trajectory(1.0, t_start_early, current_lookup_fn)
    t_ret_early = calc_ret.calculate_trajectory(1.0, t_out_early.finish_time_utc, current_lookup_fn)
    t_out_late = calc_out.calculate_trajectory(1.0, t_start_late, current_lookup_fn)
    t_ret_late = calc_ret.calculate_trajectory(1.0, t_out_late.finish_time_utc, current_lookup_fn)

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
    }

    # 8. Isochrones on 10-Minute Resolution
    isochrones_yaml = []
    s_fine_heen = np.linspace(0.0, 3.0, 60)
    s_fine_terug = np.linspace(3.0, 0.0, 60)
    iso_max_m = int(math.ceil(max(deltas) + total_nominal_min + 35.0))

    for m in range(-30, iso_max_m, iso_step_min):
        t_clock_utc = t_start_utc + timedelta(minutes=m)
        t_clock_local = t_clock_utc + timedelta(hours=2)
        t_label = t_clock_local.strftime("%H:%M")

        pts_h = []
        for s_km in s_fine_heen:
            t_r = get_t_ref_heen(float(s_km))
            py = y_ref + (m - t_r) * scale_t
            px = s_to_x_heen(float(s_km))
            if y_spine_top - 3.0 <= py <= y_spine_bottom + 3.0:
                pts_h.append([round(px, 1), round(py, 1)])

        pts_t = []
        for s_km in s_fine_terug:
            t_r = get_t_ref_terug(float(s_km))
            py = y_ref + (m - t_r) * scale_t
            px = s_to_x_terug(float(s_km))
            if y_spine_top - 3.0 <= py <= y_spine_bottom + 3.0:
                pts_t.append([round(px, 1), round(py, 1)])

        py_turn = y_ref + (m - t_heen_ref[-1]) * scale_t
        has_turn_bridge = bool((len(pts_h) > 0 and len(pts_t) > 0) and (y_spine_top <= py_turn <= y_spine_bottom))

        if len(pts_h) >= 2 or len(pts_t) >= 2:
            isochrones_yaml.append({
                "time": t_label,
                "clock_min": m,
                "pts_h": pts_h,
                "pts_t": pts_t,
                "py_turn": round(py_turn, 1) if has_turn_bridge else None,
                "has_turn_bridge": has_turn_bridge,
            })

    # 9. Vertical Current Staven along Spines
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

    # 10. Write YAML Data Contract
    yaml_filename = HIST_DIR / f"data_to_plot_v{var_id}.yaml"
    data_payload = {
        "title": f"CSCM KUSTZWEM-TRAJECTPROFIEL v{var_id}",
        "variant": var_id,
        "route": "Bredene Post 4 ➔ Vosseslag ➔ Bredene Post 4 (6.0 km Heen-en-Terug)",
        "date": "Zaterdag 24 Oktober 2026",
        "start_time": f"{start_hour_cest:02d}:00 CEST ({start_hour_utc:02d}:00 UTC)",
        "subtitle_theme": subtitle_theme,
        "geometry": {
            "format": "DIN A3/A4 Landscape (ratio 1.414)",
            "width": width,
            "height": height,
            "y_spine_top": y_spine_top,
            "y_spine_bottom": y_spine_bottom,
            "matrix_height": matrix_height,
            "y_ref": y_ref,
            "vertical_scale_px_per_min": round(scale_t, 2),
            "horizontal_scale_px_per_ms": scale_v,
            "x_heen": x_heen,
            "x_terug": x_terug,
            "x_mid_turn": x_mid_turn,
        },
        "isochrone_resolution_min": iso_step_min,
        "departure_window_min": 30,
        "checkpoints": checkpoints_yaml,
        "nominal_schedule": nominal_schedule_yaml,
        "leg_breakdown": leg_breakdown_yaml,
        "speeds_analyzed": speeds_analyzed_yaml,
        "curves": curves_yaml,
        "envelope": envelope_yaml,
        "isochrones": isochrones_yaml,
        "spine_data": spine_data_yaml,
        "forecast_metadata": {
            "high_water": {
                "time_local": hw_local.strftime("%H:%M CEST"),
                "height_m_taw": round(float(hw_row.water_level_m_taw), 2),
                "station": "Oostende MVB (+7m phase lag)",
            },
            "low_water": {
                "time_local": lw_local.strftime("%H:%M CEST"),
                "height_m_taw": round(float(lw_row.water_level_m_taw), 2),
                "station": "Oostende MVB (+7m phase lag)",
            },
            "current_provider": "Copernicus CMEMS 1.5km 2D Hydrodynamic Model (North West European Shelf)",
            "tide_provider": "Flemish Hydro Information Centre (HIC) KiWIS KT-Last Operational Forecast",
        },
    }

    with open(yaml_filename, "w", encoding="utf-8") as f:
        yaml.dump(data_payload, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
    print(f"  Saved YAML contract: {yaml_filename}")

    # 11. Render SVG
    svg_filename = HIST_DIR / f"ontwerp-kustzwem-profiel-v{var_id}.svg"
    png_filename = HIST_DIR / f"ontwerp-kustzwem-profiel-v{var_id}.png"

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
    svg.append('      <stop offset="0%" stop-color="#10b981" stop-opacity="0.02"/>')
    svg.append('      <stop offset="50%" stop-color="#10b981" stop-opacity="0.22"/>')
    svg.append('      <stop offset="100%" stop-color="#10b981" stop-opacity="0.02"/>')
    svg.append('    </linearGradient>')
    svg.append('  </defs>')

    svg.append('  <!-- Canvas Background -->')
    svg.append(f'  <rect x="0" y="0" width="{width}" height="{height}" fill="#ffffff"/>')

    # Return Leg Background
    svg.append(f'  <rect x="{x_mid_turn}" y="80" width="{1370 - x_mid_turn}" height="730" rx="10" fill="#f8fafc" stroke="#e2e8f0" stroke-width="1.2"/>')

    # Header
    hw_str = f"HW {hw_local.strftime('%H:%M CEST')} ({hw_row.water_level_m_taw:.2f}m TAW)"
    lw_str = f"LW {lw_local.strftime('%H:%M CEST')} ({lw_row.water_level_m_taw:.2f}m TAW)"

    svg.append('  <!-- ================= HEADER ================= -->')
    svg.append('  <g id="header" transform="translate(0, 30)">')
    svg.append(f'    <text x="{width/2}" y="0" font-size="22" font-weight="900" fill="#0f172a" text-anchor="middle">Traject: Bredene Post 4 ➔ Vosseslag ➔ Bredene Post 4 (6.0 km)</text>')
    svg.append(f'    <text x="{width/2}" y="22" font-size="12" font-weight="600" fill="#64748b" text-anchor="middle">Zaterdag 24 Oktober 2026 • Start {start_hour_cest:02d}:00 CEST ({subtitle_theme.replace("&", "&amp;")}) • 10\' Isochronen</text>')
    svg.append('    <g transform="translate(45, -5)">')
    svg.append('      <rect x="0" y="0" width="230" height="26" rx="5" fill="#f0f9ff" stroke="#bae6fd" stroke-width="1.0"/>')
    svg.append(f'      <text x="12" y="17" font-size="10.5" font-weight="800" fill="#0369a1">🌊 {hw_str}</text>')
    svg.append('    </g>')
    svg.append(f'    <g transform="translate({width - 275}, -5)">')
    svg.append('      <rect x="0" y="0" width="230" height="26" rx="5" fill="#f8fafc" stroke="#cbd5e1" stroke-width="1.0"/>')
    svg.append(f'      <text x="12" y="17" font-size="10.5" font-weight="800" fill="#475569">🌊 {lw_str}</text>')
    svg.append('    </g>')
    svg.append('  </g>')

    # Perspective Banners
    w_out = (x_mid_turn - 12) - 45
    svg.append('  <!-- ================= PERSPECTIVE BANNERS ================= -->')
    svg.append('  <g id="banner_out" transform="translate(45, 80)">')
    svg.append(f'    <rect x="0" y="0" width="{w_out}" height="32" rx="6" fill="#f0f9ff" stroke="#bae6fd" stroke-width="1.2"/>')
    svg.append('    <text x="14" y="21" font-size="11.5" font-weight="800" fill="#0369a1">--&gt; ZWEMRICHTING OOST [NL]</text>')
    svg.append(f'    <text x="{w_out - 14}" y="21" font-size="11" font-weight="800" fill="#0284c7" text-anchor="end">RECHTS = MEESTROOM (VLOEDSTROOM --&gt;)</text>')
    svg.append('  </g>')

    w_ret = 1370 - (x_mid_turn + 12)
    svg.append(f'  <g id="banner_ret" transform="translate({x_mid_turn + 12}, 80)">')
    svg.append(f'    <rect x="0" y="0" width="{w_ret}" height="32" rx="6" fill="#f1f5f9" stroke="#cbd5e1" stroke-width="1.2"/>')
    svg.append('    <text x="14" y="21" font-size="11.5" font-weight="800" fill="#334155">&lt;-- ZWEMRICHTING WEST [FR]</text>')
    svg.append(f'    <text x="{w_ret - 14}" y="21" font-size="11" font-weight="800" fill="#4338ca" text-anchor="end">RECHTS = MEESTROOM (EBSTROOM --&gt;)</text>')
    svg.append('  </g>')

    # Turnaround Buffer
    svg.append(f'  <line x1="{x_mid_turn}" y1="120" x2="{x_mid_turn}" y2="{y_spine_bottom + 15}" stroke="#ef4444" stroke-width="1.8" stroke-dasharray="4,4" opacity="0.6"/>')
    svg.append(f'  <g transform="translate({x_mid_turn}, 168)">')
    svg.append('    <rect x="-16" y="-42" width="32" height="84" rx="16" fill="#ef4444" filter="url(#badgeShadow)"/>')
    svg.append('    <text x="0" y="-24" font-size="14" font-weight="900" fill="#ffffff" text-anchor="middle">↺</text>')
    svg.append('    <text x="0" y="-10" font-size="9" font-weight="900" fill="#ffffff" text-anchor="middle">180°</text>')
    svg.append('    <text x="0" y="4" font-size="8" font-weight="900" fill="#ffffff" text-anchor="middle">KEER</text>')
    svg.append('    <text x="0" y="16" font-size="8" font-weight="900" fill="#ffffff" text-anchor="middle">PUNT</text>')
    svg.append('    <text x="0" y="32" font-size="7.5" font-weight="800" fill="#fecaca" text-anchor="middle">3.00k</text>')
    svg.append('  </g>')

    # Checkpoint Headers
    for cp_i, cp in enumerate(checkpoints_yaml):
        cx = cp["x"]
        is_turn = cp["leg"] in ["out_turn", "ret_turn"]
        lbl_color = "#ef4444" if is_turn else "#0f172a"
        t_nom = nominal_schedule_yaml[cp_i]["time"]

        svg.append(f'  <g transform="translate({cx}, 145)">')
        svg.append(f'    <text x="0" y="0" font-family="monospace" font-size="11" font-weight="900" fill="{lbl_color}" text-anchor="middle">km {cp["km_tot"]}</text>')
        svg.append('    <g transform="translate(0, 16)">')
        svg.append('      <circle cx="-25" cy="-3.5" r="4.5" fill="none" stroke="#64748b" stroke-width="1.2"/>')
        svg.append('      <polyline points="-25,-6 -25,-3.5 -23,-3.5" fill="none" stroke="#64748b" stroke-width="1.1"/>')
        svg.append(f'      <text x="-16" y="0" font-family="monospace" font-size="10" font-weight="700" fill="#64748b" text-anchor="start">{t_nom}</text>')
        svg.append('    </g>')
        if cp_i == 0:
            svg.append('    <text x="0" y="-16" font-size="9.5" font-weight="800" fill="#0284c7" text-anchor="middle">Bredene P4 (Start)</text>')
        elif cp_i == 4:
            svg.append('    <text x="-6" y="-16" font-size="9" font-weight="800" fill="#ef4444" text-anchor="end">Vosseslag (Aankomst)</text>')
        elif cp_i == 5:
            svg.append('    <text x="6" y="-16" font-size="9" font-weight="800" fill="#ef4444" text-anchor="start">Vosseslag (Vertrek)</text>')
        elif cp_i == 9:
            svg.append('    <text x="0" y="-16" font-size="9.5" font-weight="800" fill="#0284c7" text-anchor="middle">Bredene P4 (Finish)</text>')
        svg.append('  </g>')

    # Starttijd-venster
    svg.append(f'  <polygon points="{envelope_yaml["poly_env_heen"]}" fill="url(#envelopeGrad)" stroke="none"/>')
    svg.append(f'  <polygon points="{envelope_yaml["poly_env_terug"]}" fill="url(#envelopeGrad)" stroke="none"/>')
    svg.append(f'  <path d="{poly_to_path(envelope_yaml["env_heen_top"])}" fill="none" stroke="#10b981" stroke-width="1.0" stroke-dasharray="3,3" opacity="0.65"/>')
    svg.append(f'  <path d="{poly_to_path(envelope_yaml["env_heen_bot"])}" fill="none" stroke="#10b981" stroke-width="1.0" stroke-dasharray="3,3" opacity="0.65"/>')
    svg.append(f'  <path d="{poly_to_path(envelope_yaml["env_terug_top"])}" fill="none" stroke="#10b981" stroke-width="1.0" stroke-dasharray="3,3" opacity="0.65"/>')
    svg.append(f'  <path d="{poly_to_path(envelope_yaml["env_terug_bot"])}" fill="none" stroke="#10b981" stroke-width="1.0" stroke-dasharray="3,3" opacity="0.65"/>')

    # Isochrones (10-minute resolution)
    for iso in isochrones_yaml:
        if len(iso["pts_h"]) >= 2:
            ph = poly_to_path(iso["pts_h"])
            svg.append(f'    <path d="{ph}" fill="none" stroke="#94a3b8" stroke-width="0.9" stroke-dasharray="4,4" opacity="0.75"/>')

        if len(iso["pts_t"]) >= 2:
            pt = poly_to_path(iso["pts_t"])
            svg.append(f'    <path d="{pt}" fill="none" stroke="#94a3b8" stroke-width="0.9" stroke-dasharray="4,4" opacity="0.75"/>')

        if iso["has_turn_bridge"] and iso["py_turn"] is not None:
            y_br = iso["py_turn"]
            svg.append(f'    <line x1="{x_heen[4]}" y1="{y_br:.1f}" x2="{x_terug[0]}" y2="{y_br:.1f}" stroke="#94a3b8" stroke-width="1.2" stroke-dasharray="2,2"/>')
            render_center_label = True
            if scale_t < 1.7 and (iso["clock_min"] % 20 != 0):
                render_center_label = False
            if y_br > 218.0 and render_center_label:
                svg.append(f'    <text x="{x_mid_turn}" y="{y_br - 4:.1f}" font-family="monospace" font-size="9" font-weight="800" fill="#475569" text-anchor="middle" paint-order="stroke" stroke="#ffffff" stroke-width="2.5">{iso["time"]}</text>')

        # Labels entering along first spine
        if len(iso["pts_h"]) > 1 and iso["pts_h"][0][0] <= x_heen[0] + 2 and y_spine_top <= iso["pts_h"][0][1] <= y_spine_bottom:
            p0 = iso["pts_h"][0]
            p1 = iso["pts_h"][min(5, len(iso["pts_h"])-1)]
            angle = float(np.degrees(np.arctan2(p1[1] - p0[1], p1[0] - p0[0])))
            svg.append(f'    <text x="{p0[0] + 10:.1f}" y="{p0[1] - 4:.1f}" font-family="monospace" font-size="8.5" font-weight="800" fill="#64748b" transform="rotate({angle:.1f} {p0[0]+10:.1f} {p0[1]-4:.1f})" paint-order="stroke" stroke="#ffffff" stroke-width="3">{iso["time"]}</text>')

        # Labels entering along bottom border
        if len(iso["pts_h"]) > 1 and iso["pts_h"][0][1] >= y_spine_bottom - 5:
            p0 = iso["pts_h"][0]
            if x_heen[0] + 30 <= p0[0] <= x_heen[-1] - 40:
                p1 = iso["pts_h"][min(5, len(iso["pts_h"])-1)]
                angle = float(np.degrees(np.arctan2(p1[1] - p0[1], p1[0] - p0[0])))
                svg.append(f'    <text x="{p0[0] + 12:.1f}" y="{p0[1] - 4:.1f}" font-family="monospace" font-size="8.5" font-weight="800" fill="#64748b" transform="rotate({angle:.1f} {p0[0]+12:.1f} {p0[1]-4:.1f})" paint-order="stroke" stroke="#ffffff" stroke-width="3">{iso["time"]}</text>')

        if len(iso["pts_t"]) > 1 and iso["pts_t"][0][1] >= y_spine_bottom - 5:
            p0 = iso["pts_t"][0]
            if x_terug[0] + 10 <= p0[0] <= x_terug[-1] - 15:
                p1 = iso["pts_t"][min(5, len(iso["pts_t"])-1)]
                angle = float(np.degrees(np.arctan2(p1[1] - p0[1], p1[0] - p0[0])))
                svg.append(f'    <text x="{p0[0] + 12:.1f}" y="{p0[1] - 4:.1f}" font-family="monospace" font-size="8.5" font-weight="800" fill="#64748b" transform="rotate({angle:.1f} {p0[0]+12:.1f} {p0[1]-4:.1f})" paint-order="stroke" stroke="#ffffff" stroke-width="3">{iso["time"]}</text>')

    # Vertical Spines & Current Staven
    for s_info in spine_data_yaml:
        cx = s_info["cx"]
        cp = s_info["checkpoint"]
        is_turn = cp["leg"] in ["out_turn", "ret_turn"]
        spine_col = "#ef4444" if is_turn else "#94a3b8"

        svg.append(f'    <line x1="{cx}" y1="{y_spine_top}" x2="{cx}" y2="{y_spine_bottom}" stroke="{spine_col}" stroke-width="{1.8 if is_turn else 1.2}"/>')

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
                svg.append(f'    <rect x="{x_b:.1f}" y="{y_bar:.1f}" width="{w_b:.1f}" height="{bar_h}" rx="1.5" fill="{base_col}" opacity="0.9"{stroke_attr}/>')
                if not b["is_out"]:
                    svg.append(f'    <rect x="{x_b:.1f}" y="{y_bar:.1f}" width="{w_b:.1f}" height="{bar_h}" rx="1.5" fill="url(#whiteCrossHatch)"/>')

            svg.append(f'    <line x1="{cx - 2}" y1="{by:.1f}" x2="{cx + 2}" y2="{by:.1f}" stroke="#64748b" stroke-width="1"/>')

    # 9 Isotachs
    for crv in curves_yaml:
        ph = poly_to_path(crv["pts_heen"])
        pt = poly_to_path(crv["pts_terug"])
        svg.append(f'    <path d="{ph}" fill="none" stroke="{crv["color"]}" stroke-width="{crv["lw"]}" stroke-linecap="round" opacity="{crv["opacity"]}"/>')
        svg.append(f'    <path d="{pt}" fill="none" stroke="{crv["color"]}" stroke-width="{crv["lw"]}" stroke-linecap="round" opacity="{crv["opacity"]}"/>')

    # Finish Table
    x_tbl_v = x_terug[-1] + 32.0
    x_tbl_dt = x_tbl_v + 58.0
    y_tbl_head = 148.0

    svg.append('  <g id="finish_table">')
    svg.append(f'    <text x="{x_tbl_v}" y="{y_tbl_head:.1f}" font-size="10.5" font-weight="900" fill="#0f172a">v (m/s)</text>')
    svg.append(f'    <text x="{x_tbl_dt}" y="{y_tbl_head:.1f}" font-size="10.5" font-weight="900" fill="#0f172a">Δt (min)</text>')
    svg.append(f'    <line x1="{x_tbl_v - 5}" y1="{y_tbl_head + 5:.1f}" x2="{x_tbl_dt + 45}" y2="{y_tbl_head + 5:.1f}" stroke="#cbd5e1" stroke-width="1.0"/>')

    for crv, sp_info in zip(curves_yaml, speeds_analyzed_yaml):
        py_row = crv["last_py"]
        col = crv["color"]
        is_nom = (sp_info["speed_mps"] == 1.0)
        weight = "900" if is_nom else "700"

        svg.append(f'    <text x="{x_tbl_v + 12}" y="{py_row + 3.5:.1f}" font-family="monospace" font-size="10" font-weight="{weight}" fill="{col}" text-anchor="middle">{sp_info["speed_mps"]:.1f}</text>')
        if is_nom:
            svg.append(f'    <text x="{x_tbl_dt + 20}" y="{py_row + 3.5:.1f}" font-family="monospace" font-size="9" font-weight="900" fill="#16a34a" text-anchor="middle">{sp_info["eta_finish"]} ETA</text>')
        else:
            svg.append(f'    <text x="{x_tbl_dt + 20}" y="{py_row + 3.5:.1f}" font-family="monospace" font-size="10" font-weight="{weight}" fill="{col}" text-anchor="middle">{sp_info["delta_min"]}</text>')
    svg.append('  </g>')

    # 8 Schalingsbalken
    y_ribbon = 818.0
    w_box = 115.0
    h_box = 48.0

    for k, leg in enumerate(leg_breakdown_yaml):
        if k < 4:
            x_l = x_heen[k]
            x_r = x_heen[k + 1]
            bg_col = "#ffffff"
        else:
            x_l = x_terug[k - 4]
            x_r = x_terug[k - 3]
            bg_col = "#f1f5f9"

        x_b = x_l + ((x_r - x_l) - w_box) / 2.0
        x_mid_leg = (x_l + x_r) / 2.0

        svg.append(f'    <line x1="{x_mid_leg}" y1="{y_spine_bottom}" x2="{x_mid_leg}" y2="{y_ribbon}" stroke="#cbd5e1" stroke-width="0.9" stroke-dasharray="2,2"/>')
        svg.append(f'    <g transform="translate({x_b:.1f}, {y_ribbon:.1f})">')
        svg.append(f'      <rect x="0" y="0" width="{w_box}" height="{h_box}" rx="6" fill="{bg_col}" stroke="#cbd5e1" stroke-width="1.0" filter="url(#softShadow)"/>')

        d_w = leg["dist_swimmer_m"]
        d_u = leg["dist_current_m"]
        u_avg = leg["u_avg_mps"]
        dt_min = leg["dt_min"]
        is_flood = leg["is_flood"]
        cur_col = "#0284c7" if is_flood else "#4338ca"

        x_trk = 12.0
        y_trk = 7.0
        h_trk = 11.0

        if d_u >= 0:
            w_track = 75.0
            scale_bar = w_track / 750.0
            w_w = d_w * scale_bar
            w_u = d_u * scale_bar
            x_tick = x_trk + w_track

            svg.append(f'      <rect x="{x_trk:.1f}" y="{y_trk}" width="{w_track}" height="{h_trk}" rx="2" fill="#e2e8f0"/>')
            svg.append(f'      <rect x="{x_trk:.1f}" y="{y_trk}" width="{w_w:.1f}" height="{h_trk}" rx="2" fill="#16a34a"/>')
            svg.append(f'      <rect x="{x_trk + w_w:.1f}" y="{y_trk}" width="{w_u:.1f}" height="{h_trk}" rx="2" fill="{cur_col}"/>')
            if k >= 4:
                svg.append(f'      <rect x="{x_trk + w_w:.1f}" y="{y_trk}" width="{w_u:.1f}" height="{h_trk}" rx="2" fill="url(#whiteCrossHatch)"/>')
            cur_str = f"+{int(round(d_u))}m"
        else:
            W_total = 85.0
            x_tick = x_trk + W_total * (750.0 / d_w)
            w_w = W_total
            w_u = (x_trk + W_total) - x_tick

            svg.append(f'      <rect x="{x_trk:.1f}" y="{y_trk}" width="{w_w:.1f}" height="{h_trk}" rx="2" fill="#e2e8f0"/>')
            svg.append(f'      <rect x="{x_trk:.1f}" y="{y_trk}" width="{w_w:.1f}" height="{h_trk}" rx="2" fill="#16a34a"/>')
            svg.append(f'      <rect x="{x_tick:.1f}" y="{y_trk}" width="{w_u:.1f}" height="{h_trk}" rx="2" fill="{cur_col}" fill-opacity="0.6"/>')
            if k >= 4:
                svg.append(f'      <rect x="{x_tick:.1f}" y="{y_trk}" width="{w_u:.1f}" height="{h_trk}" rx="2" fill="url(#whiteCrossHatch)"/>')
            svg.append(f'      <polygon points="{x_tick + w_u - 2:.1f},{y_trk + 2.5} {x_tick + 2:.1f},{y_trk + 5.5} {x_tick + w_u - 2:.1f},{y_trk + 8.5}" fill="#ffffff" opacity="0.95"/>')
            cur_str = f"{int(round(d_u))}m"

        svg.append(f'      <line x1="{x_tick:.1f}" y1="{y_trk - 3}" x2="{x_tick:.1f}" y2="{y_trk + h_trk + 3}" stroke="#0f172a" stroke-width="2.0"/>')
        svg.append(f'      <text x="{w_box/2:.1f}" y="29" font-family="monospace" font-size="8.5" font-weight="800" text-anchor="middle"><tspan fill="#16a34a">{int(round(d_w))}m</tspan> <tspan fill="{cur_col}">{cur_str}</tspan></text>')
        svg.append(f'      <text x="{w_box/2:.1f}" y="40" font-family="monospace" font-size="8" font-weight="700" fill="#64748b" text-anchor="middle">u = {u_avg:+.2f} m/s • {dt_min:.1f}\'</text>')
        svg.append('    </g>')

    # Bottom Legend
    y_leg = 890.0
    w_leg = 1330.0
    x_leg = (width - w_leg) / 2.0

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

    svg.append('    <g transform="translate(325, 16)">')
    svg.append('      <rect x="0" y="2" width="22" height="12" fill="url(#envelopeGrad)"/>')
    svg.append('      <line x1="0" y1="2" x2="22" y2="2" stroke="#10b981" stroke-width="1.0" stroke-dasharray="2,2"/>')
    svg.append('      <line x1="0" y1="14" x2="22" y2="14" stroke="#10b981" stroke-width="1.0" stroke-dasharray="2,2"/>')
    svg.append('      <text x="30" y="10" font-size="10" font-weight="800" fill="#0f172a">Starttijd-venster: <tspan font-weight="600" fill="#64748b">±30 min marge</tspan></text>')
    svg.append('    </g>')

    svg.append('    <g transform="translate(560, 16)">')
    svg.append('      <text x="0" y="10" font-size="10.5" font-weight="900" fill="#0284c7">Vloedstroom:</text>')
    svg.append('      <text x="75" y="10" font-size="9.5" font-weight="700" fill="#64748b">heen</text>')
    svg.append('      <rect x="102" y="2" width="12" height="10" rx="2" fill="#0284c7"/>')
    svg.append('      <text x="122" y="10" font-size="9.5" font-weight="700" fill="#64748b">terug</text>')
    svg.append('      <rect x="154" y="2" width="14" height="10" rx="2" fill="#0284c7"/>')
    svg.append('      <rect x="154" y="2" width="14" height="10" rx="2" fill="url(#whiteCrossHatch)"/>')

    svg.append('      <text x="195" y="10" font-size="10.5" font-weight="900" fill="#4338ca">Ebstroom:</text>')
    svg.append('      <text x="256" y="10" font-size="9.5" font-weight="700" fill="#64748b">heen</text>')
    svg.append('      <rect x="283" y="2" width="12" height="10" rx="2" fill="#4338ca"/>')
    svg.append('      <text x="303" y="10" font-size="9.5" font-weight="700" fill="#64748b">terug</text>')
    svg.append('      <rect x="335" y="2" width="14" height="10" rx="2" fill="#4338ca"/>')
    svg.append('      <rect x="335" y="2" width="14" height="10" rx="2" fill="url(#whiteCrossHatch)"/>')
    svg.append('    </g>')

    svg.append('    <g transform="translate(980, 16)">')
    svg.append('      <line x1="0" y1="7" x2="24" y2="7" stroke="#94a3b8" stroke-width="1.2" stroke-dasharray="3,3"/>')
    svg.append(f'      <text x="32" y="10" font-size="10" font-weight="800" fill="#0f172a">Isochronen: <tspan font-weight="600" fill="#64748b">Lijnen gelijke tijd ({iso_step_min}\')</tspan></text>')
    svg.append('    </g>')
    svg.append('  </g>')

    svg.append('  <!-- Footer -->')
    svg.append('  <g id="footer" transform="translate(45, 972)">')
    svg.append('    <text x="0" y="0" font-size="11" font-weight="600" fill="#94a3b8">CSCM • Dynamisch Kustzwem-Trajectmodel • Copernicus CMEMS 2D &amp; HIC KiWIS Operational Forecasts (25m Grid)</text>')
    svg.append(f'    <text x="{w_leg}" y="0" font-size="11" font-weight="800" fill="#94a3b8" text-anchor="end">ONTWERP v{var_id} (A3 LIGGEND)</text>')
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
    variants = [
        ("7a", 9, "Ochtend Kentering & Vroege Vloed • Gebalanceerd"),
        ("7b", 13, "Piekvloed Heenweg & Kentering Terugweg • Snelle Heenweg"),
        ("7c", 17, "Eb Tegenstroom Heenweg & Ebstroom-Surf Terugweg • Snelle Terugweg"),
    ]
    for var_id, start_hour, theme in variants:
        generate_variant(var_id, start_hour, theme)
    print("\n" + "=" * 70)
    print("All 3 Variants (7a, 7b, 7c) successfully generated!")
    print("=" * 70)


if __name__ == "__main__":
    main()
