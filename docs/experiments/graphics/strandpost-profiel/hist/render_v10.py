#!/usr/bin/env python3
"""
Rendering Script for Coastal Current Profile v10.
Responsibility:
- Load data contract from `data_to_plot_v10.yaml`.
- Render Jinja2 SVG template `stroming-profiel-v10.svg.j2`.
- Export vector `ontwerp-stroming-profiel-v10.svg`.
- Convert with rsvg-convert to PNG `ontwerp-stroming-profiel-v10.png`.
"""

from pathlib import Path
import subprocess
import jinja2
import yaml

HIST_DIR = Path(__file__).resolve().parent

DATA_YAML_V10 = HIST_DIR / "data_to_plot_v10.yaml"
TEMPLATE_V10 = HIST_DIR / "stroming-profiel-v10.svg.j2"
OUTPUT_SVG_V10 = HIST_DIR / "ontwerp-stroming-profiel-v10.svg"
OUTPUT_PNG_V10 = HIST_DIR / "ontwerp-stroming-profiel-v10.png"


def render():
    if not DATA_YAML_V10.exists():
        print(f"Dataset {DATA_YAML_V10} not found, running fetch_data_v10 first...")
        from fetch_data_v10 import fetch_and_prepare_data
        data = fetch_and_prepare_data()
        with open(DATA_YAML_V10, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, sort_keys=False)
    else:
        with open(DATA_YAML_V10, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(HIST_DIR)),
        autoescape=False,
    )
    template = env.get_template("stroming-profiel-v10.svg.j2")
    rendered_svg = template.render(**data)

    with open(OUTPUT_SVG_V10, "w", encoding="utf-8") as f:
        f.write(rendered_svg)

    print(f"Generated v10 SVG: {OUTPUT_SVG_V10}")

    try:
        subprocess.run(
            ["rsvg-convert", "-w", "1200", str(OUTPUT_SVG_V10), "-o", str(OUTPUT_PNG_V10)],
            check=True,
        )
        print(f"Generated v10 PNG: {OUTPUT_PNG_V10}")
    except Exception as e:
        print(f"Warning: could not render PNG: {e}")


if __name__ == "__main__":
    render()
