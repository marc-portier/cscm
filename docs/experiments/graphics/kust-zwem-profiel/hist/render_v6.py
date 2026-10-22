#!/usr/bin/env python3
"""
Renderer for Coastal Swim Trajectory Profile v6 (Kustzwem-Profiel v6).

Reads strictly from data_to_plot_v6.yaml and renders the print-ready DIN A3 Landscape SVG/PNG.
Adheres strictly to the graphics-experimenting skill:
- Decoupled from data retrieval (zero external API/model dependencies).
- Strict physical tide colors: Vloedstroom = Blauw (#0284c7), Ebstroom = Paars (#4338ca).
- High-contrast white nautical cross-hatch for return leg (swimming West / FR).
- Starttijd-venster envelope band with bidirectional gradient.
- 8 bottom vector cards with proportional scale and 750m target tick.
"""

from pathlib import Path
import subprocess
import yaml
import numpy as np


HIST_DIR = Path(__file__).resolve().parent
INPUT_YAML = HIST_DIR / "data_to_plot_v6.yaml"
OUTPUT_SVG = HIST_DIR / "ontwerp-kustzwem-profiel-v6.svg"
OUTPUT_PNG = HIST_DIR / "ontwerp-kustzwem-profiel-v6.png"


def poly_to_path(pts):
    if not pts:
        return ""
    return "M " + " L ".join(f"{p[0]:.1f} {p[1]:.1f}" for p in pts)


def render():
    print("=" * 60)
    print("CSCM Kustzwem-Profiel v6: Rendering Infographic (Sat 24 Oct 2026)")
    print("=" * 60)

    if not INPUT_YAML.exists():
        raise FileNotFoundError(f"Input YAML contract not found: {INPUT_YAML}")

    with open(INPUT_YAML, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    geom = data["geometry"]
    width = geom["width"]
    height = geom["height"]
    y_spine_top = geom["y_spine_top"]
    y_spine_bottom = geom["y_spine_bottom"]
    y_ref = geom["y_ref"]
    scale_t = geom["vertical_scale_px_per_min"]
    scale_v = geom["horizontal_scale_px_per_ms"]
    x_heen = geom["x_heen"]
    x_terug = geom["x_terug"]
    x_mid_turn = geom["x_mid_turn"]

    checkpoints = data["checkpoints"]
    nominal_schedule = data["nominal_schedule"]
    leg_breakdown = data["leg_breakdown"]
    speeds_analyzed = data["speeds_analyzed"]
    curves = data["curves"]
    envelope = data["envelope"]
    isochrones = data["isochrones"]
    spine_data = data["spine_data"]
    fc_meta = data["forecast_metadata"]

    svg = []
    svg.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="100%" height="100%" style="background-color: #ffffff; font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, Helvetica, Arial, sans-serif;">')

    # Defs: filters, patterns, gradients
    svg.append('  <defs>')
    svg.append('    <filter id="softShadow" x="-10%" y="-10%" width="120%" height="120%">')
    svg.append('      <feDropShadow dx="0" dy="2" stdDeviation="3" flood-opacity="0.08"/>')
    svg.append('    </filter>')
    svg.append('    <filter id="badgeShadow" x="-15%" y="-15%" width="130%" height="130%">')
    svg.append('      <feDropShadow dx="0" dy="2.5" stdDeviation="3.5" flood-opacity="0.14"/>')
    svg.append('    </filter>')
    # High-Contrast White Nautical Cross-Hatch for Return Leg
    svg.append('    <pattern id="whiteCrossHatch" width="6" height="6" patternTransform="rotate(45 0 0)" patternUnits="userSpaceOnUse">')
    svg.append('      <line x1="0" y1="0" x2="0" y2="6" stroke="#ffffff" stroke-width="1.3" opacity="0.95"/>')
    svg.append('      <line x1="0" y1="0" x2="6" y2="0" stroke="#ffffff" stroke-width="1.3" opacity="0.95"/>')
    svg.append('    </pattern>')
    # Bidirectional Vertical Density Gradient for Starttijd-Venster
    svg.append('    <linearGradient id="envelopeGrad" x1="0" y1="0" x2="0" y2="1">')
    svg.append('      <stop offset="0%" stop-color="#10b981" stop-opacity="0.02"/>')
    svg.append('      <stop offset="50%" stop-color="#10b981" stop-opacity="0.22"/>')
    svg.append('      <stop offset="100%" stop-color="#10b981" stop-opacity="0.02"/>')
    svg.append('    </linearGradient>')
    svg.append('  </defs>')

    # 1. Backgrounds
    svg.append('  <!-- Canvas Background -->')
    svg.append(f'  <rect x="0" y="0" width="{width}" height="{height}" fill="#ffffff"/>')

    # Return Leg Tinted Background (x_mid_turn to 1370)
    svg.append('  <!-- Return Leg Tinted Background (Zwemrichting West / FR) -->')
    svg.append(f'  <rect x="{x_mid_turn}" y="80" width="{1370 - x_mid_turn}" height="730" rx="10" fill="#f8fafc" stroke="#e2e8f0" stroke-width="1.2"/>')

    # 2. Header
    hw_str = f"HW {fc_meta['high_water']['time_local']} ({fc_meta['high_water']['height_m_taw']:.2f}m TAW)"
    lw_str = f"LW {fc_meta['low_water']['time_local']} ({fc_meta['low_water']['height_m_taw']:.2f}m TAW)"

    svg.append('  <!-- ================= HEADER ================= -->')
    svg.append('  <g id="header" transform="translate(0, 30)">')
    svg.append(f'    <text x="{width/2}" y="0" font-size="22" font-weight="900" fill="#0f172a" text-anchor="middle">Traject: Bredene Post 4 ➔ Vosseslag ➔ Bredene Post 4 (6.0 km)</text>')
    svg.append(f'    <text x="{width/2}" y="22" font-size="12" font-weight="600" fill="#64748b" text-anchor="middle">Zaterdag 24 Oktober 2026 • Start 10:00 CEST • Tijd-Ruimte Diagram met Snelheidswaaier, Isochronen &amp; Stroom-Ontbinding</text>')
    # Tide Forecast Badges in Header
    svg.append('    <g transform="translate(45, -5)">')
    svg.append('      <rect x="0" y="0" width="230" height="26" rx="5" fill="#f0f9ff" stroke="#bae6fd" stroke-width="1.0"/>')
    svg.append(f'      <text x="12" y="17" font-size="10.5" font-weight="800" fill="#0369a1">🌊 {hw_str}</text>')
    svg.append('    </g>')
    svg.append(f'    <g transform="translate({width - 275}, -5)">')
    svg.append('      <rect x="0" y="0" width="230" height="26" rx="5" fill="#f8fafc" stroke="#cbd5e1" stroke-width="1.0"/>')
    svg.append(f'      <text x="12" y="17" font-size="10.5" font-weight="800" fill="#475569">🌊 {lw_str}</text>')
    svg.append('    </g>')
    svg.append('  </g>')

    # 3. Perspective Banners (Above matrix)
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
        t_nom = nominal_schedule[cp_i]["time"]

        svg.append(f'  <g transform="translate({cx}, 145)">')
        svg.append(f'    <text x="0" y="0" font-family="monospace" font-size="11" font-weight="900" fill="{lbl_color}" text-anchor="middle">km {cp["km_tot"]}</text>')
        # ETA timestamp with clock icon
        svg.append('    <g transform="translate(0, 16)">')
        svg.append('      <circle cx="-25" cy="-3.5" r="4.5" fill="none" stroke="#64748b" stroke-width="1.2"/>')
        svg.append('      <polyline points="-25,-6 -25,-3.5 -23,-3.5" fill="none" stroke="#64748b" stroke-width="1.1"/>')
        svg.append(f'      <text x="-16" y="0" font-family="monospace" font-size="10" font-weight="700" fill="#64748b" text-anchor="start">{t_nom}</text>')
        svg.append('    </g>')
        # True landmarks only (Bredene P4 & Vosseslag)
        if cp_i == 0:
            svg.append('    <text x="0" y="-16" font-size="9.5" font-weight="800" fill="#0284c7" text-anchor="middle">Bredene P4 (Start)</text>')
        elif cp_i == 4:
            svg.append('    <text x="-6" y="-16" font-size="9" font-weight="800" fill="#ef4444" text-anchor="end">Vosseslag (Aankomst)</text>')
        elif cp_i == 5:
            svg.append('    <text x="6" y="-16" font-size="9" font-weight="800" fill="#ef4444" text-anchor="start">Vosseslag (Vertrek)</text>')
        elif cp_i == 9:
            svg.append('    <text x="0" y="-16" font-size="9.5" font-weight="800" fill="#0284c7" text-anchor="middle">Bredene P4 (Finish)</text>')
        svg.append('  </g>')

    # 6. Starttijd-Venster: Soft Green Envelope Band with Vertical Density Gradient
    svg.append('  <!-- ================= STARTTIJD-VENSTER (±30 MIN ENVELOPE BAND) ================= -->')
    svg.append(f'  <polygon points="{envelope["poly_env_heen"]}" fill="url(#envelopeGrad)" stroke="none"/>')
    svg.append(f'  <polygon points="{envelope["poly_env_terug"]}" fill="url(#envelopeGrad)" stroke="none"/>')
    svg.append(f'  <path d="{poly_to_path(envelope["env_heen_top"])}" fill="none" stroke="#10b981" stroke-width="1.0" stroke-dasharray="3,3" opacity="0.65"/>')
    svg.append(f'  <path d="{poly_to_path(envelope["env_heen_bot"])}" fill="none" stroke="#10b981" stroke-width="1.0" stroke-dasharray="3,3" opacity="0.65"/>')
    svg.append(f'  <path d="{poly_to_path(envelope["env_terug_top"])}" fill="none" stroke="#10b981" stroke-width="1.0" stroke-dasharray="3,3" opacity="0.65"/>')
    svg.append(f'  <path d="{poly_to_path(envelope["env_terug_bot"])}" fill="none" stroke="#10b981" stroke-width="1.0" stroke-dasharray="3,3" opacity="0.65"/>')

    # 7. Draw Isochrones (15-Minute Resolution)
    svg.append('  <!-- ================= ISOCHRONES (15-MIN RESOLUTION) ================= -->')
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
        if iso["has_turn_bridge"] and iso["py_turn"] is not None:
            y_br = iso["py_turn"]
            svg.append(f'    <line x1="{x_heen[4]}" y1="{y_br:.1f}" x2="{x_terug[0]}" y2="{y_br:.1f}" stroke="#94a3b8" stroke-width="1.2" stroke-dasharray="2,2"/>')
            if y_br > 218.0:
                svg.append(f'    <text x="{x_mid_turn}" y="{y_br - 4:.1f}" font-family="monospace" font-size="9" font-weight="800" fill="#475569" text-anchor="middle" paint-order="stroke" stroke="#ffffff" stroke-width="2.5">{iso["time"]}</text>')

        # Labels entering along first spine (Bredene P4, spine 0): placed inside plot to the right
        if len(iso["pts_h"]) > 1 and iso["pts_h"][0][0] <= x_heen[0] + 2 and y_spine_top <= iso["pts_h"][0][1] <= y_spine_bottom:
            p0 = iso["pts_h"][0]
            p1 = iso["pts_h"][min(5, len(iso["pts_h"])-1)]
            angle = float(np.degrees(np.arctan2(p1[1] - p0[1], p1[0] - p0[0])))
            svg.append(f'    <text x="{p0[0] + 10:.1f}" y="{p0[1] - 4:.1f}" font-family="monospace" font-size="8.5" font-weight="800" fill="#64748b" transform="rotate({angle:.1f} {p0[0]+10:.1f} {p0[1]-4:.1f})" paint-order="stroke" stroke="#ffffff" stroke-width="3">{iso["time"]}</text>')

        # Labels entering along bottom border (cleanly bounded)
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

    # 8. Draw Vertical Spines & Tidal Current Staven (Copernicus CMEMS authentic)
    svg.append('  <!-- ================= VERTICAL SPINES & CURRENT STAVEN ================= -->')
    for s_info in spine_data:
        cx = s_info["cx"]
        cp = s_info["checkpoint"]
        is_turn = cp["leg"] in ["out_turn", "ret_turn"]
        spine_col = "#ef4444" if is_turn else "#94a3b8"

        # Spine line
        svg.append(f'    <line x1="{cx}" y1="{y_spine_top}" x2="{cx}" y2="{y_spine_bottom}" stroke="{spine_col}" stroke-width="{1.8 if is_turn else 1.2}"/>')

        # Staven
        for b in s_info["bars"]:
            by = b["py"]
            u_fwd = b["u_fwd"]
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

            # Small spine tick
            svg.append(f'    <line x1="{cx - 2}" y1="{by:.1f}" x2="{cx + 2}" y2="{by:.1f}" stroke="#64748b" stroke-width="1"/>')

    # 9. Draw 9 Isotachs (0.6 to 1.4 m/s)
    svg.append('  <!-- ================= 9 ISOTACHS (CONTINUOUS SPEED FAN) ================= -->')
    for crv in curves:
        ph = poly_to_path(crv["pts_heen"])
        pt = poly_to_path(crv["pts_terug"])
        svg.append(f'    <path d="{ph}" fill="none" stroke="{crv["color"]}" stroke-width="{crv["lw"]}" stroke-linecap="round" opacity="{crv["opacity"]}"/>')
        svg.append(f'    <path d="{pt}" fill="none" stroke="{crv["color"]}" stroke-width="{crv["lw"]}" stroke-linecap="round" opacity="{crv["opacity"]}"/>')

    # 10. Finish Table on Right Margin
    svg.append('  <!-- ================= FINISH TABLE (v vs Delta t) ================= -->')
    x_tbl_v = x_terug[-1] + 32.0   # 1217.0
    x_tbl_dt = x_tbl_v + 58.0      # 1275.0
    y_tbl_head = 148.0

    svg.append('  <g id="finish_table">')
    svg.append(f'    <text x="{x_tbl_v}" y="{y_tbl_head:.1f}" font-size="10.5" font-weight="900" fill="#0f172a">v (m/s)</text>')
    svg.append(f'    <text x="{x_tbl_dt}" y="{y_tbl_head:.1f}" font-size="10.5" font-weight="900" fill="#0f172a">Δt (min)</text>')
    svg.append(f'    <line x1="{x_tbl_v - 5}" y1="{y_tbl_head + 5:.1f}" x2="{x_tbl_dt + 45}" y2="{y_tbl_head + 5:.1f}" stroke="#cbd5e1" stroke-width="1.0"/>')

    for crv, sp_info in zip(curves, speeds_analyzed):
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

    # 11. 8 Schalingsbalken (Bottom Ribbon)
    svg.append('  <!-- ================= 8 SCHALINGSBALKEN (BOTTOM RIBBON) ================= -->')
    y_ribbon = 818.0
    w_box = 115.0
    h_box = 48.0

    for k, leg in enumerate(leg_breakdown):
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

        # Leader line down from matrix
        svg.append(f'    <line x1="{x_mid_leg}" y1="{y_spine_bottom}" x2="{x_mid_leg}" y2="{y_ribbon}" stroke="#cbd5e1" stroke-width="0.9" stroke-dasharray="2,2"/>')

        # Card container
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
            # Tailwind (Meestroom): Swimmer covers Dw < 750m, current bridges to 750m tick
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
            # Headwind (Tegenstroom): Swimmer covers Dw > 750m, current subtracts back to 750m tick
            W_total = 85.0
            x_tick = x_trk + W_total * (750.0 / d_w)
            w_w = W_total
            w_u = (x_trk + W_total) - x_tick

            svg.append(f'      <rect x="{x_trk:.1f}" y="{y_trk}" width="{w_w:.1f}" height="{h_trk}" rx="2" fill="#e2e8f0"/>')
            svg.append(f'      <rect x="{x_trk:.1f}" y="{y_trk}" width="{w_w:.1f}" height="{h_trk}" rx="2" fill="#16a34a"/>')
            svg.append(f'      <rect x="{x_tick:.1f}" y="{y_trk}" width="{w_u:.1f}" height="{h_trk}" rx="2" fill="{cur_col}" fill-opacity="0.6"/>')
            if k >= 4:
                svg.append(f'      <rect x="{x_tick:.1f}" y="{y_trk}" width="{w_u:.1f}" height="{h_trk}" rx="2" fill="url(#whiteCrossHatch)"/>')
            # Leftward white arrow showing opposing current pushing back to 750m tick
            svg.append(f'      <polygon points="{x_tick + w_u - 2:.1f},{y_trk + 2.5} {x_tick + 2:.1f},{y_trk + 5.5} {x_tick + w_u - 2:.1f},{y_trk + 8.5}" fill="#ffffff" opacity="0.95"/>')
            cur_str = f"{int(round(d_u))}m"

        # Explicit black tick mark at EXACT 750m target distance
        svg.append(f'      <line x1="{x_tick:.1f}" y1="{y_trk - 3}" x2="{x_tick:.1f}" y2="{y_trk + h_trk + 3}" stroke="#0f172a" stroke-width="2.0"/>')

        # Numerical label row 1: distance breakdown
        svg.append(f'      <text x="{w_box/2:.1f}" y="29" font-family="monospace" font-size="8.5" font-weight="800" text-anchor="middle"><tspan fill="#16a34a">{int(round(d_w))}m</tspan> <tspan fill="{cur_col}">{cur_str}</tspan></text>')
        # Numerical label row 2: current speed & leg time
        svg.append(f'      <text x="{w_box/2:.1f}" y="40" font-family="monospace" font-size="8" font-weight="700" fill="#64748b" text-anchor="middle">u = {u_avg:+.2f} m/s • {dt_min:.1f}\'</text>')
        svg.append('    </g>')

    # 12. Compact Single-Line Footer Legend
    svg.append('  <!-- ================= COMPACT SINGLE-LINE LEGEND ================= -->')
    y_leg = 890.0
    w_leg = 1330.0
    x_leg = (width - w_leg) / 2.0  # 45.0

    svg.append(f'  <g id="bottom_legend" transform="translate({x_leg:.1f}, {y_leg})">')
    svg.append(f'    <rect x="0" y="0" width="{w_leg}" height="44" rx="8" fill="#f8fafc" stroke="#cbd5e1" stroke-width="1.2" filter="url(#softShadow)"/>')

    # Item 1: Snelheid (9-color vector strip)
    svg.append('    <g transform="translate(18, 16)">')
    svg.append('      <text x="0" y="10" font-size="10.5" font-weight="900" fill="#0f172a">Snelheid:</text>')
    x_strip = 58.0
    for sp_i, sp_info in enumerate(speeds_analyzed):
        svg.append(f'      <rect x="{x_strip + sp_i*9}" y="2" width="9" height="10" fill="{sp_info["color"]}"/>')
    svg.append(f'      <text x="{x_strip + 88}" y="10" font-size="9.5" font-weight="700" fill="#ea580c">0.6</text>')
    svg.append(f'      <text x="{x_strip + 110}" y="10" font-size="10" font-weight="900" fill="#16a34a">1.0 [Nom]</text>')
    svg.append(f'      <text x="{x_strip + 168}" y="10" font-size="9.5" font-weight="700" fill="#2563eb">1.4 m/s</text>')
    svg.append('    </g>')

    # Item 2: Starttijd-venster
    svg.append('    <g transform="translate(325, 16)">')
    svg.append('      <rect x="0" y="2" width="22" height="12" fill="url(#envelopeGrad)"/>')
    svg.append('      <line x1="0" y1="2" x2="22" y2="2" stroke="#10b981" stroke-width="1.0" stroke-dasharray="2,2"/>')
    svg.append('      <line x1="0" y1="14" x2="22" y2="14" stroke="#10b981" stroke-width="1.0" stroke-dasharray="2,2"/>')
    svg.append('      <text x="30" y="10" font-size="10" font-weight="800" fill="#0f172a">Starttijd-venster: <tspan font-weight="600" fill="#64748b">±30 min marge</tspan></text>')
    svg.append('    </g>')

    # Item 3: Getijdestroming (Vloedstroom & Ebstroom)
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

    # Item 4: Isochronen
    svg.append('    <g transform="translate(980, 16)">')
    svg.append('      <line x1="0" y1="7" x2="24" y2="7" stroke="#94a3b8" stroke-width="1.2" stroke-dasharray="3,3"/>')
    svg.append('      <text x="32" y="10" font-size="10" font-weight="800" fill="#0f172a">Isochronen: <tspan font-weight="600" fill="#64748b">Lijnen gelijke tijd (15\')</tspan></text>')
    svg.append('    </g>')
    svg.append('  </g>')

    # 13. Subtitle Footer
    svg.append('  <!-- ================= FOOTER ================= -->')
    svg.append('  <g id="footer" transform="translate(45, 972)">')
    svg.append('    <text x="0" y="0" font-size="11" font-weight="600" fill="#94a3b8">CSCM • Dynamisch Kustzwem-Trajectmodel • Copernicus CMEMS 2D &amp; HIC KiWIS Operational Forecasts (25m Grid)</text>')
    svg.append(f'    <text x="{w_leg}" y="0" font-size="11" font-weight="800" fill="#94a3b8" text-anchor="end">ONTWERP v6 (A3 LIGGEND)</text>')
    svg.append('  </g>')

    svg.append('</svg>')

    rendered_svg = "\n".join(svg)
    with open(OUTPUT_SVG, "w", encoding="utf-8") as f:
        f.write(rendered_svg)
    print(f"Generated SVG: {OUTPUT_SVG}")

    try:
        subprocess.run(["rsvg-convert", "-w", "2000", str(OUTPUT_SVG), "-o", str(OUTPUT_PNG)], check=True)
        print(f"Generated PNG: {OUTPUT_PNG}")
    except Exception as e:
        print(f"Error converting to PNG via rsvg-convert: {e}")

    print("=" * 60)


if __name__ == "__main__":
    render()
