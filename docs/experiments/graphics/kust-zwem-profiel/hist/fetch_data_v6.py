#!/usr/bin/env python3
"""
Data Retrieval & Kinematics Pre-computation for Coastal Swim Trajectory Profile v6.

Authentic Data Sources for Saturday 24 October 2026:
1. Copernicus Marine Service (CMEMS): 1.5 km hydrodynamic 2D current forecasts (uo, vo)
   retrieved via cscm.broker.get_broker().query('current', ...).
2. Flemish Hydro Information Centre (HIC): KiWIS operational water level forecasts (KT-Last)
   and astronomical extreme predictions via cscm.broker.get_broker().query('tide', ...).
3. Alongshore Trajectory Kinematics (cscm.kinematics.AlongshoreTrajectoryCalculator):
   Discrete 25m step-by-step numerical integration projecting 2D currents onto coastal route tangents.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import math
import numpy as np
import pandas as pd
import yaml

from cscm.broker import get_broker

HIST_DIR = Path(__file__).resolve().parent
import sys
if str(HIST_DIR) not in sys.path:
    sys.path.insert(0, str(HIST_DIR))
from kinematics import AlongshoreTrajectoryCalculator, Checkpoint

OUTPUT_YAML = HIST_DIR / "data_to_plot_v6.yaml"


def main():
    print("=" * 60)
    print("CSCM Kustzwem-Profiel v6: Fetching Authentic Data (Sat 24 Oct 2026)")
    print("=" * 60)

    broker = get_broker()

    # 1. Define Route Geometry: 5 checkpoints (0.0k to 3.0k), unfolded into 10 checkpoints
    # Based on Flemish coastal chainage markers (be-full-coast-locations.yaml):
    # - 34k500: Bredene Post 4 (Droge Opgang) -> 51.24989 N, 2.96226 E
    # - 35k250: +750m                       -> 51.25330 N, 2.97156 E
    # - 36k000: +1500m                      -> 51.25721 N, 2.98033 E
    # - 36k750: +2250m                      -> 51.26129 N, 2.98890 E
    # - 37k500: Vosseslag (Turnaround)       -> 51.26538 N, 2.99748 E
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

    # 2. Target Time Window: Saturday 24 October 2026
    # Departure at 10:00 CEST (08:00 UTC)
    t_start_utc = datetime(2026, 10, 24, 8, 0, tzinfo=timezone.utc)
    t_end_query = datetime(2026, 10, 24, 16, 0, tzinfo=timezone.utc)

    print("Querying HIC operational tidal forecast for Oostende / Bredene...")
    tide_res = broker.query(
        "tide",
        station="OST",
        start_time=datetime(2026, 10, 24, 6, 0, tzinfo=timezone.utc),
        end_time=t_end_query,
        source="forecast",
        time_offset_minutes=7.0,  # +7 min phase shift for Bredene
    )
    df_tide = tide_res.to_dataframe()
    hw_row = df_tide.loc[df_tide["water_level_m_taw"].idxmax()]
    lw_row = df_tide.loc[df_tide["water_level_m_taw"].idxmin()]
    hw_local = hw_row.timestamp + pd.Timedelta(hours=2)
    lw_local = lw_row.timestamp + pd.Timedelta(hours=2)
    print(f"  High Water: {hw_local.strftime('%H:%M')} CEST ({hw_row.water_level_m_taw:.2f} m TAW)")
    print(f"  Low Water:  {lw_local.strftime('%H:%M')} CEST ({lw_row.water_level_m_taw:.2f} m TAW)")

    # 3. Query Copernicus CMEMS currents across all 5 coordinates
    print("Querying Copernicus CMEMS hydrodynamic currents along course...")
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
        start_time=datetime(2026, 10, 24, 7, 0, tzinfo=timezone.utc),
        end_time=t_end_query,
        avoid_boundary_damping=True,
    )
    df_curr = curr_res.to_dataframe()
    print(f"  Retrieved {len(df_curr)} current vector records across {len(coords_unique)} checkpoints.")

    # Spatial-temporal current lookup function using nearest CMEMS grid cell
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

    # 4. Canvas Geometry & Scaling Parameters (DIN A3 Landscape)
    width = 1420
    height = 1004
    y_spine_top = 170.0
    y_spine_bottom = 790.0
    matrix_height = y_spine_bottom - y_spine_top  # 620.0 px
    y_ref = 390.0
    scale_t = 1.90  # px per minute
    scale_v = 40.0  # px per 1.0 m/s current
    iso_step_min = 15  # 15-minute isochrones (28.5 px spacing)

    x_heen = [105.0, 230.0, 355.0, 480.0, 605.0]
    x_terug = [685.0, 810.0, 935.0, 1060.0, 1185.0]
    x_mid_turn = 645.0

    def s_to_x_heen(s_km: float) -> float:
        return 105.0 + (s_km / 3.0) * (605.0 - 105.0)

    def s_to_x_terug(s_km: float) -> float:
        # On return, distance covered is (3.0 - s_km)
        return 685.0 + ((3.0 - s_km) / 3.0) * (1185.0 - 685.0)

    # 5. Run Alongshore Kinematics Calculator for Nominal Swimmer (1.0 m/s)
    print("Simulating nominal reference swimmer (1.0 m/s, ds = 25m)...")
    calc_out = AlongshoreTrajectoryCalculator(checkpoints=kinematics_checkpoints[:5], ds_step_m=25.0)
    traj_out_nom = calc_out.calculate_trajectory(
        speed_mps=1.0,
        start_time_utc=t_start_utc,
        current_fn=current_lookup_fn,
    )

    t_turn_utc = traj_out_nom.finish_time_utc
    calc_ret = AlongshoreTrajectoryCalculator(checkpoints=kinematics_checkpoints[5:], ds_step_m=25.0)
    traj_ret_nom = calc_ret.calculate_trajectory(
        speed_mps=1.0,
        start_time_utc=t_turn_utc,
        current_fn=current_lookup_fn,
    )

    total_nominal_sec = traj_out_nom.total_duration_sec + traj_ret_nom.total_duration_sec
    total_nominal_min = total_nominal_sec / 60.0
    nominal_finish_utc = traj_ret_nom.finish_time_utc
    nominal_finish_local = nominal_finish_utc + timedelta(hours=2)

    print(f"  Outbound duration: {traj_out_nom.total_duration_min:.1f} min | Arrival at Vosseslag: {(t_turn_utc + timedelta(hours=2)).strftime('%H:%M:%S')} CEST")
    print(f"  Return duration:   {traj_ret_nom.total_duration_min:.1f} min | Finish at Bredene P4: {nominal_finish_local.strftime('%H:%M:%S')} CEST")
    print(f"  Total duration:    {total_nominal_min:.1f} min")

    # Reference trajectory interpolation tables:
    # Heenweg: s_km (0..3) -> t_min from departure
    s_heen_ref = [p[0] for p in traj_out_nom.trajectory_points]
    t_heen_ref = [(p[1] - t_start_utc).total_seconds() / 60.0 for p in traj_out_nom.trajectory_points]

    def get_t_ref_heen(s_km: float) -> float:
        return float(np.interp(s_km, s_heen_ref, t_heen_ref))

    # Terugweg: s_km (3..0) -> t_min from departure
    # Note: on return, s_km goes 3.0 -> 0.0. To use np.interp, reverse arrays to strictly increasing
    s_terug_ref = [p[0] for p in traj_ret_nom.trajectory_points]
    t_terug_ref = [(p[1] - t_start_utc).total_seconds() / 60.0 for p in traj_ret_nom.trajectory_points]
    s_terug_rev = list(reversed(s_terug_ref))
    t_terug_rev = list(reversed(t_terug_ref))

    def get_t_ref_terug(s_km: float) -> float:
        return float(np.interp(s_km, s_terug_rev, t_terug_rev))

    # Build nominal schedule (10 checkpoints: 5 outbound + 5 return)
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

    # Build leg breakdown (8 legs)
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

    # 6. Run 9-Isotach Velocity Fan (0.6 to 1.4 m/s)
    print("Computing 9-isotach velocity fan (0.6 to 1.4 m/s) with SVG curve points...")
    fan_speeds = [0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4]
    fan_colors = {
        0.6: "#ea580c",
        0.7: "#f97316",
        0.8: "#f59e0b",
        0.9: "#84cc16",
        1.0: "#16a34a",
        1.1: "#10b981",
        1.2: "#06b6d4",
        1.3: "#0ea5e9",
        1.4: "#2563eb",
    }

    speeds_analyzed_yaml = []
    curves_yaml = []

    for v in fan_speeds:
        t_out = calc_out.calculate_trajectory(speed_mps=v, start_time_utc=t_start_utc, current_fn=current_lookup_fn)
        t_ret = calc_ret.calculate_trajectory(speed_mps=v, start_time_utc=t_out.finish_time_utc, current_fn=current_lookup_fn)
        tot_sec = t_out.total_duration_sec + t_ret.total_duration_sec
        tot_min = tot_sec / 60.0
        fin_local = t_ret.finish_time_utc + timedelta(hours=2)
        delta_m = (tot_sec - total_nominal_sec) / 60.0
        sign_str = "+" if delta_m > 0.05 else ("" if abs(delta_m) <= 0.05 else "-")
        delta_str = f"{sign_str}{abs(delta_m):.0f}'" if abs(delta_m) > 0.05 else "0'"

        # Convert outbound trajectory points to (px, py)
        pts_heen = []
        for s_km, t_utc in t_out.trajectory_points:
            t_val = (t_utc - t_start_utc).total_seconds() / 60.0
            t_r = get_t_ref_heen(s_km)
            px = s_to_x_heen(s_km)
            py = y_ref + (t_val - t_r) * scale_t
            pts_heen.append([round(px, 1), round(py, 1)])

        # Convert return trajectory points to (px, py)
        pts_terug = []
        for s_km, t_utc in t_ret.trajectory_points:
            t_val = (t_utc - t_start_utc).total_seconds() / 60.0
            t_r = get_t_ref_terug(s_km)
            px = s_to_x_terug(s_km)
            py = y_ref + (t_val - t_r) * scale_t
            pts_terug.append([round(px, 1), round(py, 1)])

        speeds_analyzed_yaml.append({
            "speed_mps": float(v),
            "color": fan_colors[v],
            "eta_finish": fin_local.strftime("%H:%M"),
            "delta_min": delta_str,
            "total_time_min": round(tot_min, 1),
            "lw": 3.0 if v == 1.0 else 1.5,
            "opacity": 1.0 if v == 1.0 else 0.88,
        })

        curves_yaml.append({
            "speed_mps": float(v),
            "color": fan_colors[v],
            "lw": 3.0 if v == 1.0 else 1.5,
            "opacity": 1.0 if v == 1.0 else 0.88,
            "pts_heen": pts_heen,
            "pts_terug": pts_terug,
            "last_py": pts_terug[-1][1],
        })
        print(f"  v={v:.1f} m/s: {tot_min:.1f} min | ETA: {fin_local.strftime('%H:%M')} ({delta_str})")

    # 7. Starttijd-Venster (±30 min envelope band)
    print("Computing start window envelope band (±30 min)...")
    t_start_early = t_start_utc - timedelta(minutes=30)
    t_start_late = t_start_utc + timedelta(minutes=30)

    t_out_early = calc_out.calculate_trajectory(speed_mps=1.0, start_time_utc=t_start_early, current_fn=current_lookup_fn)
    t_ret_early = calc_ret.calculate_trajectory(speed_mps=1.0, start_time_utc=t_out_early.finish_time_utc, current_fn=current_lookup_fn)

    t_out_late = calc_out.calculate_trajectory(speed_mps=1.0, start_time_utc=t_start_late, current_fn=current_lookup_fn)
    t_ret_late = calc_ret.calculate_trajectory(speed_mps=1.0, start_time_utc=t_out_late.finish_time_utc, current_fn=current_lookup_fn)

    env_heen_top = []
    for s_km, t_utc in t_out_early.trajectory_points:
        t_val = (t_utc - t_start_utc).total_seconds() / 60.0
        py = y_ref + (t_val - get_t_ref_heen(s_km)) * scale_t
        env_heen_top.append([round(s_to_x_heen(s_km), 1), round(py, 1)])

    env_heen_bot = []
    for s_km, t_utc in t_out_late.trajectory_points:
        t_val = (t_utc - t_start_utc).total_seconds() / 60.0
        py = y_ref + (t_val - get_t_ref_heen(s_km)) * scale_t
        env_heen_bot.append([round(s_to_x_heen(s_km), 1), round(py, 1)])

    env_terug_top = []
    for s_km, t_utc in t_ret_early.trajectory_points:
        t_val = (t_utc - t_start_utc).total_seconds() / 60.0
        py = y_ref + (t_val - get_t_ref_terug(s_km)) * scale_t
        env_terug_top.append([round(s_to_x_terug(s_km), 1), round(py, 1)])

    env_terug_bot = []
    for s_km, t_utc in t_ret_late.trajectory_points:
        t_val = (t_utc - t_start_utc).total_seconds() / 60.0
        py = y_ref + (t_val - get_t_ref_terug(s_km)) * scale_t
        env_terug_bot.append([round(s_to_x_terug(s_km), 1), round(py, 1)])

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

    # 8. Compute Isochrones on 15-Minute Resolution
    print("Computing isochrones on 15-minute resolution...")
    isochrones_yaml = []
    s_fine_heen = np.linspace(0.0, 3.0, 60)
    s_fine_terug = np.linspace(3.0, 0.0, 60)

    for m in range(-30, 421, iso_step_min):
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

    # 9. Compute Vertical Current Staven along Spines from Authentic CMEMS
    print("Computing vertical spine current staven from Copernicus CMEMS...")
    spine_data_yaml = []
    for cp_idx, cp in enumerate(checkpoints_yaml):
        cx = cp["x"]
        lat = cp["lat"]
        lon = cp["lon"]
        t_nom = nom_times_min[cp_idx]
        is_out = cp["leg"] in ["out", "out_turn"]

        bars = []
        for m in range(-30, 421, iso_step_min):
            py = y_ref + (m - t_nom) * scale_t
            if y_spine_top <= py <= y_spine_bottom:
                t_sample_utc = t_start_utc + timedelta(minutes=m)
                u_east, v_north = current_lookup_fn(lat, lon, t_sample_utc)

                # Project along swimming bearing (65° outbound, 245° return)
                bearing = 65.0 if is_out else 245.0
                u_fwd = calc_out.project_current_alongshore(u_east, v_north, bearing)
                # Physical alongshore current along 65° (NE towards NL)
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

    # 10. Assemble Complete YAML Data Contract
    data_payload = {
        "title": "CSCM KUSTZWEM-TRAJECTPROFIEL v6",
        "route": "Bredene Post 4 ➔ Vosseslag ➔ Bredene Post 4 (6.0 km Heen-en-Terug)",
        "date": "Zaterdag 24 Oktober 2026",
        "start_time": "10:00 CEST (08:00 UTC)",
        "geometry": {
            "format": "DIN A3/A4 Landscape (ratio 1.414)",
            "width": width,
            "height": height,
            "y_spine_top": y_spine_top,
            "y_spine_bottom": y_spine_bottom,
            "matrix_height": matrix_height,
            "y_ref": y_ref,
            "vertical_scale_px_per_min": scale_t,
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

    with open(OUTPUT_YAML, "w", encoding="utf-8") as f:
        yaml.dump(data_payload, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    print(f"\nSuccessfully generated authentic YAML data contract: {OUTPUT_YAML}")
    print("=" * 60)


if __name__ == "__main__":
    main()
