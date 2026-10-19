---
name: graphics-experimenting
description: Workflow and structural conventions for iterative graphic and infographic development in experimenting/graphics/ using hist versioning, latest symlinks, YAML data contracts, and versions.md changelog.
---

# Graphics Experimenting Workflow & Conventions

This skill defines the directory layout, versioning discipline, and decoupled architecture for graphic prototyping and infographic design in `experimenting/graphics/`.

---

## 1. Directory Structure

Graphic initiatives are partitioned by design topic under `experimenting/graphics/<topic>/`:

```text
experimenting/graphics/<topic>/
├── hist/
│   ├── versions.md                        # Master changelog and design rationale
│   ├── fetch_data_v1.py                   # Data retrieval for v1
│   ├── render_v1.py                       # Rendering script for v1
│   ├── template-v1.svg.j2                 # Jinja2 vector template for v1
│   ├── data_to_plot_v1.yaml               # Extracted YAML data contract for v1
│   ├── ontwerp-<topic>-v1.svg             # Generated vector output
│   ├── ontwerp-<topic>-v1.png             # Converted raster preview
│   └── ...                                # Immutable previous versions (v2, v3, ...)
└── latest/
    ├── data_to_plot.yaml -> ../hist/data_to_plot_v<N>.yaml
    ├── fetch_data.py     -> ../hist/fetch_data_v<N>.py
    ├── render.py         -> ../hist/render_v<N>.py
    ├── template.svg.j2   -> ../hist/template-v<N>.svg.j2
    ├── ontwerp-<topic>.svg         -> ../hist/ontwerp-<topic>-v<N>.svg
    └── ontwerp-<topic>-preview.png -> ../hist/ontwerp-<topic>-v<N>.png
```

---

## 2. Decoupled Architecture: Data Retrieval vs. Rendering

Always separate data generation from visual rendering into distinct scripts:

### A. Data Retrieval (`fetch_data_v<N>.py`)
* Queries databases, NetCDF models, or REST APIs.
* Applies domain logic (e.g. coastal angle projections, grid classifications).
* Dumps the complete Jinja2 template context into **`data_to_plot_v<N>.yaml`**.
* **YAML is the preferred contract format** (clean human-readable diffs and inspection).

### B. SVG Rendering (`render_v<N>.py`)
* Reads strictly from `data_to_plot_v<N>.yaml`.
* Renders the Jinja2 template `template-v<N>.svg.j2`.
* Saves SVG output and invokes `rsvg-convert` to generate high-resolution PNG previews.

---

## 3. Versioning Rules

1. **Immutable History**: Never overwrite previous version numbers in `./hist/`. Every iteration receives an incremental version number (`v1`, `v2`, `v3`...).
2. **Document in `versions.md`**: Update `hist/versions.md` with:
   - File manifest per version.
   - Core visual changes and physical/design rationale.
3. **Always Update `./latest` Symlinks**: The `./latest/` directory must always point to the most recent target version.

---

## 4. Scalable Canvas Geometry

* **Dynamic Layout**: When vertical axes depend on time windows (e.g. 07:30–20:30 vs 05:30–22:30), parameterize:
  - `layout.total_height` in `<svg viewBox="0 0 920 {{ layout.total_height }}">`
  - Vertical bottom positions of gridlines and benchmark lines.
  - Offsets of bottom cards (swimmer benchmark, insight box, legend, footer).
* **Prevent Overlaps**: Subordinate cards must compute vertical positions relative to `y_end = y_start + (n_slots - 1) * dy`.
