#!/usr/bin/env python3
"""
Generator for Coastal Swim Trajectory Profile v2 (Kustzwem-Profiel v2).

Features:
- Out-and-back trajectory: Bredene Post 4 -> Vosseslag (3.0 km) -> Bredene Post 4 (6.0 km total).
- Visual asymmetry: Left half (Heen, swimming NE towards NL) is white.
  Right half (Terug, swimming SW towards FR) is tinted light grey (#f8fafc) with subtle hatching.
- Swimmer-centric directionality: Reading Left -> Right is ALWAYS forward swim direction!
  * On Heenweg: Flood (NE) flows Right (MEESTROOM).
  * On Terugweg: Ebb (SW) flows Right (MEESTROOM).
- Isochrones: Thin diagonal constant clock-time curves traversing the spines (10:15, 10:30, 10:45...).
- Isotachs: Swimmer velocity contour fan (0.6, 0.8, 1.0 [Ref], 1.2, 1.4 m/s).
- Landmark banner at top: Coastal landmarks, dunes, and beach posts for both legs.
- Water level badges at Start, Turnaround, and Finish.
- Tactical Swim Insight: The "Double Tailwind" timing strategy around high water kentering.
"""

from pathlib import Path
import subprocess
import yaml

HIST_DIR = Path(__file__).resolve().parent
OUTPUT_SVG = HIST_DIR / "ontwerp-kustzwem-profiel-v2.svg"
OUTPUT_PNG = HIST_DIR / "ontwerp-kustzwem-profiel-v2.png"
OUTPUT_YAML = HIST_DIR / "data_to_plot_v2.yaml"


def generate_profile():
    # Canvas geometry
    width = 1300
    height = 940

    # 9 Checkpoints across the 6.0 km out-and-back swim
    # x ranges from 170 to 1170
    x_coords = [170, 295, 420, 545, 670, 795, 920, 1045, 1170]

    checkpoints = [
        # HEENWEG (SW -> NE towards NL)
        {"idx": 0, "km_tot": "0.0k", "km_leg": "0.0k", "name": "Post 4 (Start)", "post": "P4", "x": x_coords[0], "leg": "out", "landmark": "Droogen Opganck"},
        {"idx": 1, "km_tot": "0.75k", "km_leg": "0.75k", "name": "Post 3", "post": "P3", "x": x_coords[1], "leg": "out", "landmark": "Duinengordel"},
        {"idx": 2, "km_tot": "1.50k", "km_leg": "1.50k", "name": "Post 2", "post": "P2", "x": x_coords[2], "leg": "out", "landmark": "Centrum Strand"},
        {"idx": 3, "km_tot": "2.25k", "km_leg": "2.25k", "name": "Post 1", "post": "P1", "x": x_coords[3], "leg": "out", "landmark": "Duinenreservaat"},
        {"idx": 4, "km_tot": "3.00k", "km_leg": "3.00k", "name": "Vosseslag (Keer)", "post": "VS", "x": x_coords[4], "leg": "turn", "landmark": "Strandhoofd Vosseslag"},
        # TERUGWEG (NE -> SW towards FR)
        {"idx": 5, "km_tot": "3.75k", "km_leg": "2.25k", "name": "Post 1 (Terug)", "post": "P1", "x": x_coords[5], "leg": "ret", "landmark": "Duinenreservaat"},
        {"idx": 6, "km_tot": "4.50k", "km_leg": "1.50k", "name": "Post 2 (Terug)", "post": "P2", "x": x_coords[6], "leg": "ret", "landmark": "Centrum Strand"},
        {"idx": 7, "km_tot": "5.25k", "km_leg": "0.75k", "name": "Post 3 (Terug)", "post": "P3", "x": x_coords[7], "leg": "ret", "landmark": "Duinengordel"},
        {"idx": 8, "km_tot": "6.00k", "km_leg": "0.0k", "name": "Post 4 (Finish)", "post": "P4", "x": x_coords[8], "leg": "ret", "landmark": "Droogen Opganck"},
    ]

    y_ref = 400.0  # Horizontal baseline for 1.0 m/s reference swimmer
    scale_t = 2.4  # px per minute difference

    # Reference swimmer schedule (departure at 10:00, ~12.5 min per 750m leg)
    t_ref_minutes = [0.0, 12.5, 25.0, 37.5, 50.0, 62.5, 75.0, 87.5, 100.0]

    # Velocity Contour Scenarios (Isotachs): paces from 0.6 to 1.4 m/s
    scenarios = [
        {"speed": 1.4, "label": "1.4 m/s (Snelle Atleet)", "color": "#0284c7", "factor": 1.0 / 1.4, "dash": "none", "lw": 2.2},
        {"speed": 1.2, "label": "1.2 m/s (Vlot Tempo)", "color": "#38bdf8", "factor": 1.0 / 1.2, "dash": "none", "lw": 1.8},
        {"speed": 1.0, "label": "1.0 m/s (Referentiezwemmer)", "color": "#16a34a", "factor": 1.0, "dash": "none", "lw": 3.8, "is_ref": True},
        {"speed": 0.8, "label": "0.8 m/s (Recreatief Tempo)", "color": "#f59e0b", "factor": 1.0 / 0.8, "dash": "none", "lw": 1.8},
        {"speed": 0.6, "label": "0.6 m/s (Rustige Schoolslag)", "color": "#ea580c", "factor": 1.0 / 0.6, "dash": "none", "lw": 2.2},
    ]

    for sc in scenarios:
        pts = []
        times_str = []
        for i, t_ref in enumerate(t_ref_minutes):
            t_swimmer = t_ref * sc["factor"]
            delta_t = t_swimmer - t_ref
            py = y_ref + delta_t * scale_t
            px = x_coords[i]
            pts.append((px, py))
            
            tot_m = int(round(t_swimmer))
            hh = 10 + (tot_m // 60)
            mm = tot_m % 60
            times_str.append(f"{hh:02d}:{mm:02d}")
        sc["points"] = pts
        sc["times"] = times_str

    # Isochrones: Lines of constant clock time across checkpoints
    isochrones = []
    for m in range(0, 136, 15):
        hh = 10 + (m // 60)
        mm = m % 60
        t_label = f"{hh:02d}:{mm:02d}"
        iso_pts = []
        for i, t_ref in enumerate(t_ref_minutes):
            delta_t = m - t_ref
            py = y_ref + delta_t * scale_t
            px = x_coords[i]
            if y_ref - 110 <= py <= y_ref + 115:
                iso_pts.append((px, py))
        if len(iso_pts) >= 2:
            isochrones.append({"time": t_label, "points": iso_pts})

    # Current profile on each spine
    spine_currents = [
        {"bars": [{"dt": -30, "v": 0.95}, {"dt": -15, "v": 0.90}, {"dt": 0, "v": 0.85}, {"dt": 15, "v": 0.75}, {"dt": 30, "v": 0.60}], "leg": "out"},
        {"bars": [{"dt": -30, "v": 0.88}, {"dt": -15, "v": 0.80}, {"dt": 0, "v": 0.70}, {"dt": 15, "v": 0.58}, {"dt": 30, "v": 0.42}], "leg": "out"},
        {"bars": [{"dt": -30, "v": 0.75}, {"dt": -15, "v": 0.62}, {"dt": 0, "v": 0.50}, {"dt": 15, "v": 0.35}, {"dt": 30, "v": 0.20}], "leg": "out"},
        {"bars": [{"dt": -30, "v": 0.50}, {"dt": -15, "v": 0.35}, {"dt": 0, "v": 0.20}, {"dt": 15, "v": 0.08}, {"dt": 30, "v": -0.08}], "leg": "out"},
        {"bars": [{"dt": -30, "v": 0.25}, {"dt": -15, "v": 0.10}, {"dt": 0, "v": 0.00}, {"dt": 15, "v": 0.12}, {"dt": 30, "v": 0.28}], "leg": "turn"},
        {"bars": [{"dt": -30, "v": -0.05}, {"dt": -15, "v": 0.12}, {"dt": 0, "v": 0.28}, {"dt": 15, "v": 0.45}, {"dt": 30, "v": 0.60}], "leg": "ret"},
        {"bars": [{"dt": -30, "v": 0.15}, {"dt": -15, "v": 0.35}, {"dt": 0, "v": 0.52}, {"dt": 15, "v": 0.68}, {"dt": 30, "v": 0.80}], "leg": "ret"},
        {"bars": [{"dt": -30, "v": 0.35}, {"dt": -15, "v": 0.55}, {"dt": 0, "v": 0.72}, {"dt": 15, "v": 0.85}, {"dt": 30, "v": 0.92}], "leg": "ret"},
        {"bars": [{"dt": -30, "v": 0.50}, {"dt": -15, "v": 0.70}, {"dt": 0, "v": 0.82}, {"dt": 15, "v": 0.90}, {"dt": 30, "v": 0.95}], "leg": "ret"},
    ]

    # Save to YAML data contract
    data_to_plot = {
        "title": "CSCM KUSTZWEM-TRAJECTPROFIEL v2",
        "route": "Bredene Post 4 ➔ Vosseslag ➔ Bredene Post 4 (6.0 km Heen-en-Terug)",
        "start_time": "10:00 CEST",
        "checkpoints": checkpoints,
        "scenarios": [
            {"speed": sc["speed"], "label": sc["label"], "color": sc["color"], "times": sc["times"]}
            for sc in scenarios
        ],
        "water_levels": {
            "start": {"station": "Bredene Post 4", "time": "10:00 CEST", "level_m_taw": 4.55, "phase": "Vloed / Stijgend (HW - 50m)"},
            "turn": {"station": "Vosseslag", "time": "10:50 CEST", "level_m_taw": 4.95, "phase": "Hoogwater / Kentering (HW)"},
            "finish": {"station": "Bredene Post 4", "time": "11:40 CEST", "level_m_taw": 4.58, "phase": "Eb / Vallend water (HW + 50m)"},
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
    # Subtle hatch pattern for return leg background
    svg.append('    <pattern id="diagonalHatch" width="10" height="10" patternTransform="rotate(45 0 0)" patternUnits="userSpaceOnUse">')
    svg.append('      <line x1="0" y1="0" x2="0" y2="10" stroke="#e2e8f0" stroke-width="1.0" />')
    svg.append('    </pattern>')
    # Arrow markers
    svg.append('    <marker id="arrowBlue" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">')
    svg.append('      <path d="M 0 0 L 6 3 L 0 6 z" fill="#0284c7" />')
    svg.append('    </marker>')
    svg.append('    <marker id="arrowPurple" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">')
    svg.append('      <path d="M 0 0 L 6 3 L 0 6 z" fill="#4338ca" />')
    svg.append('    </marker>')
    svg.append('    <marker id="arrowOrange" markerWidth="6" markerHeight="6" refX="1" refY="3" orient="auto">')
    svg.append('      <path d="M 6 0 L 0 3 L 6 6 z" fill="#ea580c" />')
    svg.append('    </marker>')
    svg.append('  </defs>')

    # 1. Backgrounds: Left half white, Right half (Return leg) Light Grey (#f8fafc)
    turn_x = x_coords[4]  # 670
    svg.append(f'  <!-- Canvas Background -->')
    svg.append(f'  <rect x="0" y="0" width="{width}" height="{height}" fill="#ffffff"/>')
    svg.append(f'  <!-- Return Leg Tinted Background (Right Half: x={turn_x} to 1240) -->')
    svg.append(f'  <rect x="{turn_x}" y="105" width="{1240 - turn_x}" height="600" rx="12" fill="#f8fafc" stroke="#e2e8f0" stroke-width="1.5"/>')
    svg.append(f'  <rect x="{turn_x}" y="105" width="{1240 - turn_x}" height="600" rx="12" fill="url(#diagonalHatch)" opacity="0.35"/>')

    # 2. Header
    svg.append('  <!-- ================= HEADER ================= -->')
    svg.append('  <g id="header" transform="translate(0, 28)">')
    svg.append(f'    <text x="{width/2}" y="18" font-size="12" font-weight="800" letter-spacing="2.0" fill="#0284c7" text-anchor="middle">CSCM KUSTZWEM-TRAJECTPROFIEL • UITGAVE v2 (HEEN &amp; TERUG)</text>')
    svg.append(f'    <text x="{width/2}" y="52" font-size="28" font-weight="900" fill="#0f172a" text-anchor="middle">Traject: Bredene Post 4 ➔ Vosseslag ➔ Bredene Post 4 (6.0 km)</text>')
    svg.append(f'    <text x="{width/2}" y="76" font-size="14" font-weight="600" fill="#64748b" text-anchor="middle">Start om 10:00 CEST • Tijd-Ruimte Diagram met Isochronen, Isotachen &amp; Dubbele Meestroom Tactiek</text>')
    svg.append('  </g>')

    # 3. Context & Perspective Banner (Above the matrix)
    svg.append('  <!-- ================= PERSPECTIVE BANNER ================= -->')
    # Heen banner (Left: 60 to 655)
    svg.append('  <g id="banner_out" transform="translate(60, 115)">')
    svg.append('    <rect x="0" y="0" width="595" height="38" rx="7" fill="#f0f9ff" stroke="#bae6fd" stroke-width="1.3"/>')
    svg.append('    <text x="14" y="24" font-size="11.5" font-weight="800" fill="#0369a1">🏊 1. HEENWEG (0k0 ➔ 3k0): ZWEMRICHTING NOORDOOST [NL]</text>')
    svg.append('    <text x="580" y="24" font-size="10.5" font-weight="800" fill="#0284c7" text-anchor="end">RECHTS = VLOED (MEESTROOM ➔)</text>')
    svg.append('  </g>')
    # Terug banner (Right: 685 to 1235)
    svg.append(f'  <g id="banner_ret" transform="translate(685, 115)">')
    svg.append('    <rect x="0" y="0" width="550" height="38" rx="7" fill="#f1f5f9" stroke="#cbd5e1" stroke-width="1.3"/>')
    svg.append('    <text x="14" y="24" font-size="11.5" font-weight="800" fill="#334155">🔄 2. TERUGWEG (3k0 ➔ 6k0): ZWEMRICHTING ZUIDWEST [FR]</text>')
    svg.append('    <text x="535" y="24" font-size="10.5" font-weight="800" fill="#4338ca" text-anchor="end">RECHTS = EB (MEESTROOM ➔)</text>')
    svg.append('  </g>')

    # 4. Coastal Landmark Strip (Top of Spines)
    svg.append('  <!-- ================= LANDMARK STRIP ================= -->')
    for cp in checkpoints:
        cx = cp["x"]
        is_turn = (cp["leg"] == "turn")
        badge_bg = "#b91c1c" if is_turn else ("#0f172a" if cp["leg"] == "out" else "#334155")
        
        svg.append(f'    <g transform="translate({cx}, 170)">')
        # Landmark name
        svg.append(f'      <text x="0" y="0" font-size="9.5" font-weight="700" fill="#64748b" text-anchor="middle">{cp["landmark"]}</text>')
        # Checkpoint Post Badge
        svg.append(f'      <rect x="-18" y="8" width="36" height="20" rx="4" fill="{badge_bg}"/>')
        svg.append(f'      <text x="0" y="22" font-size="10.5" font-weight="900" fill="#ffffff" text-anchor="middle">{cp["post"]}</text>')
        # Total Distance & Leg Distance
        svg.append(f'      <text x="0" y="42" font-size="13.5" font-weight="900" fill="#0f172a" text-anchor="middle">{cp["km_tot"]}</text>')
        svg.append(f'    </g>')

    # 5. Central Turnaround Milestone Divider (at x=turn_x)
    svg.append('  <!-- ================= KEERPUNT DIVIDER ================= -->')
    svg.append(f'  <line x1="{turn_x}" y1="215" x2="{turn_x}" y2="585" stroke="#ef4444" stroke-width="2.5" stroke-dasharray="6,4"/>')
    svg.append(f'  <g transform="translate({turn_x}, 224)">')
    svg.append(f'    <rect x="-65" y="0" width="130" height="24" rx="12" fill="#ef4444" filter="url(#badgeShadow)"/>')
    svg.append(f'    <text x="0" y="16" font-size="10.5" font-weight="900" fill="#ffffff" text-anchor="middle">🏁 180° KEERPUNT</text>')
    svg.append(f'  </g>')

    # 6. Matrix & Spines Surface
    y_spine_top = y_ref - 110
    y_spine_bottom = y_ref + 115
    scale_v = 40.0  # px per 1.0 m/s current

    svg.append('  <!-- ================= ISOCHRONES (TIME CONTOURS) ================= -->')
    for iso in isochrones:
        pts_str = " ".join(f"{pt[0]},{pt[1]:.1f}" for pt in iso["points"])
        svg.append(f'    <polyline points="{pts_str}" fill="none" stroke="#cbd5e1" stroke-width="1.2" stroke-dasharray="3,3" opacity="0.85"/>')
        first_pt = iso["points"][0]
        if first_pt[0] == x_coords[0]:
            svg.append(f'    <text x="{first_pt[0] - 12}" y="{first_pt[1] + 3.5}" font-family="monospace" font-size="9.5" font-weight="700" fill="#94a3b8" text-anchor="end">{iso["time"]}</text>')

    # Swimmer Corridor Highlight for Reference Swimmer (y_ref)
    svg.append(f'  <!-- Horizontal Corridor for Reference Swimmer -->')
    svg.append(f'  <rect x="60" y="{y_ref - 18}" width="1180" height="36" rx="6" fill="#f0fdf4" opacity="0.88" stroke="#bbf7d0" stroke-width="1.5" stroke-dasharray="5,4"/>')
    svg.append(f'  <g transform="translate(68, {y_ref - 24})">')
    svg.append(f'    <rect x="0" y="-12" width="280" height="18" rx="4" fill="#dcfce7" stroke="#86efac" stroke-width="1"/>')
    svg.append(f'    <text x="8" y="1" font-size="9.5" font-weight="800" fill="#15803d">HORIZONTALE AS = REFERENTIEZWEMMER (1.0 m/s)</text>')
    svg.append(f'  </g>')

    # Draw Vertical Spines & Tidal Current Vectors
    svg.append('  <!-- ================= SPINES & CURRENT VECTORS ================= -->')
    for cp_idx, cp in enumerate(checkpoints):
        cx = cp["x"]
        is_turn = (cp["leg"] == "turn")
        spine_color = "#ef4444" if is_turn else "#94a3b8"
        svg.append(f'    <line x1="{cx}" y1="{y_spine_top}" x2="{cx}" y2="{y_spine_bottom}" stroke="{spine_color}" stroke-width="{2.0 if is_turn else 1.4}"/>')

        bars = spine_currents[cp_idx]["bars"]
        for b in bars:
            by = y_ref + b["dt"] * scale_t
            v = b["v"]
            bar_len = v * scale_v

            if v > 0.06:
                end_x = cx + bar_len
                bar_color = "#0284c7" if cp["leg"] == "out" else "#4338ca"
                marker_url = "url(#arrowBlue)" if cp["leg"] == "out" else "url(#arrowPurple)"
                svg.append(f'    <line x1="{cx}" y1="{by}" x2="{end_x}" y2="{by}" stroke="{bar_color}" stroke-width="3.2" stroke-linecap="round" marker-end="{marker_url}"/>')
            elif v < -0.06:
                end_x = cx + bar_len
                svg.append(f'    <line x1="{cx}" y1="{by}" x2="{end_x}" y2="{by}" stroke="#ea580c" stroke-width="3.2" stroke-linecap="round" marker-start="url(#arrowOrange)"/>')
            else:
                # Kentering dot (Green)
                svg.append(f'    <circle cx="{cx}" cy="{by}" r="5.5" fill="#16a34a" stroke="#ffffff" stroke-width="2" filter="url(#softShadow)"/>')

            # Spine tick
            svg.append(f'    <line x1="{cx - 3}" y1="{by}" x2="{cx + 3}" y2="{by}" stroke="#94a3b8" stroke-width="1"/>')

    # Draw Isotach Scenario Curves
    svg.append('  <!-- ================= ISOTACHS (SWIMMER PACE FAN) ================= -->')
    for sc in scenarios:
        pts = sc["points"]
        path_d = "M " + " L ".join(f"{pt[0]} {pt[1]:.1f}" for pt in pts)
        dash_attr = f'stroke-dasharray="{sc["dash"]}"' if sc["dash"] != "none" else ""
        svg.append(f'    <path d="{path_d}" fill="none" stroke="{sc["color"]}" stroke-width="{sc["lw"]}" {dash_attr} stroke-linecap="round" opacity="0.95"/>')
        
        r_node = 6.0 if sc.get("is_ref") else 4.5
        for pt in pts:
            svg.append(f'    <circle cx="{pt[0]}" cy="{pt[1]:.1f}" r="{r_node}" fill="{sc["color"]}" stroke="#ffffff" stroke-width="1.5"/>')
        
        last_pt = pts[-1]
        svg.append(f'    <text x="{last_pt[0] + 16}" y="{last_pt[1] + 4:.1f}" font-size="11" font-weight="800" fill="{sc["color"]}">{sc["speed"]} m/s</text>')

    # 7. Water Level Indicator Badges (Start, Turn, Finish)
    svg.append('  <!-- ================= WATER LEVEL HIGHLIGHT CARDS ================= -->')
    wl_cards = [
        {"x": x_coords[0], "time": "10:00 CEST", "label": "START • WATERSTAND", "val": "4.55 m TAW", "phase": "Vloed (HW - 50m)", "color": "#0284c7"},
        {"x": turn_x, "time": "10:50 CEST", "label": "KEERPUNT • WATERSTAND", "val": "4.95 m TAW", "phase": "Hoogwater Kentering", "color": "#ef4444"},
        {"x": x_coords[8], "time": "11:40 CEST", "label": "FINISH • WATERSTAND", "val": "4.58 m TAW", "phase": "Eb (HW + 50m)", "color": "#4338ca"},
    ]
    for card in wl_cards:
        cx = card["x"]
        svg.append(f'  <g transform="translate({cx}, 538)">')
        svg.append(f'    <rect x="-82" y="0" width="164" height="60" rx="8" fill="#ffffff" stroke="{card["color"]}" stroke-width="1.6" filter="url(#softShadow)"/>')
        svg.append(f'    <text x="0" y="16" font-size="9" font-weight="800" fill="#64748b" text-anchor="middle">{card["label"]}</text>')
        svg.append(f'    <text x="0" y="35" font-size="14.5" font-weight="900" fill="{card["color"]}" text-anchor="middle">{card["val"]}</text>')
        svg.append(f'    <text x="0" y="50" font-size="9.5" font-weight="600" fill="#475569" text-anchor="middle">{card["phase"]}</text>')
        svg.append(f'  </g>')

    # 8. Trajectory Timing Table (Bottom Bands)
    y_table_top = 622.0
    svg.append(f'  <!-- ================= TIMING TABLE (BOTTOM) ================= -->')
    svg.append(f'  <g id="timing_table" transform="translate(0, {y_table_top})">')
    svg.append('    <text x="60" y="-10" font-size="11.5" font-weight="900" fill="#0f172a">⏱️ DOORKOMSTTIJDEN (TRAJECT TIMING PER TEMPO):</text>')

    for sc_i, sc in enumerate([scenarios[0], scenarios[2], scenarios[4]]):  # Fast, Ref, Slow
        by = sc_i * 32.0
        svg.append(f'    <g transform="translate(60, {by})">')
        svg.append(f'      <rect x="0" y="0" width="95" height="26" rx="5" fill="#f8fafc" stroke="#cbd5e1" stroke-width="1.0"/>')
        svg.append(f'      <circle cx="10" cy="13" r="4" fill="{sc["color"]}"/>')
        svg.append(f'      <text x="20" y="17" font-size="10" font-weight="800" fill="{sc["color"]}">{sc["speed"]} m/s</text>')
        svg.append('    </g>')

        for cp_i, cp in enumerate(checkpoints):
            t_str = sc["times"][cp_i]
            cx = cp["x"]
            is_turn = (cp["leg"] == "turn")
            badge_border = "#fca5a5" if is_turn else "#e2e8f0"
            badge_bg = "#fef2f2" if is_turn else ("#f8fafc" if cp["leg"] == "ret" else "#ffffff")
            svg.append(f'    <g transform="translate({cx - 30}, {by})">')
            svg.append(f'      <rect x="0" y="0" width="60" height="26" rx="5" fill="{badge_bg}" stroke="{badge_border}" stroke-width="1.0"/>')
            svg.append(f'      <text x="30" y="17" font-family="monospace" font-size="11" font-weight="800" fill="{sc["color"]}" text-anchor="middle">{t_str}</text>')
            svg.append('    </g>')
    svg.append('  </g>')

    # 9. Tactical Swim Insight Card
    svg.append('  <!-- ================= TACTICAL INSIGHT CARD ================= -->')
    svg.append('  <g id="tactical_insight" transform="translate(60, 738)">')
    svg.append('    <rect x="0" y="0" width="1180" height="96" rx="10" fill="#f8fafc" stroke="#0284c7" stroke-width="1.8" filter="url(#softShadow)"/>')
    svg.append('    <text x="25" y="26" font-size="13" font-weight="900" fill="#0f172a">💡 DE DUBBELE MEESTROOM TACTIEK (THE DOUBLE TAILWIND SURF):</text>')
    svg.append('    <text x="500" y="26" font-size="12.5" font-weight="800" fill="#15803d">Vertrek 50 min vóór HW-kentering = Zowel op de heenweg als de terugweg 100% MEESTROOM!</text>')
    svg.append('    <text x="25" y="48" font-size="11.5" font-weight="500" fill="#334155">• Heenweg (Bredene ➔ Vosseslag): Zwemmen naar het noordoosten (NL) met de afnemende vloedstroom mee (blauwe pijlen naar rechts).</text>')
    svg.append('    <text x="25" y="66" font-size="11.5" font-weight="500" fill="#334155">• Keerpunt (10:50): Exact op de kentering bij Vosseslag keren! De stroom valt stil (groene cirkel op keerpunt-as).</text>')
    svg.append('    <text x="25" y="84" font-size="11.5" font-weight="500" fill="#334155">• Terugweg (Vosseslag ➔ Bredene): Zwemmen naar het zuidwesten (FR) terwijl de ebstroom aanzwelt — opnieuw 100% MEESTROOM (paarse pijlen naar rechts)!</text>')
    svg.append('  </g>')

    # 10. Footer
    svg.append('  <!-- ================= FOOTER ================= -->')
    svg.append('  <g id="footer" transform="translate(60, 895)">')
    svg.append('    <text x="0" y="0" font-size="11" font-weight="600" fill="#94a3b8">CSCM • Lagrangiaans Kustzwem-Trajectmodel • Decoupled Grid &amp; Isochronen</text>')
    svg.append('    <text x="1180" y="0" font-size="11" font-weight="700" fill="#94a3b8" text-anchor="end">ONTWERP v2 (HEEN &amp; TERUG)</text>')
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
