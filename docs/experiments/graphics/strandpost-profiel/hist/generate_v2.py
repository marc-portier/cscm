#!/usr/bin/env python3
"""
Generator for Coastal Current Profile v2.
Incorporates all user feedback:
- 12.42-hour tidal cycle (~51 points at 15-minute resolution)
- Centered header & badges
- Horizontal coastline in compass rosette, rotated North needle
- Strictly horizontal bar lengths + rotating vector arrow in the circles (tidal ellipse)
- 15-min quarter-hour tick circles + full HH:MM badges only on key tidal events
- Swimmer pace inset box (0.5 m/s beginner, 1.0 m/s amateur, 1.5 m/s olympic)
- Opaque background, balanced layout
"""

import math
from pathlib import Path
import jinja2

BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_V2 = BASE_DIR / "stroming-profiel-v2.svg.j2"
OUTPUT_SVG = BASE_DIR / "ontwerp-stroming-profiel-v2.svg"
OUTPUT_PNG = BASE_DIR / "ontwerp-stroming-profiel-v2.png"

def generate_tidal_cycle_data():
    """
    Generate realistic 12.42-hour tidal data for Bredene (06:30 to 19:00).
    51 timestamps (every 15 min).
    Models water level (TAW), alongshore current (v_along), cross-shore current (u_cross),
    and true flow angle.
    """
    start_hour = 6.5  # 06:30
    n_points = 51     # 51 * 15 min = 12.5 hours -> until 19:00
    y_start = 220
    dy = 19           # 19 pixels per 15-min step -> ~950 px data height

    slots = []
    water_points = []

    # Timing parameters for the cycle:
    # 07:45 - Low Water 1 (LW1): 0.85 m TAW
    # 08:30 - Slack water (Kentering naar Vloed): v ~ 0
    # 10:45 - Peak Flood Current (PFC): +1.72 m/s (2h15 before HW!)
    # 13:00 - High Water (HW): 4.55 m TAW, v ~ +0.35 m/s
    # 14:00 - Slack water (Kentering naar Eb): v = 0.0 m/s (1h after HW)
    # 16:15 - Peak Ebb Current (PEC): -1.54 m/s (2h15 after HW!)
    # 18:45 - Low Water 2 (LW2): 0.90 m TAW, v ~ -0.30 m/s

    for i in range(n_points):
        t_hour = start_hour + (i * 0.25)
        h_int = int(t_hour)
        m_int = int(round((t_hour - h_int) * 60))
        time_str = f"{h_int:02d}:{m_int:02d}"
        y = y_start + (i * dy)

        # Progress within cycle (0 to 2*pi)
        phase = ((t_hour - 7.75) / 12.42) * 2 * math.pi

        # Water level model (semi-diurnal + shallow water distortion)
        # HW around phase = pi (13.0 h), LW around phase = 0 and 2*pi (7.75 h, 20.17 h)
        h_taw = 2.65 - 1.85 * math.cos(phase) + 0.35 * math.cos(2 * phase - 0.4)
        h_taw = round(h_taw, 2)

        # Alongshore velocity model (m/s):
        # Flood peak at phase ~ 0.7*pi (10.75 h = 10:45), zero at ~ 14.0 h (phase ~ 1.05*pi)
        # Asymmetric flood/ebb profile
        v_along = 1.68 * math.sin(phase + 0.6) - 0.25 * math.sin(2 * phase)
        # Clamp & fine tune key points:
        if time_str == "10:45":
            v_along = 1.72
        elif time_str == "14:00":
            v_along = 0.00
        elif time_str == "16:15":
            v_along = -1.54
        elif time_str == "08:15":
            v_along = 0.05
        elif time_str == "13:00":
            v_along = 0.35

        v_along = round(v_along, 2)

        # Cross-shore velocity (elliptical rotation, cyclonic during turnaround):
        # When reversing from flood to ebb, water turns seaward (North/NNW)
        if abs(v_along) < 0.25:
            # During slack water, flow turns seaward (negative cross-shore = offshore)
            u_cross = 0.18
        else:
            u_cross = 0.08 * math.cos(phase)

        # Calculate flow angle in degrees relative to the horizontal coastline:
        # Alongshore to the right (NO / Nederland) is 0°
        # Alongshore to the left (ZW / Frankrijk) is 180°
        # Straight up (zeewaarts / offshore) is -90° (in SVG coords where Y is down)
        if v_along >= 0.05:
            # Flood: generally pointing right, slightly towards sea or coast
            angle_deg = math.degrees(math.atan2(-u_cross, v_along))
        elif v_along <= -0.05:
            # Ebb: generally pointing left, slightly towards sea or coast
            angle_deg = math.degrees(math.atan2(-u_cross, v_along))
        else:
            # Kentering: turning towards sea (-90°)
            angle_deg = -90.0

        angle_deg = round(angle_deg, 1)

        # Classify key tidal milestones
        is_pfc = (time_str == "10:45")
        is_hw = (time_str == "13:00")
        is_kentering = (time_str == "14:00")
        is_pec = (time_str == "16:15")
        is_lw1 = (time_str == "07:45")
        is_lw2 = (time_str == "18:45")
        is_marked = is_pfc or is_hw or is_kentering or is_pec or is_lw1

        # Quarter-hour tick type for intermediate ticks:
        # 0 = :00 (full hour)
        # 1 = :15
        # 2 = :30
        # 3 = :45
        quarter_type = m_int // 15

        slots.append({
            "time": time_str,
            "hour_label": f"{h_int}h" if m_int == 0 else None,
            "minute": m_int,
            "quarter_type": quarter_type,
            "y": y,
            "v": v_along,
            "angle": angle_deg,
            "h_taw": h_taw,
            "is_pfc": is_pfc,
            "is_hw": is_hw,
            "is_kentering": is_kentering,
            "is_pec": is_pec,
            "is_lw": is_lw1 or is_lw2,
            "is_marked": is_marked,
        })

        # Scale water level to an X coordinate for the underlay curve:
        # Base spine right is 465, max HW (4.55m) reaches ~ X=760
        # Scale: 0m = 465, 5m = 790
        wx = 465 + (h_taw / 5.0) * 315
        water_points.append((round(wx, 1), y))

    # Construct SVG path for water curve
    # Smooth line through water_points
    line_path = f"M {water_points[0][0]} {water_points[0][1]}"
    for pt in water_points[1:]:
        line_path += f" L {pt[0]} {pt[1]}"

    # Area path closed against the center right spine (X=465)
    area_path = f"M 465 {water_points[0][1]} L {water_points[0][0]} {water_points[0][1]}"
    for pt in water_points[1:]:
        area_path += f" L {pt[0]} {pt[1]}"
    area_path += f" L 465 {water_points[-1][1]} Z"

    hw_pt = next(s for s in slots if s["is_hw"])
    hw_x = 465 + (hw_pt["h_taw"] / 5.0) * 315

    return {
        "meta": {
            "project_title": "CSCM KUST-STROMINGSPROFIEL",
            "location_name": "Bredene — Strandpost 4",
            "date_str": "Zaterdag 11 Juli 2026",
            "time_window": "06:30 – 19:00 (Volledige Getijdencyclus ~12.42u)",
            "north_angle": 25,  # North is ~25° clockwise relative to seaward normal
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
        },
        "insight": {
            "headline": 'Piek Vloedstroom (10:45) valt <tspan font-weight="800" fill="#ea580c">2u15 vóór Hoogwater (13:00)</tspan>!',
            "detail": "Bij Hoogwater (13:00) is de stroming al sterk verzwakt (0.35 m/s). De kentering (stilstaand water) valt om 14:00.",
        },
    }

def render():
    data = generate_tidal_cycle_data()
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(BASE_DIR)),
        autoescape=False,
    )
    template = env.get_template("stroming-profiel-v2.svg.j2")
    rendered_svg = template.render(**data)
    
    with open(OUTPUT_SVG, "w", encoding="utf-8") as f:
        f.write(rendered_svg)
    print(f"Generated SVG: {OUTPUT_SVG}")

if __name__ == "__main__":
    render()

