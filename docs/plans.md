# CSCM Roadmap & Engineering Plans

This document outlines the ordered development roadmap for the **Channel Swimmer Crossing Module (CSCM)**. It anchors technical development to an operational monthly calendar.

---

## 🗓️ Operational Development Timeline

| Timeline | Milestone & Focus | Key Deliverables |
| :--- | :--- | :--- |
| **Oct 2026** | **Stabilization & Clean Core** | Refactoring, code cleanup, unified CLI & logging, automated `pytest` test harness with synthetic fixtures. |
| **Nov – Dec 2026** | **CMEMS Analysis & Empirical Validation** | Extensible spatial analysis pipeline, incremental cache, and retrofitting actual swim GPS tracks to isolate localized model residuals. |
| **Jan 2027** | **Tidal Synthesis Pipeline** | Construction of neutral, non-time-bound normalized 2D hydrodynamic tensors and metadata manifests for multi-year projections. |
| **Feb 2027** | **Harmonized `CurrentsModel` Subsystem** | Unified interface spanning historical archives, live forecast windows, and long-range synthesized fields with dynamic time-scaling. |
| **Mar 2027** | **Swimmer Kinematics & Fatigue Decay** | Empirical pace decay curves ($v(t)$), heading variance under fatigue and wave action, and relay team kinematics. |
| **Apr 2027** | **Spatiotemporal Trajectory Optimization** | Space-time graph search (`TrajectoryFinder`) to discover optimal departure windows and dynamic steering angles across lunar cycles. |
| **May 2027** | **Operational Campaign Automation** | Enhanced YAML job configurations and tuned automated briefing mailers tailored for recurring seasonal coastal swim operations. |
| **Jun – Sep 2027** | **Online Client-Side Planner (Prototype)** | First working draft of a cloud-native, browser-based routing tool powered by DuckDB-Wasm and compressed data formats. |

---

## Detailed Milestone Descriptions

### Milestone 1 (October 2026): Stabilization, Refactoring & Test Harness

* **1.1 Catalog-Based NetCDF Selector**:
  * Refactor `get_latest_forecast_nc` in `predict.py` to query `CMEMSDataManager.catalog` for exact date range overlaps (`data_start_dt` / `data_end_dt`), unlocking historical simulations and offline test suites.
* **1.2 Code Convergence & Shared Infrastructure**:
  * Unify the historically separate code paths (`model.py`, `current/cmems`, and `simulation`).
  * Introduce a shared `cscm.cli` / `cscm.config` module for common arguments (`--log-level`, `--data-dir`, `--config`) and standardized logging to both stdout and [cscm.log](file:///home/marc.portier@vliz.be/projects/mpo/cscm/cscm.log).
  * Refactor `CmemsForecastCurrentsModel` to implement the abstract [CurrentsModel](file:///home/marc.portier@vliz.be/projects/mpo/cscm/src/cscm/model.py#L264) interface.
  * Refactor `simulate_test_swim` to run through [TrajectoryCalculator](file:///home/marc.portier@vliz.be/projects/mpo/cscm/src/cscm/model.py#L343) driving a concrete [Swimmer](file:///home/marc.portier@vliz.be/projects/mpo/cscm/src/cscm/model.py#L204) instance.
* **1.3 Automated Test Suite**:
  * Establish a robust `pytest` suite under `tests/`:
    * Vector algebra, coordinate translations, heading trigonometry, WKT geometry loaders, and YAML job schema validation.
    * Algorithmic validation of `find_daily_tide_peaks` dead-time filtering against synthesized velocity signals.
    * Mock hydrodynamics: a lightweight synthetic NetCDF fixture to test spatio-temporal bilinear interpolation without loading heavy data files.

---

### Milestone 2 (November – December 2026): CMEMS Analysis & Empirical Validation

* **2.1 Extensible Analysis Pipeline**:
  * Restructure `analyse.py` into a modular, task-based engine where new physical diagnostics can be registered as discrete pipeline steps.
  * Support granular CLI flags and YAML configurations to enable or disable specific analysis passes selectively.
* **2.2 Incremental Analysis Cache**:
  * Implement hash-based caching (NetCDF file hash/mtime + cellid + parameter signature) to allow sparse cell analysis (ie target focal points only) and skip recalculating unchanged grid cells and lunar cycles.
* **2.3 Hydrodynamic Insight & Sanity Checks**:
  * Map spatial progression of the spring tide lag (tidal age) across coastal and shelf waters for the analysed region.
  * Better time analysis (alternatives, sine - or at least period - time fitting verification, ...) and extended detection types: not only PFC and PEC but also ZRO 'zero' (mid-cycle crossings, note: maybe best interpolated between the max, as detection in the data suffers from noise near zero), and classification of those moments into subgroups Z2F and Z2E (zero-to-flood vs zero-to-ebb). 
  * Visualize age and tidal progression timings in the geographic region of interest. Relate it to time of the moon cycles (neap-spring extremes), tidal extremes (peak currents) and local landmarks. Make it an animated visualization, not just images.
  * Quantify shoreline friction decay, shallow-water sandbank accelerations, and slack water reversal stability relative to the nearest coast.
  * Validate velocity time series against coastal tide gauge networks.
* **2.4 Empirical Swim Data Retrofitting**:
  * Ingest real-world GPX tracks and sensor logs from completed experimental swims.
  * Overlay observed drift against predicted trajectory vectors to isolate and quantify localized hydrodynamic discrepancies in the 1.5 km model.

---

### Milestone 3 (January 2027): Tidal Synthesis Pipeline (Neutral Normalized Model)

* **3.1 Overcoming the 7-Day Forecast Horizon**:
  * CMEMS provides high-accuracy 7-day operational forecasts, but long-range campaign planning requires projections months or years in advance.
  * Because tidal hydrodynamics are deterministically driven by celestial mechanics, historical archives can be synthesized into a canonical, normalized tidal dataset.
* **3.2 Dual-Phase Normalization**:
  * Map linear time $t$ into a two-dimensional astronomical phase space:
    1. Semi-diurnal tidal phase: $\phi_{\text{tide}} \in [0, 2\pi)$ (principal lunar period $M_2 \approx 12.4206\text{h}$).
    2. Synodic lunar cycle phase: $\phi_{\text{moon}} \in [0, 2\pi)$ (spring-neap envelope $\approx 29.5306\text{d}$).
  * Construct a normalized spatiotemporal velocity tensor:
    $$V_{\text{norm}}(x, y, \phi_{\text{tide}}, \phi_{\text{moon}})$$
* **3.3 Statistical Aggregations & Envelopes**:
  * Compute the median flow field representing the astronomical baseline decoupled from weather events.
  * Derive conservative percentile envelopes (p10 / p90) to capture adverse headcurrents versus favorable tailcurrent variations.
* **3.4 Custom Synthetic NetCDF Production**:
  * Export standardized, self-describing NetCDF files and accompanying metadata manifests for long-range planning.

---

### Milestone 4 (February 2027): Harmonized `CurrentsModel` Subsystem

* **4.1 Unified Currents Interface**:
  * Extend [CurrentsModel](file:///home/marc.portier@vliz.be/projects/mpo/cscm/src/cscm/model.py#L264) to intelligently resolve and serve current vectors across three distinct data tiers:
    1. *Historical Data*: Stored multi-month CMEMS NetCDF archives.
    2. *Near-Term Operational Forecast*: Live 7-day CMEMS forecast datasets.
    3. *Long-Term Synthesized Model*: Normalized astronomical tensors re-scaled to arbitrary future target dates.
* **4.2 Dynamic Time-Scaling Engine**:
  * Query `skyfield` ephemerides to calculate exact lunar phase alignment for any selected target date.
  * Dynamically project the normalized synthetic model onto real-world calendar time, allowing seamless trajectory calculations years ahead of time.
  * Start producing a cache of json files with the core results of skyfield data to be retrieved easily (e.g. for every month, several years ahead). This cache can be used in analyse and in the trajectory calculator for synthesised data. In future it can also be made available as ready to use data for other programs or services. (like the waze browser planned)
 * **4.3 Side track -- combine and optimize this subsystem within the simulation module**:
  * Automatically select and adjust the data from the correct (historic-to-distant future) nc file, dynamically based on the simulation's start datetime and the forecast horizon (7 days) or actual date (for historical or future planning).
  * allow simulations to run over boundaries in said nc files (progress to the next)
  * Make the current simulation system work with that.
  * Investigate optimal interpolation strategies in time (in between the 15' sample interval and accross transitioned nc files using the skyfield data to decide where to transition) and space (between grid cells) and make an implementation decision. Add an easy switch (e.g. via config) to toggle between strategies.

---

### Milestone 5 (March 2027): Advanced Swimmer Kinematics & Fatigue Modeling

* **5.1 Wearable Sensor Data Ingestion (`cscm.swimmer`)**:
  * Parse and process smartwatch activity files (Garmin FIT and Polar TCX) from long-distance training sessions.
  * Extract empirical stroke rate, heart rate, and speed metrics across varying durations and sea temperatures.
* **5.2 Non-Linear Fatigue Modeling**:
  * Implement concrete behavioral functions in [MovingObject](file:///home/marc.portier@vliz.be/projects/mpo/cscm/src/cscm/model.py#L105):
    * `calculate_proper_speed_mps`: Non-linear speed decay curve ($v(t) = v_0 \cdot f(\text{fatigue}, \text{temperature})$).
    * `calculate_proper_direction_deviation`: Model heading variance and steering drift induced by physical exhaustion, cross-seas, and wind chop.
* **5.3 Relay Team Kinematics (`RelaySwimmerTeam`)**:
  * Model multi-swimmer team rotations: sequential swimmer stints, individual fatigue curves, and handover transition intervals.

---

### Milestone 6 (April 2027): Spatiotemporal Trajectory Optimization

* **6.1 Formalizing Zermelo's Problem in Space-Time ($x, y, t$)**:
  * Complete [TrajectoryFinder](file:///home/marc.portier@vliz.be/projects/mpo/cscm/src/cscm/model.py#L390) using Time-Dependent Space-Time A* (STA*) or dynamic programming over a discrete $(latitude, longitude, epoch\_time)$ graph.
* **6.2 Optimal Start Window & Course Optimization**:
  * Given a specific swimmer profile and an arbitrary origin/destination pair:
    * Scan the lunar cycle to identify optimal departure time windows ($t_0$) maximizing favorable tidal assist in order to minimise for total swim time (not neccessarily shortest distance)
    * Compute time-varying steering headings $\theta(t)$ to achieve minimal crossing duration or safe clearance around obstacles.
    * Allow for enforced on-boat interrupts for crossing shipping lanes. 
* **6.3 Perform a 'stability' analysis for the found optimal courses/timings**: 
  * How much does the optimal timing change (days/hours) if any of a number of parameters change? e.g.
    * the swimmer speed deviates by +/- 0.1 m/s? 
    * the decay/fatigue kicks in earlier
    * the feeding stops are taking more time than expected
    * environmental conditions (wind/waves) get more extreme
    * time of departure gets delayed by some delta
    * currents are not in the predicted "average" but one or more stddevs more extreme? 
    * etc.
    * any combination of the above
  * Visualise the results of this analysis e.g. as a "confidence interval" on the optimal timing or course (graph over time showing min/max allowed deviation)
  * Prioritize the parameters to keep a strict eye on not to miss the optimal window or drift too much off course.
  * Provide contingency strategies (other heading plans) to compensate.

---

### Milestone 7 (May 2027): Operational Campaign Automation

* **7.1 Tuned Coastal Job Configurations**:
  * Enhance YAML job definitions to support recurring, multi-swimmer tactical briefings for actual planned swims during the summer.
  * Support rapid parameterization for different swimmer speeds (e.g., $0.8\text{ – }1.2\text{ m/s}$) over varying course lengths (e.g., 15 km or 30 km coastal legs).
* **7.2 Automated Dispatch Engine**:
  * Tune HTML email briefings and GPX track attachments for recurring weekly operations (supporting 1–2 scheduled tactical briefings per week).
  * Consider web publishing as delivery modus (not exclusively the current email/gpx delivery way).

---

### Milestone 8 (June – September 2027): Online Client-Side Planner (Prototype)

* **8.1 Cloud-Native Hydrodynamic Data Store**:
  * Convert synthesized hydrodynamic NetCDF datasets into Zarr / GeoParquet formats partitioned for efficient HTTP Range Requests.
  * Publish via online platform for public use.
* **8.2 Browser-Side Routing Engine ("Waze for Swimmers")**:
  * Build a prototype serverless web interface.
  * Run trajectory search algorithms client-side in the browser using DuckDB-Wasm and WebAssembly, querying only necessary spatial cells and time slices on demand.
  * Publish this tool on the same online platform. Consider ease of use for non-technical users (e.g. make it easy to select the date, origin and destination, provide swimmer-profile, etc.)
