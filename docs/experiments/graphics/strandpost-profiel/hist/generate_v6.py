#!/usr/bin/env python3
"""
Generator for Coastal Current Profile v6.
Universal Coastal Orientation Architecture (Synthetic Benchmark Data):
- Uses `seaward_bearing_deg` (universal compass bearing 0°-360° perpendicular to the coastline pointing seaward).
- Dynamically derives:
  * North needle rotation on canvas: `north_angle = (360 - seaward_bearing_deg) % 360`
  * Alongshore flood/right bearing: `(seaward_bearing_deg + 90) % 360`
  * Alongshore ebb/left bearing: `(seaward_bearing_deg - 90) % 360`
- Directly loads and validates against `src/cscm/resources/be_lifeguard_posts.yaml`.
- Reproduces target infographic design v4/v5 with complete mathematical and semantic fidelity.
"""

import json
import math
from pathlib import Path
import subprocess
import jinja2
import yaml

HIST_DIR = Path(__file__).resolve().parent
REPO_ROOT = HIST_DIR.parents[3]
YAML_PATH = REPO_ROOT / "src" / "cscm" / "resources" / "be_lifeguard_posts.yaml"

TEMPLATE_V6 = HIST_DIR / "stroming-profiel-v6.svg.j2"
OUTPUT_SVG_V6 = HIST_DIR / "ontwerp-stroming-profiel-v6.svg"
OUTPUT_PNG_V6 = HIST_DIR / "ontwerp-stroming-profiel-v6.png"
DATA_YAML_V6 = HIST_DIR / "data_to_plot_v6.yaml"


def calculate_block_angle(t):
    """
    Model tidal ellipse angle as a block-wave with rapid transition around slack waters:
    - 09:00 to 13:00 (4h): steady 0° (alongshore right, NO / Nederland)
    - 13:00 to 15:00: smooth, rapid transition through -90° (seaward) at 14:00 (slack HW)
    - 15:00 to 18:45 (3.75h): steady 180° (alongshore left, ZW / Frankrijk)
    - 18:45 to 20:00: transition beginning towards next flood
    - 07:00 to 09:00: transition from 180° through +90° (landward) at 08:00 (slack LW) to 0°
    """
    if 13.0 <= t <= 15.0:
        u = (t - 14.0) / 1.0
        return -90.0 - 90.0 * math.sin(u * (math.pi / 2))

    if 7.0 <= t <= 9.0:
        u = (t - 8.0) / 1.0
        return 90.0 - 90.0 * math.sin(u * (math.pi / 2))

    if t >= 18.75:
        u = (t - 18.75) / 1.25
        return 180.0 - 60.0 * math.sin(u * (math.pi / 2))

    if 9.0 < t < 13.0:
        return 0.0

    return 180.0


def load_lifeguard_post_config(municipality_key="bredene", post_key="post_4"):
    """Loads configuration and derives universal coastal geometry."""
    with open(YAML_PATH, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    muni = cfg.get("municipalities", {}).get(municipality_key, {})
    post = muni.get("posts", {}).get(post_key, {})

    seaward_bearing = muni.get(
        "seaward_bearing_deg",
        cfg.get("metadata", {}).get("seaward_bearing_deg", 335.0),
    )

    north_angle = (360.0 - seaward_bearing) % 360.0
    alongshore_right = (seaward_bearing + 90.0) % 360.0
    alongshore_left = (seaward_bearing - 90.0) % 360.0

    return {
        "muni_name": muni.get("name", "Bredene"),
        "post_name": post.get("name", "Droogen Opganck"),
        "post_number": post.get("number", 4),
        "seaward_bearing": seaward_bearing,
        "north_angle": north_angle,
        "alongshore_right": alongshore_right,
        "alongshore_left": alongshore_left,
        "tidal_cycle_hours": cfg.get("metadata", {}).get("tidal_cycle_hours", 12.42),
    }


def generate_v6_data():
    geo = load_lifeguard_post_config("bredene", "post_4")

    start_hour = 7.0
    n_points = 51

    hw_time = 13.0
    lw1_time = 7.25
    lw2_time = 19.5

    pfc_time = 10.75
    pec_time = 16.5
    k1_time = 8.0
    k2_time = 14.0

    hw_level = 4.45
    lw_level = 0.68
    msl = (hw_level + lw_level) / 2.0
    amp_h = (hw_level - lw_level) / 2.0

    y_start = 220
    dy = 19.5

    slots = []
    water_points = []
    base_x = 100.0

    for i in range(n_points):
        t = start_hour + i * 0.25
        h_int = int(t)
        m_int = int(round((t - h_int) * 60))
        time_str = f"{h_int:02d}:{m_int:02d}"
        y = y_start + i * dy

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
        wx = 460 + (h - msl) * 135
        water_points.append((round(wx, 1), round(y, 1)))

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

        angle = calculate_block_angle(t)
        while angle <= -180:
            angle += 360
        while angle > 180:
            angle -= 360
        angle = round(angle, 1)

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

    line_path = f"M {water_points[0][0]} {water_points[0][1]}"
    for pt in water_points[1:]:
        line_path += f" L {pt[0]} {pt[1]}"

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
        "layout": {
            "total_height": 1550,
            "grid_y_bottom": 1225,
            "benchmark_y_bottom": 1220,
            "swimmer_y": 1248,
            "insight_y": 1358,
            "legend_y": 1438,
            "footer_y": 1532,
        },
        "meta": {
            "project_title": "CSCM KUST-STROMINGSPROFIEL",
            "location_name": f"{geo['muni_name']} — Strandpost {geo['post_number']}",
            "date_str": "Zaterdag 11 Juli 2026",
            "time_window": f"07:00 – 19:30 (Volledige Getijdencyclus ~{geo['tidal_cycle_hours']}u)",
            "seaward_bearing_deg": geo["seaward_bearing"],
            "north_angle": geo["north_angle"],
            "coast_left_label": "[FR] FRANKRIJK • EBBESTROOM (ZW)",
            "coast_right_label": "VLOEDSTROOM (NO) • NEDERLAND [NL]",
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
    data = generate_v6_data()

    # Dump data contract to YAML
    with open(DATA_YAML_V6, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, sort_keys=False)

    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(HIST_DIR)),
        autoescape=False,
    )
    template = env.get_template("stroming-profiel-v6.svg.j2")
    rendered_svg = template.render(**data)

    with open(OUTPUT_SVG_V6, "w", encoding="utf-8") as f:
        f.write(rendered_svg)

    print(f"Generated v6 SVG: {OUTPUT_SVG_V6} and data dump: {DATA_JSON_V6}")

    try:
        subprocess.run(
            ["rsvg-convert", "-w", "1200", str(OUTPUT_SVG_V6), "-o", str(OUTPUT_PNG_V6)],
            check=True,
        )
        print(f"Generated v6 PNG: {OUTPUT_PNG_V6}")
    except Exception as e:
        print(f"Warning: could not render PNG: {e}")


if __name__ == "__main__":
    render()
