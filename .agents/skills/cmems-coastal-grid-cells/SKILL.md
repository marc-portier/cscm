---
name: cmems-coastal-grid-cells
description: Policy and technical workflow for CMEMS hydrodynamic grid cell selection along the coast, avoiding boundary cell dampening and selecting full water cells for swim safety profiles.
---

# CMEMS Coastal Grid Cell Selection & Boundary Dampening Policy

This skill documents the methodology and best practices for selecting hydrodynamic grid cells along the Belgian coastline (and shallow seas) from Copernicus Marine (CMEMS 1.5km model) datasets.

---

## 1. The Coastal Boundary Dampening Problem

In CMEMS 1.5km hydrodynamic models (`cmems_mod_nws_phy-cur_anfc_1.5km-2D_PT15M-i_uo-vo_*`), grid cells directly touching the coastline suffer from **artificial numerical dampening**:
* **Intertidal averaging**: Model cells that span both shallow water and dry sand/dunes average velocities over the cell area.
* **Diagonal coastline rasterization**: Diagonal coastlines create jagged step-boundaries where lateral friction artificially slows down water transport.
* **Observed consequence**: Currents in boundary cells are often reported as **0.08 – 0.20 m/s**, even during spring tides when actual uninhibited coastal currents reach **1.0 – 1.2 m/s**.

Relying on boundary cells for beach safety leads to dangerous underestimations of current speed.

---

## 2. Grid Cell Classification

The module [`cscm.current.cmems.analyse`](file:///home/marc.portier@vliz.be/projects/mpo/cscm/src/cscm/current/cmems/analyse.py) provides the standardized classifier:

```python
from cscm.current.cmems.analyse import classify_grid_cells

# Returns status_mask: 0=Land, 1=Boundary, 2=Water
status_mask, is_boundary_mask = classify_grid_cells(ds)
```

| Status Code | Label | Definition | Usage Policy |
| :---: | :--- | :--- | :--- |
| **0** | **Land** | All timesteps are `NaN` or constant `0.0`. | Ignored / Inactive. |
| **1** | **Boundary (Kustcel)** | Wet cell with at least one adjacent (or diagonal) Land neighbor. | **Marked unusable** for direct beach safety current profiling without nearshore correction. |
| **2** | **Water (Open Zee)** | Pure wet cell with zero adjacent land neighbors. | **Active target** for coastal current profiling. |

---

## 3. Operational Selection Policy for Beach/Lifeguard Posts

When extracting currents for any coastal point (e.g. lifeguard post from `src/cscm/resources/be_lifeguard_posts.yaml`):

1. **Calculate distance** from the post `(lat, lon)` to all grid cells.
2. **Filter strictly** for cells where `status_mask == 2`.
3. **Select the nearest open-water cell**:
   - For Bredene Strandpost 4 (`51.2542, 2.9740`), the nearest full water cell is located at `51.2703, 2.9394` (~3,000 meters offshore).
4. **Safety justification**:
   - Swimmer safety infographics must reflect the true kinetic force of the coastal water body.
   - Using the first open-water cell yields realistic spring tide peak currents of **~1.05 m/s**, directly highlighting the hazard against the 1.0 m/s swimmer cruise speed benchmark.

---

## 4. Backlog & Future Improvements

* **Shoreline Extrapolation Model**: Develop a nearshore dissipation model (accounting for local bathymetry, shoaling, and bottom friction) to mathematically extrapolate from open water cells (status 2) to the breaker zone, rather than raw model boundary cells.
