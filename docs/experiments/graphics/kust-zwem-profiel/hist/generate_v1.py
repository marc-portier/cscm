#!/usr/bin/env python3
"""
Prototype Generator for Coastal Swim Trajectory Profile (Kustzwem-Profiel v1).

Concept from Marc Portier's sketch:
- Horizontal axis: Distance checkpoints along the coast (0 km, 0.75 km, 1.5 km, 2.25 km, 3.0 km).
- Vertical axis per checkpoint: Current spine (visgraat) with alongshore tidal vectors.
- Vertical time alignment: Each spine is vertically offset by the elapsed swim time of a
  reference swimmer (1.0 m/s), turning their journey into a straight horizontal reference line!
- Alternative swimmer paces (Fast, Slow) appear as sloping trajectory paths through the spines.
- Trajectory timing badges at the bottom indicate exact ETA per checkpoint.
"""

from pathlib import Path
import subprocess

HIST_DIR = Path(__file__).resolve().parent
OUTPUT_SVG = HIST_DIR / "ontwerp-kustzwem-profiel-v1.svg"
OUTPUT_PNG = HIST_DIR / "ontwerp-kustzwem-profiel-v1.png"


def generate_svg():
    # Checkpoints evenly spaced across width
    checkpoints = [
        {"km": "0.0k", "name": "Start: Post 4", "x": 220},
        {"km": "0.75k", "name": "Post 3 (Duinen)", "x": 365},
        {"km": "1.50k", "name": "Post 2 (Centrum)", "x": 510},
        {"km": "2.25k", "name": "Post 1 (Oost)", "x": 655},
        {"km": "3.00k", "name": "Vosseslag", "x": 800},
    ]

    # Swimmer Scenarios & Checkpoint Times
    scenarios = {
        "fast": {
            "name": "Snel (1.3 m/s)",
            "pace_desc": "Kruissnelheid atleet",
            "color": "#0284c7",
            "bg": "#f0f9ff",
            "border": "#bae6fd",
            "times": ["10:00", "10:18", "10:35", "10:55", "11:20"],
            "y_offsets": [0, -18, -34, -48, -62],  # Arrives earlier = higher up on spine
        },
        "ref": {
            "name": "Referentie (1.0 m/s)",
            "pace_desc": "Competitief tempo",
            "color": "#16a34a",
            "bg": "#f0fdf4",
            "border": "#bbf7d0",
            "times": ["10:00", "10:20", "10:40", "11:05", "11:30"],
            "y_offsets": [0, 0, 0, 0, 0],  # Aligned horizontally on y_ref
        },
        "slow": {
            "name": "Recreatief (0.7 m/s)",
            "pace_desc": "Rustige crawl / schoolslag",
            "color": "#ea580c",
            "bg": "#fff7ed",
            "border": "#fed7aa",
            "times": ["10:00", "10:25", "10:50", "11:20", "12:00"],
            "y_offsets": [0, 22, 45, 72, 102],  # Arrives later = lower down on spine
        },
    }

    y_ref = 320.0  # Horizontal baseline of reference swimmer

    # Current profile model across checkpoints (simulated realistic tidal phase):
    # Checkpoint 0 (10:00): Strong flood (+0.95 m/s)
    # Checkpoint 1 (10:20): Strong flood (+0.90 m/s)
    # Checkpoint 2 (10:40): Slackening flood (+0.65 m/s)
    # Checkpoint 3 (11:05): Approaching slack water / kentering (+0.20 m/s)
    # Checkpoint 4 (11:30): Kentering / slight ebb (-0.15 m/s)
    spine_currents = [
        # cp 0
        [{"dt": -45, "v": 1.05}, {"dt": -30, "v": 1.02}, {"dt": -15, "v": 0.98}, {"dt": 0, "v": 0.95}, {"dt": 15, "v": 0.88}, {"dt": 30, "v": 0.78}, {"dt": 45, "v": 0.65}],
        # cp 1
        [{"dt": -45, "v": 1.02}, {"dt": -30, "v": 0.98}, {"dt": -15, "v": 0.94}, {"dt": 0, "v": 0.90}, {"dt": 15, "v": 0.82}, {"dt": 30, "v": 0.70}, {"dt": 45, "v": 0.55}],
        # cp 2
        [{"dt": -45, "v": 0.92}, {"dt": -30, "v": 0.85}, {"dt": -15, "v": 0.75}, {"dt": 0, "v": 0.65}, {"dt": 15, "v": 0.50}, {"dt": 30, "v": 0.35}, {"dt": 45, "v": 0.20}],
        # cp 3
        [{"dt": -45, "v": 0.65}, {"dt": -30, "v": 0.50}, {"dt": -15, "v": 0.35}, {"dt": 0, "v": 0.20}, {"dt": 15, "v": 0.05}, {"dt": 30, "v": -0.10}, {"dt": 45, "v": -0.25}],
        # cp 4
        [{"dt": -45, "v": 0.35}, {"dt": -30, "v": 0.20}, {"dt": -15, "v": 0.02}, {"dt": 0, "v": -0.15}, {"dt": 15, "v": -0.30}, {"dt": 30, "v": -0.45}, {"dt": 45, "v": -0.58}],
    ]

    scale_v = 45.0  # px per 1.0 m/s

    svg = []
    svg.append('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 960 780" width="100%" height="100%" style="background-color: #ffffff; font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, Helvetica, Arial, sans-serif;">')
    svg.append('  <defs>')
    svg.append('    <filter id="softShadow" x="-10%" y="-10%" width="120%" height="120%">')
    svg.append('      <feDropShadow dx="0" dy="2" stdDeviation="3" flood-opacity="0.08"/>')
    svg.append('    </filter>')
    svg.append('    <filter id="badgeShadow" x="-15%" y="-15%" width="130%" height="130%">')
    svg.append('      <feDropShadow dx="0" dy="2.5" stdDeviation="3.5" flood-opacity="0.14"/>')
    svg.append('    </filter>')
    svg.append('  </defs>')

    # Solid Canvas Background
    svg.append('  <rect x="0" y="0" width="960" height="780" fill="#ffffff"/>')

    # Header
    svg.append('  <!-- ================= HEADER ================= -->')
    svg.append('  <g id="header" transform="translate(0, 32)">')
    svg.append('    <text x="480" y="20" font-size="12" font-weight="800" letter-spacing="1.8" fill="#0284c7" text-anchor="middle">CSCM KUSTZWEM-TRAJECTPROFIEL • CONCEPT PROTOTYPE v1</text>')
    svg.append('    <text x="480" y="56" font-size="30" font-weight="900" fill="#0f172a" text-anchor="middle">Traject: Bredene Post 4 ➔ De Haan (3.0 km)</text>')
    svg.append('    <text x="480" y="82" font-size="14.5" font-weight="500" fill="#64748b" text-anchor="middle">Start om 10:00 CEST • Tijd-Ruimte Visgraten per 750m doorkomstpunt</text>')
    svg.append('  </g>')

    # Direction Bar
    svg.append('  <!-- ================= DIRECTION BAR ================= -->')
    svg.append('  <g id="direction_bar" transform="translate(45, 130)">')
    svg.append('    <rect x="0" y="0" width="870" height="38" rx="8" fill="#f8fafc" stroke="#e2e8f0" stroke-width="1.2"/>')
    svg.append('    <g transform="translate(18, 19)">')
    svg.append('      <path d="M 14 0 L 0 0 M 0 0 L 5 -4 M 0 0 L 5 4" stroke="#4f46e5" stroke-width="2.2" stroke-linecap="round"/>')
    svg.append('      <text x="22" y="4.5" font-size="12" font-weight="800" fill="#4f46e5">[FR] EBBESTROOM (ZW) • TEGENSTROOM</text>')
    svg.append('    </g>')
    svg.append('    <circle cx="435" cy="19" r="3.5" fill="#cbd5e1"/>')
    svg.append('    <g transform="translate(852, 19)">')
    svg.append('      <path d="M -14 0 L 0 0 M 0 0 L -5 -4 M 0 0 L -5 4" stroke="#0284c7" stroke-width="2.2" stroke-linecap="round"/>')
    svg.append('      <text x="-22" y="4.5" font-size="12" font-weight="800" fill="#0284c7" text-anchor="end">MEESTROOM / VLOED (NO) • NEDERLAND [NL]</text>')
    svg.append('    </g>')
    svg.append('  </g>')

    # Chart Surface
    svg.append('  <!-- ================= SPATIAL-TEMPORAL MATRIX ================= -->')
    svg.append('  <g id="matrix_surface">')

    # Background Highlight Band for Reference Swimmer Corridor (Horizontal y_ref)
    svg.append(f'    <!-- Horizontal Reference Corridor (Green Swimmer Trajectory) -->')
    svg.append(f'    <rect x="45" y="{y_ref - 18}" width="870" height="36" rx="6" fill="#f0fdf4" opacity="0.9" stroke="#bbf7d0" stroke-width="1.2" stroke-dasharray="4,4"/>')
    svg.append(f'    <text x="50" y="{y_ref - 24}" font-size="11" font-weight="800" fill="#15803d">HORIZONTALE ZICHTLIJN = REFERENTIEZWERMMER (1.0 m/s)</text>')

    # Draw vertical spines and vector bars
    y_spine_top = y_ref - 105
    y_spine_bottom = y_ref + 115

    for cp_idx, cp in enumerate(checkpoints):
        cx = cp["x"]
        # Checkpoint Header
        svg.append(f'    <!-- Checkpoint {cp["km"]} -->')
        svg.append(f'    <g transform="translate({cx}, 190)">')
        svg.append(f'      <circle cx="0" cy="0" r="14" fill="#0f172a"/>')
        svg.append(f'      <text x="0" y="4" font-size="11" font-weight="900" fill="#ffffff" text-anchor="middle">{cp_idx}</text>')
        svg.append(f'      <text x="0" y="24" font-size="14" font-weight="900" fill="#0f172a" text-anchor="middle">{cp["km"]}</text>')
        svg.append(f'      <text x="0" y="38" font-size="10.5" font-weight="600" fill="#64748b" text-anchor="middle">{cp["name"]}</text>')
        svg.append(f'    </g>')

        # Vertical Spine Line
        svg.append(f'    <line x1="{cx}" y1="{y_spine_top}" x2="{cx}" y2="{y_spine_bottom}" stroke="#cbd5e1" stroke-width="1.6"/>')

        # Visgraat horizontal bars
        bars = spine_currents[cp_idx]
        for b in bars:
            by = y_ref + (b["dt"] / 15.0) * 18.0
            v = b["v"]
            bar_len = v * scale_v

            if v > 0.05:
                # Flood / Alongshore right
                end_x = cx + bar_len
                svg.append(f'    <line x1="{cx}" y1="{by}" x2="{end_x}" y2="{by}" stroke="#0284c7" stroke-width="3.5" stroke-linecap="round"/>')
                svg.append(f'    <circle cx="{end_x}" cy="{by}" r="4" fill="#ffffff" stroke="#0284c7" stroke-width="1.5"/>')
            elif v < -0.05:
                # Ebb / Alongshore left
                end_x = cx + bar_len
                svg.append(f'    <line x1="{cx}" y1="{by}" x2="{end_x}" y2="{by}" stroke="#4f46e5" stroke-width="3.5" stroke-linecap="round"/>')
                svg.append(f'    <circle cx="{end_x}" cy="{by}" r="4" fill="#ffffff" stroke="#4f46e5" stroke-width="1.5"/>')
            else:
                # Kentering
                svg.append(f'    <circle cx="{cx}" cy="{by}" r="4.5" fill="#16a34a" stroke="#ffffff" stroke-width="1.5"/>')

            # Small time tick on spine
            svg.append(f'    <line x1="{cx - 3}" y1="{by}" x2="{cx + 3}" y2="{by}" stroke="#94a3b8" stroke-width="1"/>')

    # Draw Scenario Trajectory Lines across spines
    # 1. Fast Swimmer (Blue - slanting upward to earlier times)
    fast_pts = []
    for cp_idx, cp in enumerate(checkpoints):
        px = cp["x"]
        py = y_ref + scenarios["fast"]["y_offsets"][cp_idx]
        fast_pts.append((px, py))
    path_d = "M " + " L ".join(f"{pt[0]} {pt[1]}" for pt in fast_pts)
    svg.append(f'    <!-- Fast Swimmer Trajectory (Blue) -->')
    svg.append(f'    <path d="{path_d}" fill="none" stroke="#0284c7" stroke-width="3" stroke-linecap="round" opacity="0.85"/>')
    for pt in fast_pts:
        svg.append(f'    <circle cx="{pt[0]}" cy="{pt[1]}" r="6" fill="#0284c7" stroke="#ffffff" stroke-width="2"/>')

    # 2. Reference Swimmer (Green - exact horizontal)
    ref_pts = []
    for cp_idx, cp in enumerate(checkpoints):
        px = cp["x"]
        py = y_ref + scenarios["ref"]["y_offsets"][cp_idx]
        ref_pts.append((px, py))
    path_d = "M " + " L ".join(f"{pt[0]} {pt[1]}" for pt in ref_pts)
    svg.append(f'    <!-- Reference Swimmer Trajectory (Green - Horizontaal) -->')
    svg.append(f'    <path d="{path_d}" fill="none" stroke="#16a34a" stroke-width="3.5" stroke-linecap="round"/>')
    for pt in ref_pts:
        svg.append(f'    <circle cx="{pt[0]}" cy="{pt[1]}" r="6.5" fill="#16a34a" stroke="#ffffff" stroke-width="2" filter="url(#badgeShadow)"/>')

    # 3. Slow Swimmer (Orange - slanting downward to later times)
    slow_pts = []
    for cp_idx, cp in enumerate(checkpoints):
        px = cp["x"]
        py = y_ref + scenarios["slow"]["y_offsets"][cp_idx]
        slow_pts.append((px, py))
    path_d = "M " + " L ".join(f"{pt[0]} {pt[1]}" for pt in slow_pts)
    svg.append(f'    <!-- Slow Swimmer Trajectory (Orange) -->')
    svg.append(f'    <path d="{path_d}" fill="none" stroke="#ea580c" stroke-width="3" stroke-linecap="round" opacity="0.85"/>')
    for pt in slow_pts:
        svg.append(f'    <circle cx="{pt[0]}" cy="{pt[1]}" r="6" fill="#ea580c" stroke="#ffffff" stroke-width="2"/>')

    # Trajectory Timing Table (Bottom Bands)
    svg.append('    <!-- ================= TIMING BANDS (ONDERKANT) ================= -->')
    y_table_top = 465.0

    svg.append(f'    <g id="timing_table" transform="translate(0, {y_table_top})">')
    svg.append('      <text x="45" y="-12" font-size="12" font-weight="900" fill="#0f172a">⏱️ DOORKOMSTTIJDEN (TRAJECT TIMING PER TEMPO):</text>')

    sc_keys = ["fast", "ref", "slow"]
    for sc_i, k in enumerate(sc_keys):
        sc = scenarios[k]
        by = sc_i * 42.0

        # Dedicated Scenario Label Card on Left
        svg.append(f'      <g transform="translate(45, {by})">')
        svg.append(f'        <rect x="0" y="0" width="145" height="34" rx="6" fill="{sc["bg"]}" stroke="{sc["border"]}" stroke-width="1.2"/>')
        svg.append(f'        <circle cx="14" cy="17" r="5" fill="{sc["color"]}"/>')
        svg.append(f'        <text x="26" y="16" font-size="11" font-weight="800" fill="{sc["color"]}">{sc["name"]}</text>')
        svg.append(f'        <text x="26" y="27" font-size="9" font-weight="600" fill="#64748b">{sc["pace_desc"]}</text>')
        svg.append('      </g>')

        # Badges per checkpoint column
        for cp_idx, cp in enumerate(checkpoints):
            t_str = sc["times"][cp_idx]
            cx = cp["x"]
            svg.append(f'      <g transform="translate({cx - 36}, {by})">')
            svg.append(f'        <rect x="0" y="0" width="72" height="34" rx="6" fill="{sc["bg"]}" stroke="{sc["border"]}" stroke-width="1.2" filter="url(#softShadow)"/>')
            svg.append(f'        <text x="36" y="21" font-family="monospace" font-size="13" font-weight="900" fill="{sc["color"]}" text-anchor="middle">{t_str}</text>')
            svg.append('      </g>')

    svg.append('    </g>')
    svg.append('  </g>')

    # Insight Box (Bottom)
    svg.append('  <!-- ================= INZICHT CALLOUT BOX ================= -->')
    svg.append('  <g id="insight_box" transform="translate(45, 615)">')
    svg.append('    <rect x="0" y="0" width="870" height="76" rx="8" fill="#f8fafc" stroke="#cbd5e1" stroke-width="1.5" filter="url(#softShadow)"/>')
    svg.append('    <text x="22" y="26" font-size="13" font-weight="900" fill="#0f172a">💡 TIJD-RUIMTE INTERPRETATIE:</text>')
    svg.append('    <text x="260" y="26" font-size="13" font-weight="700" fill="#15803d">Horizontale groene zichtlijn = Het reële stromingsgevoel van de referentiezwemmer!</text>')
    svg.append('    <text x="22" y="50" font-size="12" font-weight="500" fill="#475569">Door elke visgraat omhoog/omlaag te schuiven volgens de reistijd, leest de zwemmer van links naar rechts direct af wanneer de meestroom afneemt (0k➔1.5k) en omslaat naar kentering bij km 2.25➔3.0.</text>')
    svg.append('  </g>')

    # Sub-footer
    svg.append('  <!-- ================= SUB-FOOTER ================= -->')
    svg.append('  <g id="footer" transform="translate(45, 742)">')
    svg.append('    <text x="0" y="0" font-size="10.5" font-weight="600" fill="#94a3b8">CSCM • Trajectmodel 750m Intervallen &amp; Lagrangiaanse Getijdentransformatie</text>')
    svg.append('    <text x="870" y="0" font-size="10.5" font-weight="700" fill="#94a3b8" text-anchor="end">ONTWERP-SCHETS v1 • MARIEKE &amp; MARC PORTIER</text>')
    svg.append('  </g>')

    svg.append('</svg>')

    rendered = "\n".join(svg)
    with open(OUTPUT_SVG, "w", encoding="utf-8") as f:
        f.write(rendered)
    print(f"Generated {OUTPUT_SVG}")

    try:
        subprocess.run(["rsvg-convert", "-w", "1200", str(OUTPUT_SVG), "-o", str(OUTPUT_PNG)], check=True)
        print(f"Generated {OUTPUT_PNG}")
    except Exception as e:
        print(f"Could not convert to PNG: {e}")


if __name__ == "__main__":
    generate_svg()
