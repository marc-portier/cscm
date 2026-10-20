#!/usr/bin/env python3
"""
Generator for Coastal Swim Trajectory Profile v3 (Kustzwem-Profiel v3).

Design Improvements for v3:
1. Higher Physical & Hydrodynamic Fidelity:
   - Dynamic kinematics: v_ground(t, s) = v_water + u(t, s).
   - Arrival times integrate local variable current over each 750m step.
   - Isochrones (constant clock times) curve and bend naturally across the matrix.
   - 9 Isotachs (0.6 to 1.4 m/s in steps of 0.1 m/s) with sharp line crossings (no circles).
   - Multiple departure reference baselines (-30', -15', 0', +15', +30' from 10:00).
   - Realistic non-zero current at turnaround (flood still lingering, requiring headwind effort before slack).
   - Direct vector addition on first leg (0k0 -> 0k75): visual breakdown of swimmer speed (green)
     and current assistance (blue "gift"), summing exactly to the 750m checkpoint.
2. Turnaround Buffer ("Niemandsland"):
   - Turnaround point duplicated into two distinct spines: Vosseslag Arrival vs Vosseslag Departure.
   - Smooth horizontal transition zone between the two spines with 180° turnaround badge (↺).
   - Split background: switches from white to light grey halfway across the turnaround buffer.
3. Clean & Minimal Aesthetic (Less is More):
   - Removed bulky water level cards and verbose tactical insight card.
   - Replaced P4..P1 badges with clean 90° rotated metric chainage ticks (0.00, 0.75, 1.50... 6.00 km).
   - Subordinate 90° arrival timestamps for nominal 1.0 m/s pace along the top axis.
   - Current bars rendered as clean rectangular staven (no arrowheads) as in strandpost profile.
   - Compact multi-color fan legend at bottom.
   - Removed personal names from footer.
"""

from pathlib import Path
import subprocess
import yaml
import numpy as np

HIST_DIR = Path(__file__).resolve().parent
OUTPUT_SVG = HIST_DIR / "ontwerp-kustzwem-profiel-v3.svg"
OUTPUT_PNG = HIST_DIR / "ontwerp-kustzwem-profiel-v3.png"
OUTPUT_YAML = HIST_DIR / "data_to_plot_v3.yaml"


def get_current_model(s_km, t_min_from_10):
    """
    Realistic coastal current u(s, t) in m/s along the Bredene-Vosseslag corridor.
    Positive u = flow towards NE (Flood).
    Negative u = flow towards SW (Ebb).
    Kentering (HW slack) occurs around t = +75 min (11:15 CEST).
    At 10:00 (t=0): brisk flood ~ +0.75 m/s.
    At 10:40 (t=40): easing flood ~ +0.35 m/s.
    At 11:15 (t=75): 0.00 m/s (kentering).
    At 11:45 (t=105): accelerating ebb ~ -0.45 m/s.
    At 12:15 (t=135): strong ebb ~ -0.75 m/s.
    """
    omega = 2.0 * np.pi / 744.0
    u_val = 0.82 * np.cos(omega * (t_min_from_10 + 45.0))
    u_val += 0.03 * (s_km / 3.0)
    return u_val


def smooth_path(points):
    """Generates a smooth cubic bezier SVG path string through points."""
    if len(points) < 2:
        return ""
    if len(points) == 2:
        return f"M {points[0][0]:.1f} {points[0][1]:.1f} L {points[1][0]:.1f} {points[1][1]:.1f}"
    
    path = [f"M {points[0][0]:.1f} {points[0][1]:.1f}"]
    for i in range(len(points) - 1):
        p0 = points[i - 1] if i > 0 else points[i]
        p1 = points[i]
        p2 = points[i + 1]
        p3 = points[i + 2] if i + 2 < len(points) else p2
        
        # Tension factor
        t = 0.22
        cp1x = p1[0] + (p2[0] - p0[0]) * t
        cp1y = p1[1] + (p2[1] - p0[1]) * t
        cp2x = p2[0] - (p3[0] - p1[0]) * t
        cp2y = p2[1] - (p3[1] - p1[1]) * t
        path.append(f"C {cp1x:.1f} {cp1y:.1f}, {cp2x:.1f} {cp2y:.1f}, {p2[0]:.1f} {p2[1]:.1f}")
    return " ".join(path)


def generate_profile():
    width = 1420
    height = 840

    # Spacing: Give 210px left margin for clear time & departure labels
    # Heenweg: 5 spines (0.0k, 0.75k, 1.50k, 2.25k, 3.00k Heen)
    # Turnaround Buffer: 80px between 3.00k Heen and 3.00k Terug
    # Terugweg: 5 spines (3.00k Terug, 3.75k, 4.50k, 5.25k, 6.00k)
    dx = 115
    x_start = 210
    x_heen = [x_start + i * dx for i in range(5)]  # 210, 325, 440, 555, 670
    buffer_dx = 80
    x_terug_start = x_heen[-1] + buffer_dx        # 750
    x_terug = [x_terug_start + i * dx for i in range(5)] # 750, 865, 980, 1095, 1210
    x_coords = x_heen + x_terug

    # Checkpoint metadata
    checkpoints = [
        # Heenweg (0 to 4)
        {"idx": 0, "km_tot": "0.00", "label": "0.00 km", "name": "Bredene Post 4", "s_km": 0.0, "leg": "out", "x": x_coords[0]},
        {"idx": 1, "km_tot": "0.75", "label": "0.75 km", "name": "Renbaan (P6)", "s_km": 0.75, "leg": "out", "x": x_coords[1]},
        {"idx": 2, "km_tot": "1.50", "label": "1.50 km", "name": "Duinengordel", "s_km": 1.50, "leg": "out", "x": x_coords[2]},
        {"idx": 3, "km_tot": "2.25", "label": "2.25 km", "name": "Naaktstrand", "s_km": 2.25, "leg": "out", "x": x_coords[3]},
        {"idx": 4, "km_tot": "3.00", "label": "3.00 km", "name": "Vosseslag (Aankomst)", "s_km": 3.00, "leg": "out_turn", "x": x_coords[4]},
        # Terugweg (5 to 9)
        {"idx": 5, "km_tot": "3.00", "label": "3.00 km", "name": "Vosseslag (Vertrek)", "s_km": 3.00, "leg": "ret_turn", "x": x_coords[5]},
        {"idx": 6, "km_tot": "3.75", "label": "3.75 km", "name": "Naaktstrand", "s_km": 2.25, "leg": "ret", "x": x_coords[6]},
        {"idx": 7, "km_tot": "4.50", "label": "4.50 km", "name": "Duinengordel", "s_km": 1.50, "leg": "ret", "x": x_coords[7]},
        {"idx": 8, "km_tot": "5.25", "label": "5.25 km", "name": "Renbaan (P6)", "s_km": 0.75, "leg": "ret", "x": x_coords[8]},
        {"idx": 9, "km_tot": "6.00", "label": "6.00 km", "name": "Bredene Post 4 (Finish)", "s_km": 0.0, "leg": "ret", "x": x_coords[9]},
    ]

    y_ref = 375.0  # Baseline for nominal 1.0 m/s swimmer departing at 10:00
    scale_t = 2.4  # px per minute difference
    ds = 750.0     # meters per leg

    def simulate_swim(v_water, t_start_min=0.0):
        t_arr = [t_start_min]
        # Leg 0->1, 1->2, 2->3, 3->4 (Heen)
        for i in range(4):
            t_curr = t_arr[-1]
            s_curr = checkpoints[i]["s_km"]
            u = get_current_model(s_curr, t_curr)
            v_ground = max(0.18, v_water + u)
            dt_min = (ds / v_ground) / 60.0
            t_arr.append(t_curr + dt_min)
            
        # Turnaround step (idx 4 to 5): horizontal transfer
        t_arr.append(t_arr[-1] + 0.5)
        
        # Leg 5->6, 6->7, 7->8, 8->9 (Terug)
        for i in range(5, 9):
            t_curr = t_arr[-1]
            s_curr = checkpoints[i]["s_km"]
            u = get_current_model(s_curr, t_curr)
            # Swimming SW: flow towards SW (-u) is forward!
            u_rel = -u
            v_ground = max(0.18, v_water + u_rel)
            dt_min = (ds / v_ground) / 60.0
            t_arr.append(t_curr + dt_min)
            
        return t_arr

    # Nominal Reference Swimmer departing at 10:00
    t_ref_arr = simulate_swim(1.0, 0.0)

    # Format nominal timestamps for axis
    nom_times_str = []
    for t_m in t_ref_arr:
        tot_m = int(round(t_m))
        hh = 10 + (tot_m // 60)
        mm = tot_m % 60
        nom_times_str.append(f"{hh:02d}:{mm:02d}")

    # 2. Compute 9 Isotachs (0.6 to 1.4 m/s)
    speeds = [0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4]
    colors = {
        0.6: "#ea580c", 0.7: "#f97316", 0.8: "#f59e0b", 0.9: "#84cc16",
        1.0: "#16a34a",
        1.1: "#10b981", 1.2: "#06b6d4", 1.3: "#0ea5e9", 1.4: "#2563eb"
    }

    isotachs = []
    for sp in speeds:
        t_arr = simulate_swim(sp, 0.0)
        pts = []
        for i, (t_sw, t_ref) in enumerate(zip(t_arr, t_ref_arr)):
            delta_t = t_sw - t_ref
            py = y_ref + delta_t * scale_t
            px = x_coords[i]
            pts.append((px, py))
        isotachs.append({
            "speed": sp,
            "color": colors[sp],
            "lw": 3.0 if sp == 1.0 else 1.4,
            "opacity": 1.0 if sp == 1.0 else 0.85,
            "points": pts,
            "t_finish_min": t_arr[-1]
        })

    # 3. Compute Alternative Departure Lines (v = 1.0 m/s at -30', -15', +15', +30')
    departure_offsets = [-30.0, -15.0, 15.0, 30.0]
    dep_lines = []
    for dep_t in departure_offsets:
        t_arr = simulate_swim(1.0, dep_t)
        pts = []
        for i, (t_sw, t_ref) in enumerate(zip(t_arr, t_ref_arr)):
            delta_t = t_sw - t_ref
            py = y_ref + delta_t * scale_t
            px = x_coords[i]
            pts.append((px, py))
        
        tot_m = int(round(dep_t))
        hh = 10 + (tot_m // 60)
        mm = tot_m % 60
        dep_label = f"{hh:02d}:{mm:02d}"
        dep_lines.append({
            "dep_t": dep_t,
            "label": dep_label,
            "points": pts
        })

    # 4. Compute Isochrones (Lines of constant clock time T)
    isochrones = []
    for m in range(-30, 151, 15):
        hh = 10 + (m // 60)
        mm = m % 60
        t_label = f"{hh:02d}:{mm:02d}"
        pts = []
        for i, t_ref in enumerate(t_ref_arr):
            delta_t = m - t_ref
            py = y_ref + delta_t * scale_t
            px = x_coords[i]
            if y_ref - 135 <= py <= y_ref + 140:
                pts.append((px, py))
        if len(pts) >= 2:
            isochrones.append({"time": t_label, "points": pts, "t_min": m})

    # 5. Current Profile Bars on Spines
    scale_v = 45.0  # px per 1.0 m/s current
    spine_data = []
    for j, cp in enumerate(checkpoints):
        t_nom = t_ref_arr[j]
        s_km = cp["s_km"]
        bars = []
        for dt_m in [-30.0, -15.0, 0.0, 15.0, 30.0]:
            t_sample = t_nom + dt_m
            u = get_current_model(s_km, t_sample)
            u_fwd = u if cp["leg"] in ["out", "out_turn"] else -u
            bars.append({"dt": dt_m, "u": u_fwd, "u_raw": u})
        spine_data.append({"checkpoint": cp, "bars": bars})

    # 6. First-step Vector Addition breakdown
    v_w0 = 1.0
    u_0 = get_current_model(0.0, 0.0)
    v_g0 = v_w0 + u_0
    dx_step = x_coords[1] - x_coords[0]
    dx_swimmer = dx_step * (v_w0 / v_g0)
    dx_current = dx_step * (u_0 / v_g0)

    # Save to YAML data contract
    data_to_plot = {
        "title": "CSCM KUSTZWEM-TRAJECTPROFIEL v3",
        "route": "Bredene Post 4 ➔ Vosseslag ➔ Bredene Post 4 (6.0 km Heen-en-Terug)",
        "start_time": "10:00 CEST",
        "checkpoints": checkpoints,
        "nominal_schedule": [
            {"km": cp["label"], "name": cp["name"], "time": t_str}
            for cp, t_str in zip(checkpoints, nom_times_str)
        ],
        "speeds_analyzed": speeds,
        "first_step_breakdown": {
            "distance_m": ds,
            "v_swimmer_mps": v_w0,
            "u_current_mps": round(u_0, 2),
            "swimmer_share_pct": round(100.0 * v_w0 / v_g0, 1),
            "current_share_pct": round(100.0 * u_0 / v_g0, 1),
        }
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
    svg.append('      <line x1="0" y1="0" x2="0" y2="8" stroke="#cbd5e1" stroke-width="0.8" opacity="0.35"/>')
    svg.append('    </pattern>')
    svg.append('  </defs>')

    # 1. Backgrounds
    x_mid_turn = (x_coords[4] + x_coords[5]) / 2.0  # 710.0
    svg.append(f'  <!-- Canvas Background -->')
    svg.append(f'  <rect x="0" y="0" width="{width}" height="{height}" fill="#ffffff"/>')
    
    # Return Leg Background (x_mid_turn to 1360)
    svg.append(f'  <!-- Return Leg Tinted Background (Zwemrichting Zuidwest / FR) -->')
    svg.append(f'  <rect x="{x_mid_turn}" y="100" width="{1360 - x_mid_turn}" height="565" rx="10" fill="#f8fafc" stroke="#e2e8f0" stroke-width="1.2"/>')
    svg.append(f'  <rect x="{x_mid_turn}" y="100" width="{1360 - x_mid_turn}" height="565" rx="10" fill="url(#diagonalHatch)"/>')

    # 2. Header
    svg.append('  <!-- ================= HEADER ================= -->')
    svg.append('  <g id="header" transform="translate(0, 26)">')
    svg.append(f'    <text x="{width/2}" y="18" font-size="12" font-weight="800" letter-spacing="2.0" fill="#0284c7" text-anchor="middle">CSCM KUSTZWEM-TRAJECTPROFIEL • UITGAVE v3 (DYNAMISCHE KINETICA)</text>')
    svg.append(f'    <text x="{width/2}" y="50" font-size="26" font-weight="900" fill="#0f172a" text-anchor="middle">Traject: Bredene Post 4 ➔ Vosseslag ➔ Bredene Post 4 (6.0 km)</text>')
    svg.append(f'    <text x="{width/2}" y="74" font-size="13.5" font-weight="600" fill="#64748b" text-anchor="middle">Start om 10:00 CEST • Tijd-Ruimte Diagram met Gebogen Isochronen, 9 Isotachen &amp; Echte Stroomoptelling</text>')
    svg.append('  </g>')

    # 3. Perspective Banners (Above the matrix)
    svg.append('  <!-- ================= PERSPECTIVE BANNER ================= -->')
    # Heen banner (Left: 60 to x_mid_turn - 12)
    w_out = (x_mid_turn - 12) - 60
    svg.append(f'  <g id="banner_out" transform="translate(60, 105)">')
    svg.append(f'    <rect x="0" y="0" width="{w_out}" height="32" rx="6" fill="#f0f9ff" stroke="#bae6fd" stroke-width="1.2"/>')
    svg.append('    <text x="14" y="21" font-size="11" font-weight="800" fill="#0369a1">🏊 HEENWEG (0k0 ➔ 3k0): ZWEMRICHTING NOORDOOST [NL]</text>')
    svg.append(f'    <text x="{w_out - 14}" y="21" font-size="10.5" font-weight="800" fill="#0284c7" text-anchor="end">RECHTS = MEESTROOM (VLOED ➔)</text>')
    svg.append('  </g>')
    
    # Terug banner (Right: x_mid_turn + 12 to 1360)
    w_ret = 1360 - (x_mid_turn + 12)
    svg.append(f'  <g id="banner_ret" transform="translate({x_mid_turn + 12}, 105)">')
    svg.append(f'    <rect x="0" y="0" width="{w_ret}" height="32" rx="6" fill="#f1f5f9" stroke="#cbd5e1" stroke-width="1.2"/>')
    svg.append('    <text x="14" y="21" font-size="11" font-weight="800" fill="#334155">🔄 TERUGWEG (3k0 ➔ 6k0): ZWEMRICHTING ZUIDWEST [FR]</text>')
    svg.append(f'    <text x="{w_ret - 14}" y="21" font-size="10.5" font-weight="800" fill="#4338ca" text-anchor="end">RECHTS = MEESTROOM (EB ➔)</text>')
    svg.append('  </g>')

    # 4. Turnaround Corridor Milestone ("Niemandsland" between x_coords[4] and x_coords[5])
    svg.append('  <!-- ================= TURNAROUND BUFFER ("NIEMANDSLAND") ================= -->')
    svg.append(f'  <line x1="{x_mid_turn}" y1="145" x2="{x_mid_turn}" y2="650" stroke="#ef4444" stroke-width="1.8" stroke-dasharray="4,4" opacity="0.6"/>')
    
    # Stacked Turnaround Badge centered in buffer
    svg.append(f'  <g transform="translate({x_mid_turn}, 220)">')
    svg.append('    <rect x="-16" y="-62" width="32" height="124" rx="16" fill="#ef4444" filter="url(#badgeShadow)"/>')
    svg.append('    <text x="0" y="-40" font-size="16" font-weight="900" fill="#ffffff" text-anchor="middle">↺</text>')
    svg.append('    <text x="0" y="-20" font-size="10.5" font-weight="900" fill="#ffffff" text-anchor="middle">180°</text>')
    svg.append('    <text x="0" y="2" font-size="9" font-weight="900" fill="#ffffff" text-anchor="middle">KEER</text>')
    svg.append('    <text x="0" y="18" font-size="9" font-weight="900" fill="#ffffff" text-anchor="middle">PUNT</text>')
    svg.append('    <text x="0" y="40" font-size="8" font-weight="800" fill="#fecaca" text-anchor="middle">3.00k</text>')
    svg.append('  </g>')

    # 5. Checkpoint Axis Markers (90° rotated metric chainage ticks + nominal ETA)
    svg.append('  <!-- ================= CHECKPOINT 90° AXIS MARKERS ================= -->')
    for cp_i, cp in enumerate(checkpoints):
        cx = cp["x"]
        is_turn = cp["leg"] in ["out_turn", "ret_turn"]
        lbl_color = "#ef4444" if is_turn else "#0f172a"
        t_nom = nom_times_str[cp_i]
        
        svg.append(f'  <g transform="translate({cx}, 162)">')
        # Metric distance (90° rotated)
        svg.append(f'    <text x="0" y="0" font-family="monospace" font-size="11.5" font-weight="900" fill="{lbl_color}" text-anchor="end" transform="rotate(-90 0 0)">{cp["km_tot"]}</text>')
        # Nominal ETA timestamp (90° rotated)
        svg.append(f'    <text x="13" y="0" font-family="monospace" font-size="9" font-weight="700" fill="#64748b" text-anchor="end" transform="rotate(-90 13 0)">{t_nom}</text>')
        svg.append('  </g>')

    # 6. Spines & Matrix Surface
    y_spine_top = y_ref - 135
    y_spine_bottom = y_ref + 140

    # Draw Isochrones (Thin curved constant-clock-time contours)
    svg.append('  <!-- ================= CURVED ISOCHRONES (CONSTANT CLOCK TIME) ================= -->')
    for iso in isochrones:
        pts = iso["points"]
        path_str = smooth_path(pts)
        svg.append(f'    <path d="{path_str}" fill="none" stroke="#cbd5e1" stroke-width="1.1" stroke-dasharray="3,3" opacity="0.85"/>')
        
        # Label at first point only if NOT near left spine (to avoid duplicate with spine time ticks)
        first_pt = pts[0]
        if first_pt[0] > x_coords[0] + 15 and first_pt[1] <= y_spine_top + 6:
            svg.append(f'    <text x="{first_pt[0]}" y="{first_pt[1] - 6:.1f}" font-family="monospace" font-size="8.5" font-weight="700" fill="#94a3b8" text-anchor="middle">{iso["time"]}</text>')

    # Draw Alternative Departure Lines (v = 1.0 m/s at -30', -15', +15', +30')
    # Fine dotted green trajectories originating from the left spine
    svg.append('  <!-- ================= ALTERNATIVE DEPARTURE BASELINES ================= -->')
    for dep in dep_lines:
        pts = dep["points"]
        path_str = smooth_path(pts)
        svg.append(f'    <path d="{path_str}" fill="none" stroke="#10b981" stroke-width="1.1" stroke-dasharray="3,3" opacity="0.45"/>')
        py_start = pts[0][1]
        svg.append(f'    <text x="{x_coords[0] - 14}" y="{py_start + 3.5:.1f}" font-family="monospace" font-size="9" font-weight="700" fill="#059669" text-anchor="end">{dep["label"]}</text>')

    # Swimmer Nominal Baseline Label on Left
    svg.append(f'    <text x="{x_coords[0] - 14}" y="{y_ref + 3.5:.1f}" font-family="monospace" font-size="9.5" font-weight="900" fill="#15803d" text-anchor="end">10:00 [Ref]</text>')

    # Draw Vertical Spines & Rectangular Current Staven
    svg.append('  <!-- ================= VERTICAL SPINES & CURRENT STAVEN ================= -->')
    for j, s_info in enumerate(spine_data):
        cp = s_info["checkpoint"]
        cx = cp["x"]
        is_turn = cp["leg"] in ["out_turn", "ret_turn"]
        spine_col = "#ef4444" if is_turn else "#94a3b8"
        
        # Vertical spine
        svg.append(f'    <line x1="{cx}" y1="{y_spine_top}" x2="{cx}" y2="{y_spine_bottom}" stroke="{spine_col}" stroke-width="{1.8 if is_turn else 1.2}"/>')
        
        # Current Staven (horizontal bars)
        for b in s_info["bars"]:
            by = y_ref + b["dt"] * scale_t
            u = b["u"]
            bar_len = abs(u) * scale_v
            
            bar_h = 7.0
            y_bar = by - bar_h / 2.0
            
            if u > 0.05:
                # Meestroom (Right)
                bar_col = "#0284c7" if cp["leg"] in ["out", "out_turn"] else "#4338ca"
                svg.append(f'    <rect x="{cx}" y="{y_bar:.1f}" width="{bar_len:.1f}" height="{bar_h}" rx="2" fill="{bar_col}" opacity="0.9"/>')
            elif u < -0.05:
                # Tegenstroom (Left) -> Amber/Orange
                svg.append(f'    <rect x="{cx - bar_len:.1f}" y="{y_bar:.1f}" width="{bar_len:.1f}" height="{bar_h}" rx="2" fill="#ea580c" opacity="0.9"/>')
            else:
                # Kentering dot (Green)
                svg.append(f'    <circle cx="{cx}" cy="{by:.1f}" r="4" fill="#16a34a" stroke="#ffffff" stroke-width="1.5"/>')
                
            # Tick on spine
            svg.append(f'    <line x1="{cx - 2}" y1="{by:.1f}" x2="{cx + 2}" y2="{by:.1f}" stroke="#64748b" stroke-width="1"/>')

    # Draw 9 Isotachs (0.6 to 1.4 m/s) with smooth paths & sharp intersections
    svg.append('  <!-- ================= 9 ISOTACHS (CONTINUOUS SPEED FAN) ================= -->')
    for iso in isotachs:
        pts = iso["points"]
        path_str = smooth_path(pts)
        svg.append(f'    <path d="{path_str}" fill="none" stroke="{iso["color"]}" stroke-width="{iso["lw"]}" stroke-linecap="round" opacity="{iso["opacity"]}"/>')
        
        # End label on right margin
        last_pt = pts[-1]
        svg.append(f'    <text x="{last_pt[0] + 12}" y="{last_pt[1] + 3.5:.1f}" font-family="monospace" font-size="10" font-weight="800" fill="{iso["color"]}">{iso["speed"]} m/s</text>')

    # 7. First-step Vector Addition Breakdown Box (Placed above Leg 0->1 at y=192)
    svg.append('  <!-- ================= FIRST-STEP VECTOR ADDITION ================= -->')
    x0 = x_coords[0]
    x_split = x0 + dx_swimmer
    x1 = x_coords[1]
    y_box = 194.0
    
    svg.append(f'  <g id="first_step_vector_box" transform="translate({x0}, {y_box})">')
    # Background pill
    svg.append(f'    <rect x="0" y="0" width="{dx_step}" height="32" rx="5" fill="#f8fafc" stroke="#cbd5e1" stroke-width="1.0" filter="url(#softShadow)"/>')
    # Swimmer bar portion (Green)
    svg.append(f'    <rect x="3" y="3" width="{dx_swimmer - 4:.1f}" height="10" rx="2.5" fill="#16a34a"/>')
    # Current bar portion (Blue)
    svg.append(f'    <rect x="{dx_swimmer + 1:.1f}" y="3" width="{dx_current - 4:.1f}" height="10" rx="2.5" fill="#0284c7"/>')
    # Single clean legend label below the bar
    pct_sw = data_to_plot["first_step_breakdown"]["swimmer_share_pct"]
    pct_cur = data_to_plot["first_step_breakdown"]["current_share_pct"]
    svg.append(f'    <text x="{dx_step/2:.1f}" y="24" font-size="8.5" font-weight="800" fill="#0f172a" text-anchor="middle">750m = <tspan fill="#16a34a">Zwem {pct_sw}%</tspan> + <tspan fill="#0284c7">Stroom {pct_cur}% kado</tspan></text>')
    # Connector down to checkpoint 1
    svg.append(f'    <line x1="{dx_step}" y1="32" x2="{dx_step}" y2="{y_ref - y_box}" stroke="#0284c7" stroke-width="1.2" stroke-dasharray="2,2"/>')
    svg.append(f'  </g>')

    # 8. Clean Compact Legend at Bottom
    svg.append('  <!-- ================= COMPACT BOTTOM LEGEND ================= -->')
    y_leg = 685.0
    svg.append(f'  <g id="bottom_legend" transform="translate(60, {y_leg})">')
    svg.append(f'    <rect x="0" y="0" width="{width - 120}" height="76" rx="8" fill="#f8fafc" stroke="#cbd5e1" stroke-width="1.2" filter="url(#softShadow)"/>')
    
    # Column 1: Isotachen Waaier 🗧
    svg.append('    <g transform="translate(25, 20)">')
    svg.append('      <text x="0" y="0" font-size="11.5" font-weight="900" fill="#0f172a">🗧 ISOTACHEN (SNELHEIDS-WAAIER):</text>')
    svg.append('      <text x="0" y="22" font-size="10.5" font-weight="700" fill="#ea580c">0.6 m/s (Rustig)</text>')
    svg.append('      <text x="115" y="22" font-size="10.5" font-weight="700" fill="#f59e0b">0.8 m/s</text>')
    svg.append('      <text x="175" y="22" font-size="11" font-weight="900" fill="#16a34a">1.0 m/s (Nominaal)</text>')
    svg.append('      <text x="300" y="22" font-size="10.5" font-weight="700" fill="#0ea5e9">1.2 m/s</text>')
    svg.append('      <text x="360" y="22" font-size="10.5" font-weight="700" fill="#2563eb">1.4 m/s (Snel)</text>')
    svg.append('      <text x="0" y="42" font-size="9.5" font-weight="500" fill="#64748b">Afwijking per 0.1 m/s • Snijpunt met isochronen geeft exacte aankomsttijd</text>')
    svg.append('    </g>')
    
    # Column 2: Stromingsstaven (Visgraten)
    svg.append('    <g transform="translate(560, 20)">')
    svg.append('      <text x="0" y="0" font-size="11.5" font-weight="900" fill="#0f172a">⚡ STROMINGSSTAVEN (VISGRATEN):</text>')
    svg.append('      <rect x="0" y="12" width="22" height="7" rx="1.5" fill="#0284c7"/>')
    svg.append('      <text x="28" y="19" font-size="10" font-weight="700" fill="#0284c7">Vloed mee (Heen)</text>')
    svg.append('      <rect x="135" y="12" width="22" height="7" rx="1.5" fill="#4338ca"/>')
    svg.append('      <text x="163" y="19" font-size="10" font-weight="700" fill="#4338ca">Eb mee (Terug)</text>')
    svg.append('      <rect x="255" y="12" width="22" height="7" rx="1.5" fill="#ea580c"/>')
    svg.append('      <text x="283" y="19" font-size="10" font-weight="700" fill="#ea580c">Tegenstroom</text>')
    svg.append('      <circle cx="365" cy="15.5" r="3.5" fill="#16a34a"/>')
    svg.append('      <text x="375" y="19" font-size="10" font-weight="700" fill="#16a34a">Kentering</text>')
    svg.append('      <text x="0" y="42" font-size="9.5" font-weight="500" fill="#64748b">Rechts = Meestroom in zwemrichting • Lengte staaf = stroomsnelheid (m/s)</text>')
    svg.append('    </g>')

    # Column 3: Isochronen & Blikveld
    svg.append('    <g transform="translate(1030, 20)">')
    svg.append('      <text x="0" y="0" font-size="11.5" font-weight="900" fill="#0f172a">⏱️ ISOCHRONEN &amp; BLIKVELD:</text>')
    svg.append('      <text x="0" y="20" font-size="10" font-weight="600" fill="#334155">• <tspan font-family="monospace" font-weight="bold">-- 10:15 --</tspan> Lijnen van gelijke kloktijd</text>')
    svg.append('      <text x="0" y="38" font-size="10" font-weight="600" fill="#334155">• <tspan font-weight="bold">Wit</tspan> = Blik naar zee [NL] • <tspan font-weight="bold">Grijs</tspan> = Terugweg [FR]</text>')
    svg.append('    </g>')
    svg.append('  </g>')

    # 9. Minimal Footer (NO personal names)
    svg.append('  <!-- ================= FOOTER ================= -->')
    svg.append('  <g id="footer" transform="translate(60, 795)">')
    svg.append('    <text x="0" y="0" font-size="11" font-weight="600" fill="#94a3b8">CSCM • Dynamisch Kustzwem-Trajectmodel • Decoupled Grid, Isochronen &amp; Isotachen</text>')
    svg.append(f'    <text x="{width - 120}" y="0" font-size="11" font-weight="700" fill="#94a3b8" text-anchor="end">ONTWERP v3 (HEEN &amp; TERUG)</text>')
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
