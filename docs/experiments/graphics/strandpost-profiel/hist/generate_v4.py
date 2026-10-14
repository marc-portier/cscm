#!/usr/bin/env python3
"""
Generator for Coastal Current Profile v4.
Incorporates all user feedback for v4:
- Block-wave like angle transitions: steady 0° (flood) and 180° (ebb) for 4-5 hours,
  rapid linear/sinusoidal transition in the 1-2 hour window around slack water (kentering).
- True TAW 0m baseline (far left) for water level gradient:
  fills from left (0m TAW reference, near X=100) to the water level curve,
  simulating the actual water body filling and emptying.
- Callout markers placed EXACTLY on the curve extrema (no offset),
  dotted lines extend outward (right for HW, left for LW) with zero collision.
- Legend current vector bar shows the actual dual-colored bar (half purple, half blue)
  between the dual circles.
"""

import math
from pathlib import Path
import jinja2

BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_V4 = BASE_DIR / "stroming-profiel-v4.svg.j2"
OUTPUT_SVG_V4 = BASE_DIR / "ontwerp-stroming-profiel-v4.svg"
OUTPUT_PNG_V4 = BASE_DIR / "ontwerp-stroming-profiel-v4.png"

# Canonical active files
CANONICAL_SVG = BASE_DIR / "ontwerp-stroming-profiel.svg"
CANONICAL_PNG = BASE_DIR / "ontwerp-stroming-profiel-preview.png"

def calculate_block_angle(t):
    """
    Model tidal ellipse angle as a block-wave with rapid transition around slack waters:
    - 09:00 to 13:00 (4h): steady 0° (alongshore right, NO / Nederland)
    - 13:00 to 15:00: smooth, rapid transition through -90° (seaward) at 14:00 (slack HW)
    - 15:00 to 18:45 (3.75h): steady 180° (alongshore left, ZW / Frankrijk)
    - 18:45 to 20:00: transition beginning towards next flood
    - 07:00 to 09:00: transition from 180° through +90° (landward) at 08:00 (slack LW) to 0°
    """
    # 1. HW Slack transition window [13.0, 15.0]
    if 13.0 <= t <= 15.0:
        u = (t - 14.0) / 1.0  # -1 at 13.0, 0 at 14.0, +1 at 15.0
        # Smooth S-curve transition from 0° through -90° to -180° (180°)
        angle = -90.0 - 90.0 * math.sin(u * (math.pi / 2))
        return angle

    # 2. LW Slack transition window [7.0, 9.0]
    if 7.0 <= t <= 9.0:
        u = (t - 8.0) / 1.0  # -1 at 07:00, 0 at 08:00, +1 at 09:00
        angle = 90.0 - 90.0 * math.sin(u * (math.pi / 2))
        return angle

    # 3. Evening transition [18.75, 20.0]
    if t >= 18.75:
        u = (t - 18.75) / 1.25
        angle = 180.0 - 60.0 * math.sin(u * (math.pi / 2))
        return angle

    # 4. Steady Flood (09:00 to 13:00)
    if 9.0 < t < 13.0:
        return 0.0

    # 5. Steady Ebb (15:00 to 18.75)
    return 180.0

def generate_v4_data():
    start_hour = 7.0   # 07:00
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
    msl = (hw_level + lw_level) / 2.0   # 2.565 m TAW
    amp_h = (hw_level - lw_level) / 2.0  # 1.885 m

    y_start = 220
    dy = 19.5

    slots = []
    water_points = []
    base_x = 100.0  # 0m TAW reference baseline on the far left

    for i in range(n_points):
        t = start_hour + i * 0.25
        h_int = int(t)
        m_int = int(round((t - h_int) * 60))
        time_str = f"{h_int:02d}:{m_int:02d}"
        y = y_start + i * dy

        # 1. Mathematically pure water level curve h(t)
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

        # X position on the canvas:
        # MSL (2.565m) is at center X=460. Scale: 1m = 135 px
        # At HW (4.45m), deviation is +1.885m -> X = 460 + 1.885*135 = 704.5 (Right / Flood)
        # At LW (0.68m), deviation is -1.885m -> X = 460 - 1.885*135 = 195.5 (Left / Ebb)
        wx = 460 + (h - msl) * 135
        water_points.append((round(wx, 1), round(y, 1)))

        # 2. Smooth alongshore velocity v(t)
        if t < k1_time:
            phi = (k1_time - t) / 2.0 * (math.pi / 2)
            v = -1.52 * math.sin(phi)
        elif t <= k2_time:
            if t <= pfc_time:
                phi = (t - k1_time) / (pfc_time - k1_time) * (math.pi / 2)
                v = 1.68 * math.sin(phi)
            else:
                phi = (t - pfc_time) / (k2_time - pfc_time) * (math.pi / 2)
                v = 1.68 * math.cos(phi)
        else:
            if t <= pec_time:
                phi = (t - k2_time) / (pec_time - k2_time) * (math.pi / 2)
                v = -1.52 * math.sin(phi)
            else:
                phi = (t - pec_time) / 3.75 * (math.pi / 2)
                v = -1.52 * math.cos(phi)

        v = round(v, 2)

        # 3. Block-wave angle transition
        angle = calculate_block_angle(t)
        while angle <= -180:
            angle += 360
        while angle > 180:
            angle -= 360
        angle = round(angle, 1)

        # Flags
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

    # Line path for water curve
    line_path = f"M {water_points[0][0]} {water_points[0][1]}"
    for pt in water_points[1:]:
        line_path += f" L {pt[0]} {pt[1]}"

    # Area path: fills from far left baseline (base_x = 100) to the water curve!
    area_path = f"M {base_x} {water_points[0][1]} L {water_points[0][0]} {water_points[0][1]}"
    for pt in water_points[1:]:
        area_path += f" L {pt[0]} {pt[1]}"
    area_path += f" L {base_x} {water_points[-1][1]} Z"

    hw_pt = next(s for s in slots if s["is_hw"])
    lw1_pt = next(s for s in slots if s["is_lw1"])
    lw2_pt = next(s for s in slots if s["is_lw2"])

    hw_x = 460 + (hw_pt["h_taw"] - msl) * 135
    lw1_x = 460 + (lw1_pt["h_taw"] - msl) * 135
    lw2_x = 460 + (lw2_pt["h_taw"] - msl) * 135

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
    data = generate_v4_data()
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(BASE_DIR)),
        autoescape=False,
    )
    template = env.get_template("stroming-profiel-v4.svg.j2")
    rendered_svg = template.render(**data)

    with open(OUTPUT_SVG_V4, "w", encoding="utf-8") as f:
        f.write(rendered_svg)
    with open(CANONICAL_SVG, "w", encoding="utf-8") as f:
        f.write(rendered_svg)

    print(f"Generated v4 SVG: {OUTPUT_SVG_V4} and updated {CANONICAL_SVG}")

if __name__ == "__main__":
    render()
