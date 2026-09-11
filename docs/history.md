# CSCM Project History & Evolution

## 1. Context & The Navigation Challenge

The **Channel Swimmer Crossing Module (CSCM)** was initiated to address a fundamental navigational problem in open-water athletics: **Zermelo's Navigation Problem** in dynamic, non-linear coastal current fields.

In regions like the North Sea and the English Channel:
* Tidal currents regularly reach speeds between $0.5\text{ m/s}$ and $2.7\text{ m/s}$ ($1.8\text{ – }9.7\text{ km/h}$).
* A swimmer's sustained cruising pace is typically around $1.0\text{ m/s}$ ($3.6\text{ km/h}$).

Because environmental flow speeds often equal or exceed the athlete's speed, traditional navigation heuristics break down. Calculating viable courses requires continuous vectorial combination of swimmer headings with localized, time-dependent hydrodynamic stream velocities.

```
Ground Velocity Vector:
V_effective(t) = V_swimmer(heading, speed) + V_current(lat, lon, t)
```

---

## 2. Evolution & Key Architectural Pivots

The project evolved through several distinct phases, moving from idealized mathematical models to operational hydrodynamic forecasting.

### Phase 1: Analytical Prototypes & Idealized Tidal Waves
Early experiments explored analytical approximations of tides:
* **Sinusoidal Approximation**: Implemented an idealized 12.42-hour semi-diurnal ($M_2$) sine wave with an angle parallel to the coast and an amplitude mildly grabbed from experience (and tuned to neap-time conditions)
* **Spatial Attenuation**: No distance-decay functions applied.
* **Findings**: Idealized sinusoidal models failed to capture coastal bathymetry, shallow-water friction, localized tidal phase lags, and meteorological storm surges. A physical, data-driven hydrodynamic approach was necessary.

---

### Phase 2: Copernicus Marine (CMEMS) Ingestion & Astronomical Partitioning
To obtain realistic spatiotemporal flow fields, the system transitioned to the **Copernicus Marine Service (CMEMS)** North-West European Shelf 2D hydrodynamic model (`cmems_mod_nws_phy-cur_anfc_1.5km-2D_PT15M-i`):
* **Resolution**: 1.5 km spatial grid cells at 15-minute temporal intervals, providing zonal ($u_o$, Eastward) and meridional ($v_o$, Northward) current vectors.
* **Astronomical Partitioning**: Rather than arbitrary calendar months, downloads are partitioned into synodic lunar months using NASA JPL DE421 ephemerides via `skyfield`.
* **Tidal Age Buffer**: Because peak spring tides typically lag the astronomical new/full moon by 1 to 3 days (the "age of the tide"), downloads include an asymmetric $+5$ day trailing window to guarantee complete coverage of spring tide extrema across boundaries.

---

### Phase 3: Tidal Ellipse Analysis vs. Operational Signed Peak Detection
Understanding when tidal currents reverse and reach peak velocity is critical for timing departures:
* **Concept introduction**: While regular land-humans typically only use the high/low water table as a reference, the swimmers, living in the water, just rise or drop with that water level. For them, not the water level, but the current is the main evironmental parameter to assess. For them timing events too should be based on current status. We have therefor introduced the terms PFC and PEC (Peak Flood Current and Peak Ebb Current) these typically appear 40 to 60 minutes ahead of the high/low water extremes.
* **Spatial PCA**: The system initially calculated localized Principal Component Analysis (PCA) on velocity vectors $(u_o, v_o)$ per grid cell to determine each cell's unique tidal ellipse major axis across varying coastlines.
* **Operational Pivot**: For the daily operational trajectory predictor, PCA orientation exhibited a 180° sign ambiguity along near-linear coastlines. The predictor was pivoted to a direct, physically robust signed velocity metric:
  $$v_{\text{parallel}} = \sqrt{u_o^2 + v_o^2} \times \text{sign}(u_o)$$
  * $u_o > 0$: Eastward flood flow (Peak Flood Current / PFC).
  * $u_o < 0$: Westward ebb flow (Peak Ebb Current / PEC).
* **Noise Suppression**: A 4-hour temporal dead-time filter was introduced to eliminate numerical noise in 15-minute model steps, preventing false double-peaks.
* **Validation**: Detected hydrodynamic peaks reliably precede coastal High/Low water tables by 40–60 minutes, matching regional hydrographic reality.

---

### Phase 4: Coastal Boundaries & Offshore Proxy Coordinates
When evaluating swimmer departures directly from the beach, early simulations encountered near-zero velocities or missing data:
* **Cause**: CMEMS 1.5 km grid cells intersecting the coastline often reflect land-masking or artificial boundary friction.
* **Validation**: Introduced explicit offshore proxy coordinates (offset ~1–2 km seaward) and verified dramatically more sensible and trustworthy current data and peak timing, compared to the noisy data at the immediate coast.
* **Solution**: Marked zero cells as landcells, and applied a straightforward nearest-cell marker to identify the partial land "boundary" cells, trusting the remainder cells as open sea cells. 
Swimmer departure calculations snap to these active hydrodynamic cells, preventing shoreline artifact distortion.

---

### Phase 5: Storage Optimization (>99% Reduction)
Initial spatial analyses exported full 15-minute time series for all grid cells across full lunar cycles, generating ~740 MB JSON files that degraded performance:
* **Solution**: Analysis storage was decoupled from raw hydrodynamic data. The NetCDF files serve as the authoritative raw store, while companion analysis JSON files store only lightweight calibration anchors (PCA angles, top 6 Spring/Neap peaks, lunar phase markers, and tidal lag).
* **Impact**: Reduced metadata file sizes from ~740 MB to under 500 KB per lunar cycle.
* **Backlog**: We realise more extensive data analysis is needed for a complete verification of the model, as well as for a gained insight into the real world environment in which all these calculations have to be performed.

---

### Phase 6: Operational Simulation & The "Visgraat" (Fishbone) Visualization
To support tactical planning and support boat crews, a declarative simulation engine and specialized nautical visualization were developed:
* **Declarative YAML Jobs**: Jobs define active dates, swimmer configurations, target bearings, durations, and automated peak detection windows.
* **Data-Driven Geometries**: Obstructions (e.g., aquaculture zones, shipping lanes) and coastal contours are ingested dynamically from WKT/CSV files rather than hardcoded definitions.
* **The "Visgraat" Layout**:
  * **Spine (Backbone)**: The dead-reckoning intended course along constant compass heading.
  * **Ribs (Graten)**: 15-minute tidal displacement vectors ($v_{\text{current}} \times 900\text{s}$) illustrating localized current drift at each stage.
  * **Offset Stencils**: Labels are offset both along-track and perpendicular to the spine, and rib labels sit opposite current deflection to guarantee zero text intersection.
* **Output Deliverables**: Automated generation of standard GPX navigation tracks and high-contrast cartographic overview plots, dispatched via automated notification reports.

---

### Phase 7: Autonomous Pipeline Hardening & Lunar Boundary Resilience
Operational cron execution on local and remote servers revealed edge cases at the boundaries of astronomical cycles and remote APIs:
* **The "Delete-Before-Download" Trap**: Ingestion previously deleted older forecast files before pulling updates. When upstream providers (CloudFerro S3 / CMEMS) experienced transient connection drops or 504 timeouts, the active file was lost, leaving only stale historical files and causing silent simulation skips (0 peaks detected).
* **Non-Destructive Staging & Retries**: Downloads now target an isolated `.staging/` directory with automated 3-attempt exponential backoff. Existing NetCDF and metadata files are preserved intact until the new download is verified and cataloged.
* **The Synodic Month Lookahead (35 vs. 29 Days)**: Because the synodic lunar period is ~29.53 days, a 29-day lookahead landed several hours short of the subsequent new moon when evaluated on the day of a new moon. Because cycle generation requires adjacent new moon pairs, the system was temporarily blind to the newly started cycle. Extending the lookahead to 35 days guarantees continuous, seamless discovery across new moon boundaries.
* **Trailing Buffer Saturation**: A cycle whose trailing margin has already fully downloaded (`data_end_dt >= nwmn_end_dt + 5 days`) is now recognized as saturated, eliminating redundant daily re-downloads of ~190 MB files whose date ranges cannot expand further.
* **Graceful Degradation with Cached Bulletins**: If remote updates fail after retries, simulations proceed using the latest available bulletin rather than halting, tagging the email with `[CMEMS Cache]` and explicitly displaying the date of the latest available data.
