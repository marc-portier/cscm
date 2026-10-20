#!/usr/bin/env python3
"""
Generator for Coastal Swim Trajectory Profile v5 (Kustzwem-Profiel v5).

Master Improvements for v5 (Consensus from pair-programming dialogue):
1. DIN A3/A4 Landscape Geometry (ratio sqrt(2) ≈ 1.414):
   - Canvas set to 1420 x 1004 px, perfectly filling A3 prints and presentation slides.
   - Vertically zoomed into the core operational window (±40 min around reference swimmer).
   - Vertical scale expanded to 6.55 px/min for maximum breathing room between isochrones.
   - Horizontal margins reclaimed: 8 etappe columns expanded to dx = 125 px.
2. Soft Green Starttijd-Venster (Envelope Band):
   - Eliminated 4 competing green dashed lines and left-side badges.
   - Replaced by a subtle, translucent green background corridor (±30 min departure margin)
     enclosing the nominal trajectory and stopping cleanly at the turnaround spines.
3. Decoupled Turnaround Corridor ("Niemandsland"):
   - Outbound leg (0k0 -> 3k0) and return leg (3k0 -> 6k0) strictly disconnected.
   - Zero crossing lines for isotachs; isochrones bridged horizontally with timestamps.
   - Compact 180° turnaround badge positioned cleanly at the top of the corridor.
4. Strict Physical Tidal Current Color Logic:
   - Blauw (#0284c7) = Vloedstroom (oostwaarts).
   - Paars (#4338ca) = Ebstroom (westwaarts).
   - Gearceerd (#diagonalHatch) = Terugweg (omgekeerde strandblik).
   - Geen oranje meer voor stroom (oranje blijft exclusief gereserveerd voor trage zwemmers!).
   - Geen verwarrende groene kentering-stip meer (stroomsterkte is direct de lengte van de staaf).
   - Actieve stroomstaaf (bij nominale doorkomst) krijgt een subtiele donkere rand.
5. 8 Schalingsbalken (All 8 below plot):
   - Arranged in a continuous ribbon underneath the matrix.
   - Distinct 750m black vertical tick mark on the progress track:
     - Tailwind: swimmer covers Dw < 750m, current bridges to the 750m tick.
     - Headwind (Leg 5): swimmer shoots past 750m, hatched blue current subtracts back to 750m.
   - Return leg cards tinted light grey (#f1f5f9).
   - Clean text formula: "Dw m + Du m (u = ... m/s • dt')".
6. Isochronen & Speed Fan:
   - 10-minute isochrone resolution, dashed grey (#94a3b8), with labels following slope.
   - 9 Isotachs (0.6 to 1.4 m/s) with a dedicated two-column finish table:
     v (m/s) and Delta t (min) in '+/- extra/saved minutes'.
7. Streamlined Header & Single-Line Legend:
   - Clean, uncluttered title and perspective banners (ZWEMRICHTING OOST [NL] / WEST [FR]).
   - Compact single-line footer legend.
"""

from pathlib import Path
import subprocess
import yaml
import numpy as np

HIST_DIR = Path(__file__).resolve().parent
OUTPUT_SVG = HIST_DIR / "ontwerp-kustzwem-profiel-v5.svg"
OUTPUT_PNG = HIST_DIR / "ontwerp-kustzwem-profiel-v5.png"
OUTPUT_YAML = HIST_DIR / "data_to_plot_v5.yaml"


def get_triangle_current(t_min):
    """
    Predictable synthetic tidal current u(t) in m/s.
    Period = 180 min (3h).
    Peak flood (+0.60 m/s) at 10:00 (t = 0 min).
    Delta = 0.20 m/s per 15 min.
    Kentering (0.00 m/s) at 10:45 (t = 45 min).
    Peak ebb (-0.60 m/s) at 11:30 (t = 90 min).
    Next kentering (0.00 m/s) at 12:15 (t = 135 min).
    """
    t_mod = (t_min + 90.0) % 180.0
    if t_mod <= 90.0:
        return -0.6 + (t_mod / 90.0) * 1.2
    else:
        return 0.6 - ((t_mod - 90.0) / 90.0) * 1.2


def simulate_swim(v_water, t_start_min=0.0, ds=25.0):
    """
    Numerically integrates swimmer trajectory on fine grid ds = 25m.
    Returns:
      traj_heen: list of (s_m, t_min)
      traj_terug: list of (s_m, t_min)
      leg_stats: list of 8 leg summary dicts
    """
    n_steps_leg = int(750.0 / ds)
    t_curr = t_start_min

    traj_heen = [(0.0, t_curr)]
    leg_stats = []

    # Heenweg: 4 legs of 750m (0 to 3000m), swimming East (NE)
    for leg in range(4):
        t_leg_start = t_curr
        for step in range(n_steps_leg):
            u = get_triangle_current(t_curr)
            v_g = max(0.15, v_water + u)
            dt_sec = ds / v_g
            t_curr += dt_sec / 60.0
            s = (leg * n_steps_leg + step + 1) * ds
            traj_heen.append((s, t_curr))

        dt_leg_min = t_curr - t_leg_start
        dt_leg_sec = dt_leg_min * 60.0
        dist_w = v_water * dt_leg_sec
        dist_u = 750.0 - dist_w
        u_avg = dist_u / dt_leg_sec
        leg_stats.append({
            "leg_idx": leg + 1,
            "name": f"Leg {leg+1}/8",
            "direction": "out",
            "from_km": leg * 0.75,
            "to_km": (leg + 1) * 0.75,
            "t_start_min": t_leg_start,
            "t_end_min": t_curr,
            "dt_min": dt_leg_min,
            "dist_swimmer_m": dist_w,
            "dist_current_m": dist_u,
            "u_avg_mps": u_avg,
            "is_tailwind": dist_u >= 0,
            "is_flood": u_avg >= 0
        })

    # Instant transfer across turnaround buffer
    t_turn_dep = t_curr

    # Terugweg: 4 legs of 750m (3000 to 6000m), swimming West (SW)
    traj_terug = [(3000.0, t_turn_dep)]
    for leg in range(4):
        t_leg_start = t_curr
        for step in range(n_steps_leg):
            u = get_triangle_current(t_curr)
            u_rel = -u  # Swimming West: ebb (-u) is tailwind!
            v_g = max(0.15, v_water + u_rel)
            dt_sec = ds / v_g
            t_curr += dt_sec / 60.0
            s = 3000.0 + (leg * n_steps_leg + step + 1) * ds
            traj_terug.append((s, t_curr))

        dt_leg_min = t_curr - t_leg_start
        dt_leg_sec = dt_leg_min * 60.0
        dist_w = v_water * dt_leg_sec
        dist_u = 750.0 - dist_w
        u_avg = dist_u / dt_leg_sec
        leg_stats.append({
            "leg_idx": leg + 5,
            "name": f"Leg {leg+5}/8",
            "direction": "ret",
            "from_km": (leg + 4) * 0.75,
            "to_km": (leg + 5) * 0.75,
            "t_start_min": t_leg_start,
            "t_end_min": t_curr,
            "dt_min": dt_leg_min,
            "dist_swimmer_m": dist_w,
            "dist_current_m": dist_u,
            "u_avg_mps": u_avg,
            "is_tailwind": dist_u >= 0,
            "is_flood": u_avg < 0  # when opposing on return leg, it is flood!
        })

    return traj_heen, traj_terug, leg_stats


def generate_profile():
    # Canvas dimensions: DIN A3/A4 landscape ratio (1420 x 1004)
    width = 1420
    height = 1004

    # Horizontal Spacing: 8 etappes of dx = 125px + buffer 80px
    dx = 125
    x_start = 140
    x_heen = [x_start + i * dx for i in range(5)]           # 140, 265, 390, 515, 640
    buffer_dx = 80
    x_terug_start = x_heen[-1] + buffer_dx                 # 720
    x_terug = [x_terug_start + i * dx for i in range(5)]  # 720, 845, 970, 1095, 1220
    x_mid_turn = (x_heen[-1] + x_terug[0]) / 2.0           # 680.0
    x_coords = x_heen + x_terug

    # Checkpoint Metadata
    checkpoints = [
        {"idx": 0, "km_tot": "0.00", "label": "0.00 km", "name": "Bredene P4 (Start)", "s_km": 0.0, "leg": "out", "x": x_coords[0]},
        {"idx": 1, "km_tot": "0.75", "label": "0.75 km", "name": "", "s_km": 0.75, "leg": "out", "x": x_coords[1]},
        {"idx": 2, "km_tot": "1.50", "label": "1.50 km", "name": "", "s_km": 1.50, "leg": "out", "x": x_coords[2]},
        {"idx": 3, "km_tot": "2.25", "label": "2.25 km", "name": "", "s_km": 2.25, "leg": "out", "x": x_coords[3]},
        {"idx": 4, "km_tot": "3.00", "label": "3.00 km", "name": "Vosseslag (Aankomst)", "s_km": 3.00, "leg": "out_turn", "x": x_coords[4]},
        {"idx": 5, "km_tot": "3.00", "label": "3.00 km", "name": "Vosseslag (Vertrek)", "s_km": 3.00, "leg": "ret_turn", "x": x_coords[5]},
        {"idx": 6, "km_tot": "3.75", "label": "3.75 km", "name": "", "s_km": 2.25, "leg": "ret", "x": x_coords[6]},
        {"idx": 7, "km_tot": "4.50", "label": "4.50 km", "name": "", "s_km": 1.50, "leg": "ret", "x": x_coords[7]},
        {"idx": 8, "km_tot": "5.25", "label": "5.25 km", "name": "", "s_km": 0.75, "leg": "ret", "x": x_coords[8]},
        {"idx": 9, "km_tot": "6.00", "label": "6.00 km", "name": "Bredene P4 (Finish)", "s_km": 0.0, "leg": "ret", "x": x_coords[9]},
    ]

    # Vertical Geometry: Zoomed into operational core window
    # Window: ±42 minutes around the reference swimmer
    y_spine_top = 190.0
    y_spine_bottom = 740.0
    matrix_height = y_spine_bottom - y_spine_top  # 550.0 px
    y_ref = (y_spine_top + y_spine_bottom) / 2.0  # 465.0 px
    t_window_half_min = 42.0
    scale_t = (matrix_height / 2.0) / t_window_half_min  # ~6.55 px per minute difference

    # 1. Simulate Reference Swimmer (1.0 m/s departing at 10:00)
    traj_heen_ref, traj_terug_ref, legs_ref = simulate_swim(1.0, 0.0, ds=25.0)

    s_heen_ref = np.array([pt[0] for pt in traj_heen_ref])
    t_heen_ref = np.array([pt[1] for pt in traj_heen_ref])
    s_terug_ref = np.array([pt[0] for pt in traj_terug_ref])
    t_terug_ref = np.array([pt[1] for pt in traj_terug_ref])

    def get_t_ref_heen(s_m):
        return float(np.interp(s_m, s_heen_ref, t_heen_ref))

    def get_t_ref_terug(s_m):
        return float(np.interp(s_m, s_terug_ref, t_terug_ref))

    def s_to_x_heen(s_m):
        return x_heen[0] + (s_m / 3000.0) * (x_heen[4] - x_heen[0])

    def s_to_x_terug(s_m):
        return x_terug[0] + ((s_m - 3000.0) / 3000.0) * (x_terug[4] - x_terug[0])

    # Checkpoint nominal arrival times
    nom_times_str = []
    nom_times_min = []
    for cp in checkpoints:
        if cp["leg"] in ["out", "out_turn"]:
            t_m = get_t_ref_heen(cp["s_km"] * 1000.0)
        else:
            t_m = get_t_ref_terug((6.0 - cp["s_km"]) * 1000.0)
        nom_times_min.append(t_m)
        tot_m = int(round(t_m))
        hh = 10 + (tot_m // 60)
        mm = tot_m % 60
        nom_times_str.append(f"{hh:02d}:{mm:02d}")

    # 2. Compute 9 Isotachs (0.6 to 1.4 m/s) on Fine Grid
    speeds = [0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4]
    colors = {
        0.6: "#ea580c", 0.7: "#f97316", 0.8: "#f59e0b", 0.9: "#84cc16",
        1.0: "#16a34a",
        1.1: "#10b981", 1.2: "#06b6d4", 1.3: "#0ea5e9", 1.4: "#2563eb"
    }

    t_fin_ref = traj_terug_ref[-1][1]  # 79.5 min

    isotach_data = []
    for sp in speeds:
        th, tt, _ = simulate_swim(sp, 0.0, ds=25.0)

        pts_heen = []
        for s_m, t_val in th:
            t_r = get_t_ref_heen(s_m)
            py = y_ref + (t_val - t_r) * scale_t
            px = s_to_x_heen(s_m)
            pts_heen.append((px, py))

        pts_terug = []
        for s_m, t_val in tt:
            t_r = get_t_ref_terug(s_m)
            py = y_ref + (t_val - t_r) * scale_t
            px = s_to_x_terug(s_m)
            pts_terug.append((px, py))

        t_fin = tt[-1][1]
        delta_fin_min = t_fin - t_fin_ref
        tot_m = int(round(t_fin))
        hh = 10 + (tot_m // 60)
        mm = tot_m % 60

        if abs(delta_fin_min) < 0.2:
            delta_str = "0'"
        elif delta_fin_min > 0:
            delta_str = f"+{int(round(delta_fin_min))}'"
        else:
            delta_str = f"{int(round(delta_fin_min))}'"

        isotach_data.append({
            "speed": sp,
            "color": colors[sp],
            "lw": 3.0 if sp == 1.0 else 1.5,
            "opacity": 1.0 if sp == 1.0 else 0.88,
            "pts_heen": pts_heen,
            "pts_terug": pts_terug,
            "t_fin_min": t_fin,
            "delta_str": delta_str,
            "eta_finish": f"{hh:02d}:{mm:02d}"
        })

    # 3. Compute Starttijd-Venster (±30 min envelope band)
    th_early, tt_early, _ = simulate_swim(1.0, -30.0, ds=25.0)
    th_late, tt_late, _ = simulate_swim(1.0, +30.0, ds=25.0)

    # Heenweg envelope points
    env_heen_top = [(s_to_x_heen(s_m), y_ref + (t_val - get_t_ref_heen(s_m)) * scale_t) for s_m, t_val in th_early]
    env_heen_bot = [(s_to_x_heen(s_m), y_ref + (t_val - get_t_ref_heen(s_m)) * scale_t) for s_m, t_val in th_late]
    # Return leg envelope points
    env_terug_top = [(s_to_x_terug(s_m), y_ref + (t_val - get_t_ref_terug(s_m)) * scale_t) for s_m, t_val in tt_early]
    env_terug_bot = [(s_to_x_terug(s_m), y_ref + (t_val - get_t_ref_terug(s_m)) * scale_t) for s_m, t_val in tt_late]

    def make_envelope_path(top_pts, bot_pts):
        pts_forward = " ".join(f"{p[0]:.1f},{p[1]:.1f}" for p in top_pts)
        pts_reverse = " ".join(f"{p[0]:.1f},{p[1]:.1f}" for p in reversed(bot_pts))
        return f"{pts_forward} {pts_reverse}"

    poly_env_heen = make_envelope_path(env_heen_top, env_heen_bot)
    poly_env_terug = make_envelope_path(env_terug_top, env_terug_bot)

    # 4. Compute Isochrones on 10-Minute Resolution (Parametrizable)
    iso_step_min = 10
    isochrones = []
    for m in range(-40, 141, iso_step_min):
        hh = 10 + (m // 60)
        mm = m % 60
        t_label = f"{hh:02d}:{mm:02d}"

        pts_h = []
        for s_m, t_r in zip(s_heen_ref, t_heen_ref):
            py = y_ref + (m - t_r) * scale_t
            px = s_to_x_heen(s_m)
            if y_spine_top - 3 <= py <= y_spine_bottom + 3:
                pts_h.append((px, py))

        pts_t = []
        for s_m, t_r in zip(s_terug_ref, t_terug_ref):
            py = y_ref + (m - t_r) * scale_t
            px = s_to_x_terug(s_m)
            if y_spine_top - 3 <= py <= y_spine_bottom + 3:
                pts_t.append((px, py))

        py_turn = y_ref + (m - t_heen_ref[-1]) * scale_t
        has_turn_bridge = (len(pts_h) > 0 and len(pts_t) > 0 and
                           y_spine_top <= py_turn <= y_spine_bottom)

        if len(pts_h) >= 2 or len(pts_t) >= 2:
            isochrones.append({
                "time": t_label,
                "t_min": m,
                "pts_h": pts_h,
                "pts_t": pts_t,
                "py_turn": py_turn if has_turn_bridge else None,
                "has_turn_bridge": has_turn_bridge
            })

    # 5. Current Profile Bars on Spines (Tied to 10-min isochrones, no green dots)
    scale_v = 40.0  # px per 1.0 m/s
    spine_data = []
    for j, cp in enumerate(checkpoints):
        cx = cp["x"]
        t_nom = nom_times_min[j]
        bars = []
        for m in range(-40, 141, iso_step_min):
            py = y_ref + (m - t_nom) * scale_t
            if y_spine_top <= py <= y_spine_bottom:
                u_raw = get_triangle_current(m)
                is_out = cp["leg"] in ["out", "out_turn"]
                u_fwd = u_raw if is_out else -u_raw
                is_nominal = abs(py - y_ref) < 3.0
                bars.append({
                    "clock_min": m,
                    "py": py,
                    "u_fwd": u_fwd,
                    "u_raw": u_raw,
                    "is_nominal": is_nominal,
                    "is_out": is_out
                })
        spine_data.append({"checkpoint": cp, "bars": bars, "t_nom": t_nom})

    # Save to YAML data contract
    data_to_plot = {
        "title": "CSCM KUSTZWEM-TRAJECTPROFIEL v5",
        "route": "Bredene Post 4 ➔ Vosseslag ➔ Bredene Post 4 (6.0 km Heen-en-Terug)",
        "start_time": "10:00 CEST",
        "geometry": {
            "format": "DIN A3/A4 Landscape (ratio 1.414)",
            "width": width,
            "height": height,
            "matrix_height": matrix_height,
            "vertical_scale_px_per_min": round(scale_t, 2)
        },
        "isochrone_resolution_min": iso_step_min,
        "departure_window_min": 30,
        "checkpoints": checkpoints,
        "nominal_schedule": [
            {"km": cp["label"], "name": cp["name"], "time": t_str}
            for cp, t_str in zip(checkpoints, nom_times_str)
        ],
        "leg_breakdown": legs_ref,
        "speeds_analyzed": [
            {
                "speed_mps": iso["speed"],
                "color": iso["color"],
                "eta_finish": iso["eta_finish"],
                "delta_min": iso["delta_str"],
                "total_time_min": round(iso["t_fin_min"], 1)
            }
            for iso in isotach_data
        ]
    }

    with open(OUTPUT_YAML, "w", encoding="utf-8") as f:
        yaml.dump(data_to_plot, f, sort_keys=False, indent=2)
    print(f"Saved data contract to {OUTPUT_YAML}")

    # Build SVG
    svg = []
    svg.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="100%" height="100%" style="background-color: #ffffff; font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, Helvetica, Arial, sans-serif;">')
    svg.append('  <defs>')
    svg.append('    <filter id="softShadow" x="-10%" y="-10%" width="120%" height="120%">')
    svg.append('      <feDropShadow dx="0" dy="2" stdDeviation="3" flood-opacity="0.08"/>')
    svg.append('    </filter>')
    svg.append('    <filter id="badgeShadow" x="-15%" y="-15%" width="130%" height="130%">')
    svg.append('      <feDropShadow dx="0" dy="2.5" stdDeviation="3.5" flood-opacity="0.14"/>')
    svg.append('    </filter>')
    # Subtle hatch pattern for return leg
    svg.append('    <pattern id="diagonalHatch" width="8" height="8" patternTransform="rotate(45 0 0)" patternUnits="userSpaceOnUse">')
    svg.append('      <line x1="0" y1="0" x2="0" y2="8" stroke="#94a3b8" stroke-width="1.0" opacity="0.45"/>')
    svg.append('    </pattern>')
    svg.append('  </defs>')

    # 1. Backgrounds
    svg.append(f'  <!-- Canvas Background -->')
    svg.append(f'  <rect x="0" y="0" width="{width}" height="{height}" fill="#ffffff"/>')

    # Return Leg Background (x_mid_turn to 1385)
    svg.append(f'  <!-- Return Leg Tinted Background (Zwemrichting West / FR) -->')
    svg.append(f'  <rect x="{x_mid_turn}" y="80" width="{1385 - x_mid_turn}" height="760" rx="10" fill="#f8fafc" stroke="#e2e8f0" stroke-width="1.2"/>')
    svg.append(f'  <rect x="{x_mid_turn}" y="80" width="{1385 - x_mid_turn}" height="760" rx="10" fill="url(#diagonalHatch)" opacity="0.22"/>')

    # 2. Header
    svg.append('  <!-- ================= HEADER ================= -->')
    svg.append('  <g id="header" transform="translate(0, 32)">')
    svg.append(f'    <text x="{width/2}" y="0" font-size="24" font-weight="900" fill="#0f172a" text-anchor="middle">Traject: Bredene Post 4 ➔ Vosseslag ➔ Bredene Post 4 (6.0 km)</text>')
    svg.append(f'    <text x="{width/2}" y="24" font-size="12.5" font-weight="600" fill="#64748b" text-anchor="middle">Start om 10:00 CEST • Tijd-Ruimte Diagram met Snelheidswaaier, Isochronen &amp; Stroom-Ontbinding</text>')
    svg.append('  </g>')

    # 3. Perspective Banners (Above the matrix)
    svg.append('  <!-- ================= PERSPECTIVE BANNERS ================= -->')
    w_out = (x_mid_turn - 12) - 60
    svg.append(f'  <g id="banner_out" transform="translate(60, 80)">')
    svg.append(f'    <rect x="0" y="0" width="{w_out}" height="32" rx="6" fill="#f0f9ff" stroke="#bae6fd" stroke-width="1.2"/>')
    svg.append('    <text x="14" y="21" font-size="11.5" font-weight="800" fill="#0369a1">--&gt; ZWEMRICHTING OOST [NL]</text>')
    svg.append(f'    <text x="{w_out - 14}" y="21" font-size="11" font-weight="800" fill="#0284c7" text-anchor="end">RECHTS = MEESTROOM (VLOED --&gt;)</text>')
    svg.append('  </g>')

    w_ret = 1385 - (x_mid_turn + 12)
    svg.append(f'  <g id="banner_ret" transform="translate({x_mid_turn + 12}, 80)">')
    svg.append(f'    <rect x="0" y="0" width="{w_ret}" height="32" rx="6" fill="#f1f5f9" stroke="#cbd5e1" stroke-width="1.2"/>')
    svg.append('    <text x="14" y="21" font-size="11.5" font-weight="800" fill="#334155">&lt;-- ZWEMRICHTING WEST [FR]</text>')
    svg.append(f'    <text x="{w_ret - 14}" y="21" font-size="11" font-weight="800" fill="#4338ca" text-anchor="end">RECHTS = MEESTROOM (EB --&gt;)</text>')
    svg.append('  </g>')

    # 4. Turnaround Corridor Milestone ("Niemandsland" between x_coords[4] and x_coords[5])
    svg.append('  <!-- ================= TURNAROUND BUFFER ("NIEMANDSLAND") ================= -->')
    svg.append(f'  <line x1="{x_mid_turn}" y1="120" x2="{x_mid_turn}" y2="{y_spine_bottom + 15}" stroke="#ef4444" stroke-width="1.8" stroke-dasharray="4,4" opacity="0.6"/>')

    # Compact Turnaround Badge positioned cleanly at top of buffer (y = 126 to 210)
    svg.append(f'  <g transform="translate({x_mid_turn}, 168)">')
    svg.append('    <rect x="-16" y="-42" width="32" height="84" rx="16" fill="#ef4444" filter="url(#badgeShadow)"/>')
    svg.append('    <text x="0" y="-24" font-size="14" font-weight="900" fill="#ffffff" text-anchor="middle">↺</text>')
    svg.append('    <text x="0" y="-10" font-size="9" font-weight="900" fill="#ffffff" text-anchor="middle">180°</text>')
    svg.append('    <text x="0" y="4" font-size="8" font-weight="900" fill="#ffffff" text-anchor="middle">KEER</text>')
    svg.append('    <text x="0" y="16" font-size="8" font-weight="900" fill="#ffffff" text-anchor="middle">PUNT</text>')
    svg.append('    <text x="0" y="32" font-size="7.5" font-weight="800" fill="#fecaca" text-anchor="middle">3.00k</text>')
    svg.append('  </g>')

    # 5. Checkpoint Axis Headers (Horizontal above each spine)
    svg.append('  <!-- ================= CHECKPOINT HEADERS ================= -->')
    for cp_i, cp in enumerate(checkpoints):
        cx = cp["x"]
        is_turn = cp["leg"] in ["out_turn", "ret_turn"]
        lbl_color = "#ef4444" if is_turn else "#0f172a"
        t_nom = nom_times_str[cp_i]

        svg.append(f'  <g transform="translate({cx}, 145)">')
        # Distance (horizontal, bold monospace)
        svg.append(f'    <text x="0" y="0" font-family="monospace" font-size="12" font-weight="900" fill="{lbl_color}" text-anchor="middle">{cp["km_tot"]}</text>')
        # ETA timestamp (horizontal)
        svg.append(f'    <text x="0" y="16" font-family="monospace" font-size="10" font-weight="700" fill="#64748b" text-anchor="middle">{t_nom}</text>')
        # True landmarks only (Bredene P4 & Vosseslag) pointing cleanly away from the central badge
        if cp_i == 0:
            svg.append('    <text x="0" y="-16" font-size="9.5" font-weight="800" fill="#0284c7" text-anchor="middle">Bredene P4 (Start)</text>')
        elif cp_i == 4:
            svg.append('    <text x="-6" y="-16" font-size="9" font-weight="800" fill="#ef4444" text-anchor="end">Vosseslag (Aankomst)</text>')
        elif cp_i == 5:
            svg.append('    <text x="6" y="-16" font-size="9" font-weight="800" fill="#ef4444" text-anchor="start">Vosseslag (Vertrek)</text>')
        elif cp_i == 9:
            svg.append('    <text x="0" y="-16" font-size="9.5" font-weight="800" fill="#0284c7" text-anchor="middle">Bredene P4 (Finish)</text>')
        svg.append('  </g>')

    # 6. Starttijd-Venster: Soft Green Envelope Band (±30 min margin)
    svg.append('  <!-- ================= STARTTIJD-VENSTER (±30 MIN ENVELOPE BAND) ================= -->')
    svg.append(f'  <polygon points="{poly_env_heen}" fill="#10b981" fill-opacity="0.08" stroke="#10b981" stroke-width="0.8" stroke-dasharray="3,3" opacity="0.6"/>')
    svg.append(f'  <polygon points="{poly_env_terug}" fill="#10b981" fill-opacity="0.08" stroke="#10b981" stroke-width="0.8" stroke-dasharray="3,3" opacity="0.6"/>')

    # 7. Function to build SVG polyline from points
    def poly_to_path(pts):
        if not pts:
            return ""
        return "M " + " L ".join(f"{p[0]:.1f} {p[1]:.1f}" for p in pts)

    # 8. Draw Isochrones (10-Minute Resolution, Constant Clock Time)
    svg.append('  <!-- ================= ISOCHRONES (10-MIN RESOLUTION) ================= -->')
    for iso in isochrones:
        # Heenweg segment
        if len(iso["pts_h"]) >= 2:
            ph = poly_to_path(iso["pts_h"])
            svg.append(f'    <path d="{ph}" fill="none" stroke="#94a3b8" stroke-width="0.9" stroke-dasharray="4,4" opacity="0.75"/>')

        # Terugweg segment
        if len(iso["pts_t"]) >= 2:
            pt = poly_to_path(iso["pts_t"])
            svg.append(f'    <path d="{pt}" fill="none" stroke="#94a3b8" stroke-width="0.9" stroke-dasharray="4,4" opacity="0.75"/>')

        # Horizontal connector across turnaround buffer
        if iso["has_turn_bridge"]:
            y_br = iso["py_turn"]
            svg.append(f'    <line x1="{x_heen[4]}" y1="{y_br:.1f}" x2="{x_terug[0]}" y2="{y_br:.1f}" stroke="#94a3b8" stroke-width="1.2" stroke-dasharray="2,2"/>')
            # Clock label centered in buffer
            svg.append(f'    <text x="{x_mid_turn}" y="{y_br - 4:.1f}" font-family="monospace" font-size="9" font-weight="800" fill="#475569" text-anchor="middle" paint-order="stroke" stroke="#ffffff" stroke-width="2.5">{iso["time"]}</text>')

        # Labels entering midway along bottom border: placed just above the line, rotated to follow slope
        # Heenweg entering isochrone:
        if len(iso["pts_h"]) > 1 and iso["pts_h"][0][1] >= y_spine_bottom - 5:
            p0 = iso["pts_h"][0]
            p1 = iso["pts_h"][min(5, len(iso["pts_h"])-1)]
            angle = float(np.degrees(np.arctan2(p1[1] - p0[1], p1[0] - p0[0])))
            svg.append(f'    <text x="{p0[0] + 12:.1f}" y="{p0[1] - 4:.1f}" font-family="monospace" font-size="8.5" font-weight="800" fill="#64748b" transform="rotate({angle:.1f} {p0[0]+12:.1f} {p0[1]-4:.1f})" paint-order="stroke" stroke="#ffffff" stroke-width="3">{iso["time"]}</text>')

        # Terugweg entering isochrone:
        if len(iso["pts_t"]) > 1 and iso["pts_t"][0][1] >= y_spine_bottom - 5:
            p0 = iso["pts_t"][0]
            p1 = iso["pts_t"][min(5, len(iso["pts_t"])-1)]
            angle = float(np.degrees(np.arctan2(p1[1] - p0[1], p1[0] - p0[0])))
            svg.append(f'    <text x="{p0[0] + 12:.1f}" y="{p0[1] - 4:.1f}" font-family="monospace" font-size="8.5" font-weight="800" fill="#64748b" transform="rotate({angle:.1f} {p0[0]+12:.1f} {p0[1]-4:.1f})" paint-order="stroke" stroke="#ffffff" stroke-width="3">{iso["time"]}</text>')

    # 9. Draw Vertical Spines & Tidal Current Staven (Physical Vloed-blauw / Eb-paars)
    svg.append('  <!-- ================= VERTICAL SPINES & CURRENT STAVEN ================= -->')
    for j, s_info in enumerate(spine_data):
        cp = s_info["checkpoint"]
        cx = cp["x"]
        is_turn = cp["leg"] in ["out_turn", "ret_turn"]
        spine_col = "#ef4444" if is_turn else "#94a3b8"

        # Vertical spine
        svg.append(f'    <line x1="{cx}" y1="{y_spine_top}" x2="{cx}" y2="{y_spine_bottom}" stroke="{spine_col}" stroke-width="{1.8 if is_turn else 1.2}"/>')

        # Current Staven
        for b in s_info["bars"]:
            by = b["py"]
            u_fwd = b["u_fwd"]
            u_raw = b["u_raw"]
            bar_len = abs(u_fwd) * scale_v

            bar_h = 7.0
            y_bar = by - bar_h / 2.0

            # Color represents physical tide: Flood is BLUE (#0284c7), Ebb is PURPLE (#4338ca)
            is_flood = (u_raw >= 0)
            base_col = "#0284c7" if is_flood else "#4338ca"

            stroke_attr = ' stroke="#0f172a" stroke-width="1.2"' if b["is_nominal"] else ""

            if u_fwd >= 0:
                # Meestroom (Right)
                x_b = cx
            else:
                # Tegenstroom (Left)
                x_b = cx - bar_len

            if bar_len > 0.5:
                w_b = max(1.0, bar_len)
                svg.append(f'    <rect x="{x_b:.1f}" y="{y_bar:.1f}" width="{w_b:.1f}" height="{bar_h}" rx="1.5" fill="{base_col}" opacity="0.9"{stroke_attr}/>')
                if not b["is_out"]:
                    # Return leg receives diagonal hatch
                    svg.append(f'    <rect x="{x_b:.1f}" y="{y_bar:.1f}" width="{w_b:.1f}" height="{bar_h}" rx="1.5" fill="url(#diagonalHatch)"/>')

            # Small spine tick
            svg.append(f'    <line x1="{cx - 2}" y1="{by:.1f}" x2="{cx + 2}" y2="{by:.1f}" stroke="#64748b" stroke-width="1"/>')

    # 10. Draw 9 Isotachs (0.6 to 1.4 m/s) on Fine Grid (Decoupled at Turnaround)
    svg.append('  <!-- ================= 9 ISOTACHS (CONTINUOUS SPEED FAN) ================= -->')
    for iso in isotach_data:
        ph = poly_to_path(iso["pts_heen"])
        pt = poly_to_path(iso["pts_terug"])

        svg.append(f'    <path d="{ph}" fill="none" stroke="{iso["color"]}" stroke-width="{iso["lw"]}" stroke-linecap="round" opacity="{iso["opacity"]}"/>')
        svg.append(f'    <path d="{pt}" fill="none" stroke="{iso["color"]}" stroke-width="{iso["lw"]}" stroke-linecap="round" opacity="{iso["opacity"]}"/>')

    # Finish Table on Right Margin (Cleanly formatted into two columns, placed cleanly above curves)
    svg.append('  <!-- ================= FINISH TABLE (v vs Delta t) ================= -->')
    x_tbl_v = x_terug[-1] + 32.0   # 1252.0
    x_tbl_dt = x_tbl_v + 58.0      # 1310.0
    y_tbl_head = 315.0

    svg.append(f'  <g id="finish_table">')
    svg.append(f'    <text x="{x_tbl_v}" y="{y_tbl_head:.1f}" font-size="10.5" font-weight="900" fill="#0f172a">v (m/s)</text>')
    svg.append(f'    <text x="{x_tbl_dt}" y="{y_tbl_head:.1f}" font-size="10.5" font-weight="900" fill="#0f172a">Δt (min)</text>')
    svg.append(f'    <line x1="{x_tbl_v - 5}" y1="{y_tbl_head + 5:.1f}" x2="{x_tbl_dt + 45}" y2="{y_tbl_head + 5:.1f}" stroke="#cbd5e1" stroke-width="1.0"/>')

    for iso in isotach_data:
        last_pt = iso["pts_terug"][-1]
        py_row = last_pt[1]
        col = iso["color"]
        weight = "900" if iso["speed"] == 1.0 else "700"

        # Speed column
        svg.append(f'    <text x="{x_tbl_v + 12}" y="{py_row + 3.5:.1f}" font-family="monospace" font-size="10" font-weight="{weight}" fill="{col}" text-anchor="middle">{iso["speed"]:.1f}</text>')
        # Delta time column
        svg.append(f'    <text x="{x_tbl_dt + 20}" y="{py_row + 3.5:.1f}" font-family="monospace" font-size="10" font-weight="{weight}" fill="{col}" text-anchor="middle">{iso["delta_str"]}</text>')
    svg.append('  </g>')

    # 11. 8 Schalingsbalken (All 8 below plot, ribbon layout)
    svg.append('  <!-- ================= 8 SCHALINGSBALKEN (BOTTOM RIBBON) ================= -->')
    y_ribbon = 765.0
    w_box = 115.0
    h_box = 48.0
    w_track = 100.0
    scale_bar = w_track / 750.0

    for k, leg_info in enumerate(legs_ref):
        if k < 4:
            x_l = x_heen[k]
            x_r = x_heen[k + 1]
            bg_col = "#ffffff"
        else:
            x_l = x_terug[k - 4]
            x_r = x_terug[k - 3]
            bg_col = "#f1f5f9"

        # Center card horizontally within column
        x_b = x_l + ((x_r - x_l) - w_box) / 2.0
        x_mid_leg = (x_l + x_r) / 2.0

        # Subtle leader line down from matrix
        svg.append(f'    <line x1="{x_mid_leg}" y1="{y_spine_bottom}" x2="{x_mid_leg}" y2="{y_ribbon}" stroke="#cbd5e1" stroke-width="0.9" stroke-dasharray="2,2"/>')

        # Card Container
        svg.append(f'    <g transform="translate({x_b:.1f}, {y_ribbon:.1f})">')
        svg.append(f'      <rect x="0" y="0" width="{w_box}" height="{h_box}" rx="6" fill="{bg_col}" stroke="#cbd5e1" stroke-width="1.0" filter="url(#softShadow)"/>')

        d_w = leg_info["dist_swimmer_m"]
        d_u = leg_info["dist_current_m"]
        u_avg = leg_info["u_avg_mps"]
        dt_min = leg_info["dt_min"]
        is_flood = leg_info["is_flood"]

        # Track base
        x_trk = (w_box - w_track) / 2.0
        y_trk = 7.0
        h_trk = 11.0
        svg.append(f'      <rect x="{x_trk:.1f}" y="{y_trk}" width="{w_track}" height="{h_trk}" rx="2" fill="#e2e8f0"/>')

        # Current color: Flood is BLUE (#0284c7), Ebb is PURPLE (#4338ca)
        cur_col = "#0284c7" if is_flood else "#4338ca"

        if d_u >= 0:
            # Tailwind (Meestroom): Swimmer covers Dw < 750m, current bridges to 750m
            w_w = d_w * scale_bar
            w_u = d_u * scale_bar
            svg.append(f'      <rect x="{x_trk:.1f}" y="{y_trk}" width="{w_w:.1f}" height="{h_trk}" rx="2" fill="#16a34a"/>')
            svg.append(f'      <rect x="{x_trk + w_w:.1f}" y="{y_trk}" width="{w_u:.1f}" height="{h_trk}" rx="2" fill="{cur_col}"/>')
            if k >= 4:
                svg.append(f'      <rect x="{x_trk + w_w:.1f}" y="{y_trk}" width="{w_u:.1f}" height="{h_trk}" rx="2" fill="url(#diagonalHatch)"/>')
            cur_str = f"+{int(round(d_u))}m"
        else:
            # Headwind (Tegenstroom, Leg 5): Swimmer covers Dw > 750m, current subtracts back to 750m tick!
            w_w = min(108.0, d_w * scale_bar)
            w_u = max(6.0, abs(d_u) * scale_bar)
            svg.append(f'      <rect x="{x_trk:.1f}" y="{y_trk}" width="{w_w:.1f}" height="{h_trk}" rx="2" fill="#16a34a"/>')
            # Opposing current bar pushing back from w_w to 100px
            x_opp = max(x_trk, x_trk + w_w - w_u)
            svg.append(f'      <rect x="{x_opp:.1f}" y="{y_trk}" width="{w_u:.1f}" height="{h_trk}" rx="2" fill="{cur_col}"/>')
            if k >= 4:
                svg.append(f'      <rect x="{x_opp:.1f}" y="{y_trk}" width="{w_u:.1f}" height="{h_trk}" rx="2" fill="url(#diagonalHatch)"/>')
            cur_str = f"{int(round(d_u))}m"

        # Explicit black tick mark at EXACT 750m (target distance)
        x_tick = x_trk + w_track
        svg.append(f'      <line x1="{x_tick:.1f}" y1="{y_trk - 2}" x2="{x_tick:.1f}" y2="{y_trk + h_trk + 2}" stroke="#0f172a" stroke-width="1.8"/>')

        # Numerical label row 1: distance breakdown
        svg.append(f'      <text x="{w_box/2:.1f}" y="29" font-family="monospace" font-size="8.5" font-weight="800" text-anchor="middle"><tspan fill="#16a34a">{int(round(d_w))}m</tspan> <tspan fill="{cur_col}">{cur_str}</tspan></text>')
        # Numerical label row 2: current speed & leg time
        svg.append(f'      <text x="{w_box/2:.1f}" y="40" font-family="monospace" font-size="8" font-weight="700" fill="#64748b" text-anchor="middle">u = {u_avg:+.2f} m/s • {dt_min:.1f}\'</text>')
        svg.append('    </g>')

    # 12. Single-Line Compact Legend (Underneath Schalingsbalken)
    svg.append('  <!-- ================= COMPACT SINGLE-LINE LEGEND ================= -->')
    y_leg = 845.0
    w_leg = 1260.0
    x_leg = (width - w_leg) / 2.0

    svg.append(f'  <g id="bottom_legend" transform="translate({x_leg:.1f}, {y_leg})">')
    svg.append(f'    <rect x="0" y="0" width="{w_leg}" height="42" rx="8" fill="#f8fafc" stroke="#cbd5e1" stroke-width="1.2" filter="url(#softShadow)"/>')

    # Item 1: Snelheid (9-color vector strip)
    svg.append('    <g transform="translate(20, 15)">')
    svg.append('      <text x="0" y="10" font-size="11" font-weight="900" fill="#0f172a">Snelheid:</text>')
    x_strip = 62.0
    for sp_i, sp in enumerate(speeds):
        svg.append(f'      <rect x="{x_strip + sp_i*9}" y="2" width="9" height="10" fill="{colors[sp]}"/>')
    svg.append(f'      <text x="{x_strip + 90}" y="10" font-size="10" font-weight="700" fill="#ea580c">0.6</text>')
    svg.append(f'      <text x="{x_strip + 112}" y="10" font-size="10" font-weight="900" fill="#16a34a">1.0 [Nom]</text>')
    svg.append(f'      <text x="{x_strip + 172}" y="10" font-size="10" font-weight="700" fill="#2563eb">1.4 m/s</text>')
    svg.append('    </g>')

    # Item 2: Starttijd-venster
    svg.append('    <g transform="translate(350, 15)">')
    svg.append('      <rect x="0" y="2" width="18" height="10" rx="2" fill="#10b981" fill-opacity="0.15" stroke="#10b981" stroke-width="0.9" stroke-dasharray="2,2"/>')
    svg.append('      <text x="26" y="10" font-size="10.5" font-weight="800" fill="#0f172a">Starttijd-venster: <tspan font-weight="600" fill="#64748b">±30 min vertrekmarge</tspan></text>')
    svg.append('    </g>')

    # Item 3: Getijdestroming
    svg.append('    <g transform="translate(670, 15)">')
    svg.append('      <rect x="0" y="2" width="12" height="10" rx="2" fill="#0284c7"/>')
    svg.append('      <text x="18" y="10" font-size="10.5" font-weight="800" fill="#0284c7">Vloed</text>')
    svg.append('      <rect x="68" y="2" width="12" height="10" rx="2" fill="#4338ca"/>')
    svg.append('      <text x="86" y="10" font-size="10.5" font-weight="800" fill="#4338ca">Eb</text>')
    svg.append('      <rect x="115" y="2" width="14" height="10" rx="2" fill="#4338ca"/>')
    svg.append('      <rect x="115" y="2" width="14" height="10" rx="2" fill="url(#diagonalHatch)"/>')
    svg.append('      <text x="135" y="10" font-size="10.5" font-weight="800" fill="#64748b">Terugweg (gearceerd)</text>')
    svg.append('    </g>')

    # Item 4: Isochronen
    svg.append('    <g transform="translate(1005, 15)">')
    svg.append('      <line x1="0" y1="7" x2="24" y2="7" stroke="#94a3b8" stroke-width="1.2" stroke-dasharray="3,3"/>')
    svg.append('      <text x="32" y="10" font-size="10.5" font-weight="800" fill="#0f172a">Isochronen: <tspan font-weight="600" fill="#64748b">Lijnen gelijke tijd (10\')</tspan></text>')
    svg.append('    </g>')
    svg.append('  </g>')

    # 13. Clean Footer
    svg.append('  <!-- ================= FOOTER ================= -->')
    svg.append(f'  <g id="footer" transform="translate(80, {height - 35})">')
    svg.append('    <text x="0" y="0" font-size="11" font-weight="600" fill="#94a3b8">CSCM • Dynamisch Kustzwem-Trajectmodel • Discrete Kinematica (25m Grid) &amp; Driehoeks-Getij</text>')
    svg.append(f'    <text x="{w_leg}" y="0" font-size="11" font-weight="800" fill="#94a3b8" text-anchor="end">ONTWERP v5 (A3 LIGGEND)</text>')
    svg.append('  </g>')

    svg.append('</svg>')

    rendered = "\n".join(svg)
    with open(OUTPUT_SVG, "w", encoding="utf-8") as f:
        f.write(rendered)
    print(f"Generated {OUTPUT_SVG}")

    try:
        subprocess.run(["rsvg-convert", "-w", "2000", str(OUTPUT_SVG), "-o", str(OUTPUT_PNG)], check=True)
        print(f"Generated {OUTPUT_PNG}")
    except Exception as e:
        print(f"Error converting to PNG: {e}")


if __name__ == "__main__":
    generate_profile()
