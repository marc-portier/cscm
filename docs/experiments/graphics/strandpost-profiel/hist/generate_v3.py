#!/usr/bin/env python3
"""
Generator for Coastal Current Profile v3.
Incorporates all user feedback for v3:
- Fully realistic, mathematically sound 12.42-hour tidal cycle (07:00 to 19:30, 51 slots)
- Peak HW (13:00, 4.45 m TAW) coincides EXACTLY with maximum of water curve
- Low Water 1 (07:15, 0.68 m) and Low Water 2 (19:30, 0.68 m) coincide EXACTLY with minimums
- Symmetrical water curve: bulges right at HW (flood side) and bulges left at LW (ebb side)
- Symmetrical alongshore velocity curve:
  * Zero crossings (kentering) at 08:00 and 14:00
  * True mathematical peak at PFC (10:45, +1.68 m/s)
  * True mathematical peak at PEC (16:30, -1.52 m/s)
  * No hardcoded clamps or discontinuities
- Continuous, smooth counter-clockwise (cyclonic) tidal ellipse rotation
- Updated color system:
  * PFC is Blue (matching flood family)
  * PEC is Purple (matching ebb family)
  * HW is Amber/Yellow
  * LW is Orange
  * Kentering is Green
- Legend updated:
  * Current speed indicator has circles on BOTH ends (purple on left with arrow left, blue on right with arrow right)
  * Water curve in legend curves gently with gradient
"""

import math
from pathlib import Path
import jinja2

BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_V3 = BASE_DIR / "stroming-profiel-v3.svg.j2"
OUTPUT_SVG_V3 = BASE_DIR / "ontwerp-stroming-profiel-v3.svg"
OUTPUT_PNG_V3 = BASE_DIR / "ontwerp-stroming-profiel-v3.png"

# Canonical active files in graphics directory
CANONICAL_SVG = BASE_DIR / "ontwerp-stroming-profiel.svg"
CANONICAL_PNG = BASE_DIR / "ontwerp-stroming-profiel-preview.png"

def generate_v3_data():
    start_hour = 7.0   # 07:00
    end_hour = 19.5    # 19:30
    n_points = 51      # 51 points every 15 min (12.5h)

    hw_time = 13.0     # 13:00 (HW peak)
    lw1_time = 7.25    # 07:15 (LW1)
    lw2_time = 19.5    # 19:30 (LW2)

    pfc_time = 10.75   # 10:45 (PFC peak)
    pec_time = 16.5    # 16:30 (PEC peak)
    k1_time = 8.0      # 08:00 (Kentering 1: eb -> vloed)
    k2_time = 14.0     # 14:00 (Kentering 2: vloed -> eb)

    hw_level = 4.45    # m TAW
    lw_level = 0.68    # m TAW
    msl = (hw_level + lw_level) / 2.0  # 2.565 m TAW
    amp_h = (hw_level - lw_level) / 2.0 # 1.885 m

    y_start = 220
    dy = 19.5

    slots = []
    water_points = []

    for i in range(n_points):
        t = start_hour + i * 0.25
        h_int = int(t)
        m_int = int(round((t - h_int) * 60))
        time_str = f"{h_int:02d}:{m_int:02d}"
        y = y_start + i * dy

        # 1. Continuous, mathematically smooth water level h(t)
        if t <= hw_time:
            if t < lw1_time:
                phi = (lw1_time - t) / 6.5 * math.pi
                h = lw_level + amp_h * (1 - math.cos(phi)) * 0.1
            else:
                phi = (t - lw1_time) / (hw_time - lw1_time) * math.pi
                h = lw_level + amp_h * (1 - math.cos(phi))
        else:
            phi = (t - hw_time) / (lw2_time - hw_time) * math.pi
            h = hw_level - amp_h * (1 - math.cos(phi))

        h = round(h, 2)

        # Symmetrical water curve X coordinate:
        # MSL (2.565 m) is at center X=450
        # Scale: 1m = 135 px
        # At HW (4.45m), deviation is +1.885m -> X = 450 + 1.885*135 = 704.5 (Right / Flood)
        # At LW (0.68m), deviation is -1.885m -> X = 450 - 1.885*135 = 195.5 (Left / Ebb)
        wx = 450 + (h - msl) * 135
        water_points.append((round(wx, 1), round(y, 1)))

        # 2. Continuous, smooth alongshore current v(t)
        if t < k1_time:
            # Ebb tapering down to slack at 08:00
            phi = (k1_time - t) / 2.0 * (math.pi / 2)
            v = -1.52 * math.sin(phi)
        elif t <= k2_time:
            # Flood phase (08:00 to 14:00, duration 6.0h)
            if t <= pfc_time:
                phi = (t - k1_time) / (pfc_time - k1_time) * (math.pi / 2)
                v = 1.68 * math.sin(phi)
            else:
                phi = (t - pfc_time) / (k2_time - pfc_time) * (math.pi / 2)
                v = 1.68 * math.cos(phi)
        else:
            # Ebb phase (14:00 to 20.25h)
            if t <= pec_time:
                phi = (t - k2_time) / (pec_time - k2_time) * (math.pi / 2)
                v = -1.52 * math.sin(phi)
            else:
                phi = (t - pec_time) / 3.75 * (math.pi / 2)
                v = -1.52 * math.cos(phi)

        v = round(v, 2)

        # 3. Continuous counter-clockwise (cyclonic) tidal ellipse rotation angle
        # 0° = Right (NO / Nederland)
        # -90° = Up (Offshore / Seaward)
        # 180° = Left (ZW / Frankrijk)
        # +90° = Down (Onshore / Coastward)
        if t <= pfc_time:
            frac = (t - k1_time) / (pfc_time - k1_time)
            angle = 90.0 - frac * 90.0
        elif t <= k2_time:
            frac = (t - pfc_time) / (k2_time - pfc_time)
            angle = 0.0 - frac * 90.0
        elif t <= pec_time:
            frac = (t - k2_time) / (pec_time - k2_time)
            angle = -90.0 - frac * 90.0
        else:
            frac = (t - pec_time) / 3.75
            angle = 180.0 - frac * 90.0

        while angle <= -180:
            angle += 360
        while angle > 180:
            angle -= 360

        angle = round(angle, 1)

        # Key milestones
        is_pfc = (time_str == "10:45")
        is_hw = (time_str == "13:00")
        is_kentering1 = (time_str == "08:00")
        is_kentering2 = (time_str == "14:00")
        is_pec = (time_str == "16:30")
        is_lw1 = (time_str == "07:15")
        is_lw2 = (time_str == "19:30")

        slots.append({
            "time": time_str,
            "hour_label": f"{h_int}h" if m_int == 0 else None,
            "minute": m_int,
            "quarter_type": m_int // 15,
            "y": round(y, 1),
            "v": v,
            "angle": angle,
            "h_taw": h,
            "is_pfc": is_pfc,
            "is_hw": is_hw,
            "is_kentering": is_kentering1 or is_kentering2,
            "is_kentering1": is_kentering1,
            "is_kentering2": is_kentering2,
            "is_pec": is_pec,
            "is_lw1": is_lw1,
            "is_lw2": is_lw2,
            "is_lw": is_lw1 or is_lw2,
            "is_marked": is_pfc or is_hw or is_kentering1 or is_kentering2 or is_pec or is_lw1 or is_lw2,
        })

    # Build SVG path strings for water curve
    line_path = f"M {water_points[0][0]} {water_points[0][1]}"
    for pt in water_points[1:]:
        line_path += f" L {pt[0]} {pt[1]}"

    # Area path: from center X=450 through the points and back to center
    area_path = f"M 450 {water_points[0][1]} L {water_points[0][0]} {water_points[0][1]}"
    for pt in water_points[1:]:
        area_path += f" L {pt[0]} {pt[1]}"
    area_path += f" L 450 {water_points[-1][1]} Z"

    hw_pt = next(s for s in slots if s["is_hw"])
    lw1_pt = next(s for s in slots if s["is_lw1"])
    lw2_pt = next(s for s in slots if s["is_lw2"])

    hw_x = 450 + (hw_pt["h_taw"] - msl) * 135
    lw1_x = 450 + (lw1_pt["h_taw"] - msl) * 135
    lw2_x = 450 + (lw2_pt["h_taw"] - msl) * 135

    return {
        "meta": {
            "project_title": "CSCM KUST-STROMINGSPROFIEL",
            "location_name": "Bredene — Strandpost 4",
            "date_str": "Zaterdag 11 Juli 2026",
            "time_window": "07:00 – 19:30 (Volledige Getijdencyclus ~12.42u)",
            "north_angle": 25,
            "source_label": "CSCM • CMEMS 1.5km Model &amp; MDK Meetnet",
        },
        "slots": slots,
        "water_level": {
            "line_d": line_path,
            "area_d": area_path,
            "hw": {
                "x": round(hw_x, 1),
                "y": hw_pt["y"],
                "height": f"{hw_pt['h_taw']} m",
            },
            "lw1": {
                "x": round(lw1_x, 1),
                "y": lw1_pt["y"],
                "height": f"{lw1_pt['h_taw']} m",
            },
            "lw2": {
                "x": round(lw2_x, 1),
                "y": lw2_pt["y"],
                "height": f"{lw2_pt['h_taw']} m",
            },
        },
        "insight": {
            "headline": 'Piek Vloedstroom (10:45) valt <tspan font-weight="800" fill="#0284c7">2u15 vóór Hoogwater (13:00)</tspan>!',
            "detail": "Bij Hoogwater (13:00) is de vloedstroom al sterk verzwakt. De kentering naar eb (0.0 m/s) valt om 14:00.",
        },
    }

def render():
    data = generate_v3_data()
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(BASE_DIR)),
        autoescape=False,
    )
    template = env.get_template("stroming-profiel-v3.svg.j2")
    rendered_svg = template.render(**data)

    with open(OUTPUT_SVG_V3, "w", encoding="utf-8") as f:
        f.write(rendered_svg)
    with open(CANONICAL_SVG, "w", encoding="utf-8") as f:
        f.write(rendered_svg)

    print(f"Generated v3 SVG: {OUTPUT_SVG_V3} and updated {CANONICAL_SVG}")

if __name__ == "__main__":
    render()
