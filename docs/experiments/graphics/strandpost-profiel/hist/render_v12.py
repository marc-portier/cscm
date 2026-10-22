#!/usr/bin/env python3
"""
Rendering Script for Coastal Current Profile v12 (Multi-Station & Spring/Neap Comparison).

Responsibility:
- Load data contract from `data_to_plot_v<variant>.yaml` (12a, 12b, 12c, 12d).
- Render Jinja2 SVG template `stroming-profiel-v12.svg.j2`.
- Export vector `ontwerp-stroming-profiel-v<variant>.svg`.
- Convert with rsvg-convert to PNG `ontwerp-stroming-profiel-v<variant>.png`.
"""

import argparse
from pathlib import Path
import subprocess
import jinja2
import yaml

HIST_DIR = Path(__file__).resolve().parent
TEMPLATE_NAME = "stroming-profiel-v12.svg.j2"


def render_variant(variant_key: str):
    yaml_path = HIST_DIR / f"data_to_plot_v{variant_key}.yaml"
    if not yaml_path.exists():
        print(f"Data file {yaml_path} not found. Running fetch_data_v12 first...")
        from fetch_data_v12 import fetch_and_prepare_variant
        fetch_and_prepare_variant(variant_key)

    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(HIST_DIR)),
        autoescape=False,
    )
    template = env.get_template(TEMPLATE_NAME)
    rendered_svg = template.render(**data)

    svg_out = HIST_DIR / f"ontwerp-stroming-profiel-v{variant_key}.svg"
    png_out = HIST_DIR / f"ontwerp-stroming-profiel-v{variant_key}.png"

    with open(svg_out, "w", encoding="utf-8") as f:
        f.write(rendered_svg)
    print(f"Generated v{variant_key} SVG: {svg_out}")

    try:
        subprocess.run(
            ["rsvg-convert", "-w", "1200", str(svg_out), "-o", str(png_out)],
            check=True,
        )
        print(f"Generated v{variant_key} PNG: {png_out}")
    except Exception as e:
        print(f"Warning: could not convert PNG for {variant_key}: {e}")


def main():
    parser = argparse.ArgumentParser(description="Render Coastal Current Profile v12 Suite")
    parser.add_argument("--variant", choices=["12a", "12b", "12c", "12d", "all"], default="all")
    args = parser.parse_args()

    targets = ["12a", "12b", "12c", "12d"] if args.variant == "all" else [args.variant]
    for key in targets:
        render_variant(key)


if __name__ == "__main__":
    main()
