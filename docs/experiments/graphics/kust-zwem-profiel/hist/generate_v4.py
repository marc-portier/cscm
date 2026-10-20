#!/usr/bin/env python3
"""
Generator for Coastal Swim Trajectory Profile v4 (Kustzwem-Profiel v4).

Design Improvements for v4 (incorporating Marc's handwritten feedback):
1. Discrete Kinematics Engine on Fine Grid (ds = 25m):
   - Replaced global cubic Bézier spline with numerical integration:
     dt = ds / (v_swimmer + u_rel(t)) on a 25m spatial grid.
   - 100% faithful to physics: no spline oscillations, no unnatural pinching.
   - Correctly reproduces explosive non-linear time penalty for slower swimmers against current.
2. Predictable Synthetic Tidal Current Model:
   - Piecewise linear triangle profile with fixed step Delta u = 0.20 m/s per 15 minutes.
   - Symmetrical oscillation between +0.60 m/s (peak flood) and -0.60 m/s (peak ebb).
   - Kentering (slack, u = 0.00 m/s) occurs at 10:45 CEST (t = +45 min).
   - Allows exact mental and manual verification of all vectors and time shifts.
3. Turnaround Decoupling ("Niemandsland"):
   - Outbound leg (0k0 -> 3k0) and return leg (3k0 -> 6k0) strictly decoupled.
   - Isotachs terminate at Vosseslag Inbound spine and restart at Vosseslag Outbound spine.
   - Isochrones bridged across the turnaround buffer with strictly horizontal lines and clock labels.
4. 8 Alternating Schalingsbalken (Vector Breakdown Cards):
   - Vector addition displayed for every 750m segment (8 in total).
   - Alternating placement: odd legs (1, 3, 5, 7) at top; even legs (2, 4, 6, 8) at bottom.
   - Displays exact meters through water (swimmer) vs meters pushed/pulled by current, plus m/s.
   - Headwind/tegenstroom legs (Leg 5) show swimmer bar exceeding 750m with current subtracted.
   - Water current remains blue; return leg receives subtle diagonal grey hatching.
5. Coherent Vertical Spines & Isochrone Time Alignment:
   - Current staven on spines placed at exact clock time isochrone intersections.
   - Displays vertical time shift directly on the spine (7-8 minutes later arrival at 750m).
   - Every isochrone entering from bottom/left is clearly labeled with HH:MM timestamp.
"""

from pathlib import Path
import subprocess
import yaml
import numpy as np

HIST_DIR = Path(__file__).resolve().parent
OUTPUT_SVG = HIST_DIR / "ontwerp-kustzwem-profiel-v4.svg"
OUTPUT_PNG = HIST_DIR / "ontwerp-kustzwem-profiel-v4.png"
OUTPUT_YAML = HIST_DIR / "data_to_plot_v4.yaml"


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

    # Heenweg: 4 legs of 750m (0 to 3000m), swimming NE
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
            "is_tailwind": dist_u >= 0
        })

    # Instant transfer across turnaround buffer
    t_turn_dep = t_curr

    # Terugweg: 4 legs of 750m (3000 to 6000m), swimming SW
    traj_terug = [(3000.0, t_turn_dep)]
    for leg in range(4):
        t_leg_start = t_curr
        for step in range(n_steps_leg):
            u = get_triangle_current(t_curr)
            u_rel = -u  # Swimming SW: ebb (-u) is tailwind!
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
            "is_tailwind": dist_u >= 0
        })

    return traj_heen, traj_terug, leg_stats


def generate_profile():
    width = 1460
    height = 790

    # Layout Spacing
    dx = 115
    x_start = 225
    x_heen = [x_start + i * dx for i in range(5)]           # 225, 340, 455, 570, 685
    buffer_dx = 80
    x_terug_start = x_heen[-1] + buffer_dx                 # 765
    x_terug = [x_terug_start + i * dx for i in range(5)]  # 765, 880, 995, 1110, 1225
    x_mid_turn = (x_heen[-1] + x_terug[0]) / 2.0           # 725.0
    x_coords = x_heen + x_terug

    # Checkpoint Metadata
    checkpoints = [
        {"idx": 0, "km_tot": "0.00", "label": "0.00 km", "name": "Bredene Post 4", "s_km": 0.0, "leg": "out", "x": x_coords[0]},
        {"idx": 1, "km_tot": "0.75", "label": "0.75 km", "name": "Renbaan (P6)", "s_km": 0.75, "leg": "out", "x": x_coords[1]},
        {"idx": 2, "km_tot": "1.50", "label": "1.50 km", "name": "Duinengordel", "s_km": 1.50, "leg": "out", "x": x_coords[2]},
        {"idx": 3, "km_tot": "2.25", "label": "2.25 km", "name": "Naaktstrand", "s_km": 2.25, "leg": "out", "x": x_coords[3]},
        {"idx": 4, "km_tot": "3.00", "label": "3.00 km", "name": "Vosseslag (Aankomst)", "s_km": 3.00, "leg": "out_turn", "x": x_coords[4]},
        {"idx": 5, "km_tot": "3.00", "label": "3.00 km", "name": "Vosseslag (Vertrek)", "s_km": 3.00, "leg": "ret_turn", "x": x_coords[5]},
        {"idx": 6, "km_tot": "3.75", "label": "3.75 km", "name": "Naaktstrand", "s_km": 2.25, "leg": "ret", "x": x_coords[6]},
        {"idx": 7, "km_tot": "4.50", "label": "4.50 km", "name": "Duinengordel", "s_km": 1.50, "leg": "ret", "x": x_coords[7]},
        {"idx": 8, "km_tot": "5.25", "label": "5.25 km", "name": "Renbaan (P6)", "s_km": 0.75, "leg": "ret", "x": x_coords[8]},
        {"idx": 9, "km_tot": "6.00", "label": "6.00 km", "name": "Bredene Post 4 (Finish)", "s_km": 0.0, "leg": "ret", "x": x_coords[9]},
    ]

    # Baseline geometry
    y_ref = 390.0
    scale_t = 2.4   # px per minute difference
    y_spine_top = y_ref - 145.0     # 245.0
    y_spine_bottom = y_ref + 145.0  # 535.0

    # 1. Simulate Reference Swimmer (1.0 m/s departing at 10:00)
    traj_heen_ref, traj_terug_ref, legs_ref = simulate_swim(1.0, 0.0, ds=25.0)

    # Reference timeline interpolators
    s_heen_ref = np.array([pt[0] for pt in traj_heen_ref])
    t_heen_ref = np.array([pt[1] for pt in traj_heen_ref])
    s_terug_ref = np.array([pt[0] for pt in traj_terug_ref])
    t_terug_ref = np.array([pt[1] for pt in traj_terug_ref])

    def get_t_ref(s_m):
        if s_m <= 3000.0:
            return float(np.interp(s_m, s_heen_ref, t_heen_ref))
        else:
            return float(np.interp(s_m, s_terug_ref, t_terug_ref))

    def s_to_x(s_m):
        if s_m <= 3000.0:
            return x_heen[0] + (s_m / 3000.0) * (x_heen[4] - x_heen[0])
        else:
            return x_terug[0] + ((s_m - 3000.0) / 3000.0) * (x_terug[4] - x_terug[0])

    # Checkpoint nominal ETA
    nom_times_str = []
    nom_times_min = []
    for cp in checkpoints:
        s_val = cp["s_km"] * 1000.0
        if cp["leg"] in ["ret", "ret_turn"]:
            s_val = (6.0 - cp["s_km"]) * 1000.0
        t_m = get_t_ref(s_val)
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

    isotach_data = []
    for sp in speeds:
        th, tt, _ = simulate_swim(sp, 0.0, ds=25.0)

        pts_heen = []
        for s_m, t_val in th:
            t_r = get_t_ref(s_m)
            py = y_ref + (t_val - t_r) * scale_t
            px = s_to_x(s_m)
            pts_heen.append((px, py))

        pts_terug = []
        for s_m, t_val in tt:
            t_r = get_t_ref(s_m)
            py = y_ref + (t_val - t_r) * scale_t
            px = s_to_x(s_m)
            pts_terug.append((px, py))

        t_fin = tt[-1][1]
        tot_m = int(round(t_fin))
        hh = 10 + (tot_m // 60)
        mm = tot_m % 60

        isotach_data.append({
            "speed": sp,
            "color": colors[sp],
            "lw": 3.0 if sp == 1.0 else 1.4,
            "opacity": 1.0 if sp == 1.0 else 0.85,
            "pts_heen": pts_heen,
            "pts_terug": pts_terug,
            "t_fin_min": t_fin,
            "eta_finish": f"{hh:02d}:{mm:02d}"
        })

    # 3. Compute Alternative Departure Lines (v = 1.0 m/s at -30', -15', +15', +30')
    departure_offsets = [-30.0, -15.0, 15.0, 30.0]
    dep_lines = []
    for dep_t in departure_offsets:
        th, tt, _ = simulate_swim(1.0, dep_t, ds=25.0)

        pts_heen = []
        for s_m, t_val in th:
            t_r = get_t_ref(s_m)
            py = y_ref + (t_val - t_r) * scale_t
            px = s_to_x(s_m)
            pts_heen.append((px, py))

        pts_terug = []
        for s_m, t_val in tt:
            t_r = get_t_ref(s_m)
            py = y_ref + (t_val - t_r) * scale_t
            px = s_to_x(s_m)
            pts_terug.append((px, py))

        tot_m = int(round(dep_t))
        hh = 10 + (tot_m // 60)
        mm = tot_m % 60
        dep_lines.append({
            "dep_t": dep_t,
            "label": f"{hh:02d}:{mm:02d}",
            "pts_heen": pts_heen,
            "pts_terug": pts_terug
        })

    # 4. Compute Isochrones (Lines of Constant Clock Time T)
    isochrones = []
    for m in range(-30, 151, 15):
        hh = 10 + (m // 60)
        mm = m % 60
        t_label = f"{hh:02d}:{mm:02d}"

        # Points on Heenweg
        pts_h = []
        for s_m, t_r in zip(s_heen_ref, t_heen_ref):
            py = y_ref + (m - t_r) * scale_t
            px = s_to_x(s_m)
            if y_spine_top - 5 <= py <= y_spine_bottom + 5:
                pts_h.append((px, py))

        # Points on Terugweg
        pts_t = []
        for s_m, t_r in zip(s_terug_ref, t_terug_ref):
            py = y_ref + (m - t_r) * scale_t
            px = s_to_x(s_m)
            if y_spine_top - 5 <= py <= y_spine_bottom + 5:
                pts_t.append((px, py))

        # Horizontal connector across turnaround buffer
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

    # 5. Current Profile Bars on Spines (Tied directly to isochrones)
    scale_v = 45.0  # px per 1.0 m/s
    spine_data = []
    for j, cp in enumerate(checkpoints):
        cx = cp["x"]
        t_nom = nom_times_min[j]
        bars = []
        for m in range(-30, 151, 15):
            py = y_ref + (m - t_nom) * scale_t
            if y_spine_top - 2 <= py <= y_spine_bottom + 2:
                u_raw = get_triangle_current(m)
                u_fwd = u_raw if cp["leg"] in ["out", "out_turn"] else -u_raw
                bars.append({
                    "clock_min": m,
                    "py": py,
                    "u_fwd": u_fwd,
                    "u_raw": u_raw
                })
        spine_data.append({"checkpoint": cp, "bars": bars, "t_nom": t_nom})

    # Save to YAML data contract
    data_to_plot = {
        "title": "CSCM KUSTZWEM-TRAJECTPROFIEL v4",
        "route": "Bredene Post 4 ➔ Vosseslag ➔ Bredene Post 4 (6.0 km Heen-en-Terug)",
        "start_time": "10:00 CEST",
        "synthetic_tidal_model": {
            "type": "Piecewise linear triangle profile",
            "period_min": 180,
            "peak_flood_mps": 0.60,
            "peak_ebb_mps": -0.60,
            "delta_per_15min_mps": 0.20,
            "kentering_cest": "10:45 CEST (t = +45 min)"
        },
        "discretization_step_m": 25.0,
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

    # Return Leg Background (x_mid_turn to 1395)
    svg.append(f'  <!-- Return Leg Tinted Background (Zwemrichting Zuidwest / FR) -->')
    svg.append(f'  <rect x="{x_mid_turn}" y="88" width="{1395 - x_mid_turn}" height="520" rx="10" fill="#f8fafc" stroke="#e2e8f0" stroke-width="1.2"/>')
    svg.append(f'  <rect x="{x_mid_turn}" y="88" width="{1395 - x_mid_turn}" height="520" rx="10" fill="url(#diagonalHatch)" opacity="0.25"/>')

    # 2. Header
    svg.append('  <!-- ================= HEADER ================= -->')
    svg.append('  <g id="header" transform="translate(0, 22)">')
    svg.append(f'    <text x="{width/2}" y="16" font-size="11.5" font-weight="800" letter-spacing="2.0" fill="#0284c7" text-anchor="middle">CSCM KUSTZWEM-TRAJECTPROFIEL • UITGAVE v4 (DISCRETE KINEMATICA &amp; 8 VECTORBALKEN)</text>')
    svg.append(f'    <text x="{width/2}" y="44" font-size="24" font-weight="900" fill="#0f172a" text-anchor="middle">Traject: Bredene Post 4 ➔ Vosseslag ➔ Bredene Post 4 (6.0 km)</text>')
    svg.append(f'    <text x="{width/2}" y="66" font-size="12.5" font-weight="600" fill="#64748b" text-anchor="middle">Start om 10:00 CEST • 25m Grid Integratie • Driehoeks-Getij (Δ0.2 m/s / 15\') • 8 Schalingsbalken • Ontkoppeld Keerpunt</text>')
    svg.append('  </g>')

    # 3. Perspective Banners (Above the matrix)
    svg.append('  <!-- ================= PERSPECTIVE BANNER ================= -->')
    w_out = (x_mid_turn - 12) - 60
    svg.append(f'  <g id="banner_out" transform="translate(60, 90)">')
    svg.append(f'    <rect x="0" y="0" width="{w_out}" height="30" rx="6" fill="#f0f9ff" stroke="#bae6fd" stroke-width="1.2"/>')
    svg.append('    <text x="14" y="20" font-size="11" font-weight="800" fill="#0369a1">🏊 HEENWEG (0k0 ➔ 3k0): ZWEMRICHTING NOORDOOST [NL]</text>')
    svg.append(f'    <text x="{w_out - 14}" y="20" font-size="10.5" font-weight="800" fill="#0284c7" text-anchor="end">RECHTS = MEESTROOM (VLOED ➔)</text>')
    svg.append('  </g>')

    w_ret = 1395 - (x_mid_turn + 12)
    svg.append(f'  <g id="banner_ret" transform="translate({x_mid_turn + 12}, 90)">')
    svg.append(f'    <rect x="0" y="0" width="{w_ret}" height="30" rx="6" fill="#f1f5f9" stroke="#cbd5e1" stroke-width="1.2"/>')
    svg.append('    <text x="14" y="20" font-size="11" font-weight="800" fill="#334155">🔄 TERUGWEG (3k0 ➔ 6k0): ZWEMRICHTING ZUIDWEST [FR]</text>')
    svg.append(f'    <text x="{w_ret - 14}" y="20" font-size="10.5" font-weight="800" fill="#4338ca" text-anchor="end">RECHTS = MEESTROOM (EB ➔)</text>')
    svg.append('  </g>')

    # 4. Turnaround Corridor Milestone ("Niemandsland" between x_coords[4] and x_coords[5])
    svg.append('  <!-- ================= TURNAROUND BUFFER ("NIEMANDSLAND") ================= -->')
    svg.append(f'  <line x1="{x_mid_turn}" y1="128" x2="{x_mid_turn}" y2="600" stroke="#ef4444" stroke-width="1.8" stroke-dasharray="4,4" opacity="0.6"/>')

    # Compact Turnaround Badge positioned cleanly at top of buffer (y = 135 to 230)
    svg.append(f'  <g transform="translate({x_mid_turn}, 182)">')
    svg.append('    <rect x="-16" y="-46" width="32" height="92" rx="16" fill="#ef4444" filter="url(#badgeShadow)"/>')
    svg.append('    <text x="0" y="-28" font-size="14" font-weight="900" fill="#ffffff" text-anchor="middle">↺</text>')
    svg.append('    <text x="0" y="-13" font-size="9.5" font-weight="900" fill="#ffffff" text-anchor="middle">180°</text>')
    svg.append('    <text x="0" y="2" font-size="8" font-weight="900" fill="#ffffff" text-anchor="middle">KEER</text>')
    svg.append('    <text x="0" y="14" font-size="8" font-weight="900" fill="#ffffff" text-anchor="middle">PUNT</text>')
    svg.append('    <text x="0" y="32" font-size="7.5" font-weight="800" fill="#fecaca" text-anchor="middle">3.00k</text>')
    svg.append('  </g>')

    # 5. Checkpoint Axis Markers (90° rotated metric chainage ticks + nominal ETA)
    svg.append('  <!-- ================= CHECKPOINT 90° AXIS MARKERS ================= -->')
    for cp_i, cp in enumerate(checkpoints):
        cx = cp["x"]
        is_turn = cp["leg"] in ["out_turn", "ret_turn"]
        lbl_color = "#ef4444" if is_turn else "#0f172a"
        t_nom = nom_times_str[cp_i]

        svg.append(f'  <g transform="translate({cx}, 190)">')
        svg.append(f'    <text x="0" y="0" font-family="monospace" font-size="11" font-weight="900" fill="{lbl_color}" text-anchor="end" transform="rotate(-90 0 0)">{cp["km_tot"]}</text>')
        svg.append(f'    <text x="12" y="0" font-family="monospace" font-size="8.5" font-weight="700" fill="#64748b" text-anchor="end" transform="rotate(-90 12 0)">{t_nom}</text>')
        svg.append('  </g>')

    # 6. Function to build SVG polyline from points
    def poly_to_path(pts):
        if not pts:
            return ""
        return "M " + " L ".join(f"{p[0]:.1f} {p[1]:.1f}" for p in pts)

    # 7. Draw Isochrones (Thin curved constant-clock-time contours)
    svg.append('  <!-- ================= CURVED ISOCHRONES (CONSTANT CLOCK TIME) ================= -->')
    for iso in isochrones:
        # Heenweg segment
        if len(iso["pts_h"]) >= 2:
            ph = poly_to_path(iso["pts_h"])
            svg.append(f'    <path d="{ph}" fill="none" stroke="#94a3b8" stroke-width="1.0" stroke-dasharray="4,4" opacity="0.75"/>')

        # Terugweg segment
        if len(iso["pts_t"]) >= 2:
            pt = poly_to_path(iso["pts_t"])
            svg.append(f'    <path d="{pt}" fill="none" stroke="#94a3b8" stroke-width="1.0" stroke-dasharray="4,4" opacity="0.75"/>')

        # Horizontal connector across turnaround buffer
        if iso["has_turn_bridge"]:
            y_br = iso["py_turn"]
            svg.append(f'    <line x1="{x_heen[4]}" y1="{y_br:.1f}" x2="{x_terug[0]}" y2="{y_br:.1f}" stroke="#94a3b8" stroke-width="1.2" stroke-dasharray="2,2"/>')
            # Clock label in buffer
            svg.append(f'    <text x="{x_mid_turn}" y="{y_br - 4:.1f}" font-family="monospace" font-size="8.5" font-weight="800" fill="#475569" text-anchor="middle">{iso["time"]}</text>')

        # Isochrone labels entering at bottom of plot:
        # (Heenweg):
        if len(iso["pts_h"]) > 0 and iso["pts_h"][0][1] >= y_spine_bottom - 5:
            x_enter = iso["pts_h"][0][0]
            if x_enter > x_heen[0] + 20:
                svg.append(f'    <text x="{x_enter}" y="{y_spine_bottom + 14:.1f}" font-family="monospace" font-size="8.5" font-weight="800" fill="#64748b" text-anchor="middle">{iso["time"]}</text>')

        # (Terugweg):
        if len(iso["pts_t"]) > 0 and iso["pts_t"][0][1] >= y_spine_bottom - 5:
            x_enter = iso["pts_t"][0][0]
            if x_enter > x_terug[0] + 20:
                svg.append(f'    <text x="{x_enter}" y="{y_spine_bottom + 14:.1f}" font-family="monospace" font-size="8.5" font-weight="800" fill="#64748b" text-anchor="middle">{iso["time"]}</text>')

    # 8. Draw Alternative Departure Baselines (v = 1.0 m/s at -30', -15', +15', +30')
    svg.append('  <!-- ================= ALTERNATIVE DEPARTURE BASELINES ================= -->')
    for dep in dep_lines:
        ph = poly_to_path(dep["pts_heen"])
        pt = poly_to_path(dep["pts_terug"])
        svg.append(f'    <path d="{ph}" fill="none" stroke="#10b981" stroke-width="1.3" stroke-dasharray="2,2" opacity="0.6"/>')
        svg.append(f'    <path d="{pt}" fill="none" stroke="#10b981" stroke-width="1.3" stroke-dasharray="2,2" opacity="0.6"/>')

    # Unified Left Departure Badges (Cleanly separated from matrix ticks)
    dep_badges = [
        {"t_min": -30.0, "label": "09:30", "type": "alt"},
        {"t_min": -15.0, "label": "09:45", "type": "alt"},
        {"t_min": 0.0,   "label": "10:00 [Ref]", "type": "ref"},
        {"t_min": 15.0,  "label": "10:15", "type": "alt"},
        {"t_min": 30.0,  "label": "10:30", "type": "alt"},
        {"t_min": 45.0,  "label": "10:45", "type": "iso_only"},
    ]
    for db in dep_badges:
        py_b = y_ref + db["t_min"] * scale_t
        if db["type"] == "ref":
            # Prominent Reference Swimmer Badge
            svg.append(f'    <g transform="translate({x_heen[0] - 8}, {py_b:.1f})">')
            svg.append(f'      <rect x="-82" y="-10" width="82" height="20" rx="4" fill="#dcfce7" stroke="#16a34a" stroke-width="1.2"/>')
            svg.append(f'      <text x="-41" y="4" font-family="monospace" font-size="9" font-weight="900" fill="#15803d" text-anchor="middle">10:00 [Ref]</text>')
            svg.append(f'    </g>')
        elif db["type"] == "alt":
            # Alternative Departure Badge
            svg.append(f'    <g transform="translate({x_heen[0] - 8}, {py_b:.1f})">')
            svg.append(f'      <rect x="-56" y="-8.5" width="56" height="17" rx="3.5" fill="#f0fdf4" stroke="#86efac" stroke-width="1.0"/>')
            svg.append(f'      <text x="-28" y="3.5" font-family="monospace" font-size="8.5" font-weight="800" fill="#166534" text-anchor="middle">{db["label"]}</text>')
            svg.append(f'    </g>')
        else:
            # Pure Isochrone Tick
            svg.append(f'    <text x="{x_heen[0] - 12}" y="{py_b + 3:.1f}" font-family="monospace" font-size="8.5" font-weight="700" fill="#94a3b8" text-anchor="end">{db["label"]}</text>')

    # 9. Draw Vertical Spines & Tidal Current Staven (Unified with Isochrones)
    svg.append('  <!-- ================= VERTICAL SPINES & CURRENT STAVEN ================= -->')
    for j, s_info in enumerate(spine_data):
        cp = s_info["checkpoint"]
        cx = cp["x"]
        is_turn = cp["leg"] in ["out_turn", "ret_turn"]
        spine_col = "#ef4444" if is_turn else "#94a3b8"

        # Vertical spine
        svg.append(f'    <line x1="{cx}" y1="{y_spine_top}" x2="{cx}" y2="{y_spine_bottom}" stroke="{spine_col}" stroke-width="{1.8 if is_turn else 1.2}"/>')

        # Current Staven (horizontal bars tied to isochrones)
        for b in s_info["bars"]:
            by = b["py"]
            u = b["u_fwd"]
            bar_len = abs(u) * scale_v

            bar_h = 7.0
            y_bar = by - bar_h / 2.0

            if u > 0.04:
                # Meestroom (Right)
                bar_col = "#0284c7" if cp["leg"] in ["out", "out_turn"] else "#4338ca"
                svg.append(f'    <rect x="{cx}" y="{y_bar:.1f}" width="{bar_len:.1f}" height="{bar_h}" rx="2" fill="{bar_col}" opacity="0.9"/>')
                if cp["leg"] in ["ret", "ret_turn"]:
                    svg.append(f'    <rect x="{cx}" y="{y_bar:.1f}" width="{bar_len:.1f}" height="{bar_h}" rx="2" fill="url(#diagonalHatch)"/>')
            elif u < -0.04:
                # Tegenstroom (Left) -> Amber/Orange
                svg.append(f'    <rect x="{cx - bar_len:.1f}" y="{y_bar:.1f}" width="{bar_len:.1f}" height="{bar_h}" rx="2" fill="#ea580c" opacity="0.9"/>')
            else:
                # Kentering dot (Green)
                svg.append(f'    <circle cx="{cx}" cy="{by:.1f}" r="4" fill="#16a34a" stroke="#ffffff" stroke-width="1.5"/>')

            # Small spine tick
            svg.append(f'    <line x1="{cx - 2}" y1="{by:.1f}" x2="{cx + 2}" y2="{by:.1f}" stroke="#64748b" stroke-width="1"/>')

    # 10. Draw 9 Isotachs (0.6 to 1.4 m/s) on Fine Grid (Separated at Turnaround!)
    svg.append('  <!-- ================= 9 ISOTACHS (CONTINUOUS SPEED FAN) ================= -->')
    for iso in isotach_data:
        ph = poly_to_path(iso["pts_heen"])
        pt = poly_to_path(iso["pts_terug"])

        svg.append(f'    <path d="{ph}" fill="none" stroke="{iso["color"]}" stroke-width="{iso["lw"]}" stroke-linecap="round" opacity="{iso["opacity"]}"/>')
        svg.append(f'    <path d="{pt}" fill="none" stroke="{iso["color"]}" stroke-width="{iso["lw"]}" stroke-linecap="round" opacity="{iso["opacity"]}"/>')

        # End label on right margin: Speed + ETA Finish!
        last_pt = iso["pts_terug"][-1]
        svg.append(f'    <text x="{last_pt[0] + 12}" y="{last_pt[1] + 3.5:.1f}" font-family="monospace" font-size="9.5" font-weight="800" fill="{iso["color"]}">{iso["speed"]} m/s ({iso["eta_finish"]})</text>')

    # 11. 8 Alternating Schalingsbalken (Vector Breakdown Boxes)
    svg.append('  <!-- ================= 8 SCHALINGSBALKEN (VECTOR BREAKDOWNS) ================= -->')
    y_box_top = 134.0
    y_box_bot = 556.0
    w_box = 105.0
    h_box = 38.0

    for k, leg_info in enumerate(legs_ref):
        is_odd = (k % 2 == 0)  # k=0,2,4,6 -> Legs 1,3,5,7 (Odd) -> TOP
        y_b = y_box_top if is_odd else y_box_bot

        if k < 4:
            x_l = x_heen[k]
            x_r = x_heen[k + 1]
        else:
            x_l = x_terug[k - 4]
            x_r = x_terug[k - 3]

        # Centered within column
        x_b = x_l + ((x_r - x_l) - w_box) / 2.0
        x_mid_leg = (x_l + x_r) / 2.0

        # Leader line to matrix
        if is_odd:
            svg.append(f'    <line x1="{x_mid_leg}" y1="{y_b + h_box}" x2="{x_mid_leg}" y2="{y_spine_top}" stroke="#cbd5e1" stroke-width="0.9" stroke-dasharray="2,2"/>')
        else:
            svg.append(f'    <line x1="{x_mid_leg}" y1="{y_spine_bottom + 18}" x2="{x_mid_leg}" y2="{y_b}" stroke="#cbd5e1" stroke-width="0.9" stroke-dasharray="2,2"/>')

        # Box card
        svg.append(f'    <g transform="translate({x_b:.1f}, {y_b:.1f})">')
        svg.append(f'      <rect x="0" y="0" width="{w_box}" height="{h_box}" rx="5" fill="#f8fafc" stroke="#cbd5e1" stroke-width="1.0" filter="url(#softShadow)"/>')

        # Vector bar representation (95px wide baseline for 750m)
        w_track = 95.0
        scale_bar = w_track / 750.0
        d_w = leg_info["dist_swimmer_m"]
        d_u = leg_info["dist_current_m"]
        u_avg = leg_info["u_avg_mps"]
        dt_min = leg_info["dt_min"]

        svg.append(f'      <rect x="5" y="4" width="{w_track}" height="10" rx="2" fill="#e2e8f0"/>')

        if d_u >= 0:
            # Tailwind / Meestroom
            w_w = d_w * scale_bar
            w_u = d_u * scale_bar
            svg.append(f'      <rect x="5" y="4" width="{w_w:.1f}" height="10" rx="2" fill="#16a34a"/>')
            svg.append(f'      <rect x="{5 + w_w:.1f}" y="4" width="{w_u:.1f}" height="10" rx="2" fill="#0284c7"/>')
            if k >= 4:
                # Hatching on return leg
                svg.append(f'      <rect x="{5 + w_w:.1f}" y="4" width="{w_u:.1f}" height="10" rx="2" fill="url(#diagonalHatch)"/>')

            cur_str = f"+{int(round(d_u))}m"
            cur_col = "#0284c7"
            cur_sym = "⊕"
        else:
            # Headwind / Tegenstroom: Swimmer covers > 750m, current subtracts!
            w_w = min(100.0, d_w * scale_bar)
            w_u = max(6.0, abs(d_u) * scale_bar)  # ensure at least 6px visible
            svg.append(f'      <rect x="5" y="4" width="{w_w:.1f}" height="10" rx="2" fill="#16a34a"/>')
            # Opposing current bar pushing back
            x_sub = max(5.0, 5.0 + w_w - w_u)
            svg.append(f'      <rect x="{x_sub:.1f}" y="4" width="{w_u:.1f}" height="10" rx="2" fill="#ea580c"/>')
            cur_str = f"{int(round(d_u))}m"
            cur_col = "#ea580c"
            cur_sym = "⊖"

        # Numerical labels inside card
        svg.append(f'      <text x="{w_box/2:.1f}" y="23" font-family="monospace" font-size="8" font-weight="800" text-anchor="middle"><tspan fill="#16a34a">🏊{int(round(d_w))}m</tspan> <tspan fill="{cur_col}">{cur_sym}{cur_str}</tspan></text>')
        svg.append(f'      <text x="{w_box/2:.1f}" y="33" font-family="monospace" font-size="7.5" font-weight="700" fill="#64748b" text-anchor="middle">u={u_avg:+.2f} m/s ({dt_min:.1f}\')</text>')
        svg.append('    </g>')

    # 12. Clean Compact Legend at Bottom
    svg.append('  <!-- ================= COMPACT BOTTOM LEGEND ================= -->')
    y_leg = 622.0
    svg.append(f'  <g id="bottom_legend" transform="translate(60, {y_leg})">')
    svg.append(f'    <rect x="0" y="0" width="{width - 120}" height="76" rx="8" fill="#f8fafc" stroke="#cbd5e1" stroke-width="1.2" filter="url(#softShadow)"/>')

    # Column 1: Isotachen Waaier
    svg.append('    <g transform="translate(25, 20)">')
    svg.append('      <text x="0" y="0" font-size="11.5" font-weight="900" fill="#0f172a">🗧 ISOTACHEN (SNELHEIDS-WAAIER 25m GRID):</text>')
    svg.append('      <text x="0" y="22" font-size="10.5" font-weight="700" fill="#ea580c">0.6 m/s (Rustig)</text>')
    svg.append('      <text x="115" y="22" font-size="10.5" font-weight="700" fill="#f59e0b">0.8 m/s</text>')
    svg.append('      <text x="175" y="22" font-size="11" font-weight="900" fill="#16a34a">1.0 m/s (Nominaal)</text>')
    svg.append('      <text x="300" y="22" font-size="10.5" font-weight="700" fill="#0ea5e9">1.2 m/s</text>')
    svg.append('      <text x="360" y="22" font-size="10.5" font-weight="700" fill="#2563eb">1.4 m/s (Snel)</text>')
    svg.append('      <text x="0" y="42" font-size="9.5" font-weight="500" fill="#64748b">Ontkoppeld bij keerpunt • Tegenstroom vergroot tijdverschil voor trage zwemmers (1/v niet-lineair)</text>')
    svg.append('    </g>')

    # Column 2: 8 Schalingsbalken & Stroming
    svg.append('    <g transform="translate(600, 20)">')
    svg.append('      <text x="0" y="0" font-size="11.5" font-weight="900" fill="#0f172a">⚡ 8 SCHALINGSBALKEN &amp; GETIJDE-VECTOREN:</text>')
    svg.append('      <rect x="0" y="12" width="22" height="7" rx="1.5" fill="#16a34a"/>')
    svg.append('      <text x="28" y="19" font-size="10" font-weight="700" fill="#16a34a">Zwemmer</text>')
    svg.append('      <rect x="95" y="12" width="22" height="7" rx="1.5" fill="#0284c7"/>')
    svg.append('      <text x="123" y="19" font-size="10" font-weight="700" fill="#0284c7">Stroom mee (Heen)</text>')
    svg.append('      <rect x="245" y="12" width="22" height="7" rx="1.5" fill="#4338ca"/>')
    svg.append('      <rect x="245" y="12" width="22" height="7" rx="1.5" fill="url(#diagonalHatch)"/>')
    svg.append('      <text x="273" y="19" font-size="10" font-weight="700" fill="#4338ca">Stroom mee (Terug)</text>')
    svg.append('      <rect x="400" y="12" width="22" height="7" rx="1.5" fill="#ea580c"/>')
    svg.append('      <text x="428" y="19" font-size="10" font-weight="700" fill="#ea580c">Tegenstroom</text>')
    svg.append('      <text x="0" y="42" font-size="9.5" font-weight="500" fill="#64748b">Balken wisselen af (oneven boven / even onder) • Driehoeksprofiel: Δ0.2 m/s per 15 min</text>')
    svg.append('    </g>')

    # Column 3: Isochronen & Keerpunt
    svg.append('    <g transform="translate(1120, 20)">')
    svg.append('      <text x="0" y="0" font-size="11.5" font-weight="900" fill="#0f172a">⏱️ ISOCHRONEN &amp; KEERPUNT:</text>')
    svg.append('      <text x="0" y="20" font-size="10" font-weight="600" fill="#334155">• <tspan font-family="monospace" font-weight="bold">-- 10:15 --</tspan> Lijnen van gelijke tijd</text>')
    svg.append('      <text x="0" y="38" font-size="10" font-weight="600" fill="#334155">• Horizontaal verbonden over buffer</text>')
    svg.append('    </g>')
    svg.append('  </g>')

    # 13. Minimal Footer
    svg.append('  <!-- ================= FOOTER ================= -->')
    svg.append('  <g id="footer" transform="translate(60, 735)">')
    svg.append('    <text x="0" y="0" font-size="10.5" font-weight="600" fill="#94a3b8">CSCM • Dynamisch Kustzwem-Trajectmodel • 25m Kinematica, 8 Schalingsbalken &amp; Driehoeks-Getij</text>')
    svg.append(f'    <text x="{width - 120}" y="0" font-size="10.5" font-weight="700" fill="#94a3b8" text-anchor="end">ONTWERP v4 (DISCRETE FYSICA)</text>')
    svg.append('  </g>')

    svg.append('</svg>')

    rendered = "\n".join(svg)
    with open(OUTPUT_SVG, "w", encoding="utf-8") as f:
        f.write(rendered)
    print(f"Generated {OUTPUT_SVG}")

    try:
        subprocess.run(["rsvg-convert", "-w", "1600", str(OUTPUT_SVG), "-o", str(OUTPUT_PNG)], check=True)
        print(f"Generated {OUTPUT_PNG}")
    except Exception as e:
        print(f"Error converting to PNG: {e}")


if __name__ == "__main__":
    generate_profile()
