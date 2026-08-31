# cscm (Coastal Swimmer Crossing Module) 

Assists in Current Modeling & Trajectory Optimization for swimmers in the North Sea.

A tactical routing, tidal analysis, and trajectory optimization system designed specifically for ultra-distance open-water swimmers operating in highly dynamic, non-linear coastal current fields.

---

## 🎯 Project Goals

The ultimate objective of `cscm` is to solve **Zermelo's Navigation Problem** [85] for human athletes. In open-water swimming, currents can easily equal or exceed a swimmer's cruising speed. By vectorially combining localized tidal stream velocities with human endurance profiles, `cscm` computes the optimal steering angles (headings) over time to yield the fastest path from A to B.

### Major Milestones:
* **Short-Term (September 2026 - Active):** Validate the kinematics model to support a 6-hour experimental test swim in Koksijde, Belgium. Models will predict the exact trajectories of two alternative courses (316° at high tide vs. 333° at low tide) designed to safely clear the local Colruyt mussel farm.
* **Mid-Term (September 2027):** Deliver a tactical pacing, timing, and routing plan for a potential historic ultra-crossing. Factoring in swimmer fatigue models, based on results from actual swims by various people.
* **Long-Term (The "Waze for Swimmers" App):** Build a serverless, highly optimized web application where users can input start/end coordinates and instantly receive the optimal start time window and head-over-time routing strategy. This should involve the production of a tuned "cloud optimised" statistical model for the currents in the North Sea.

---

## 🏗️ Current Project State

The repository is organized under a modular Python package (`cscm`):

* **`cscm/model.py`:** Core domain kinematics representing coordinates, velocity vectors, swimmers, and the abstraction interfaces for trajectory calculation and pathfinders.
* **`cscm/moon/phases.py`:** High-precision astronomical moon phase and cycle calculations using NASA JPL ephemeris files via `skyfield`. It groups time into synodic months, establishing a baseline for the astronomical Spring/Neap tide cycle.
* **`cscm/current/cmems/retrieve.py`:** Robust data management layer that programmatically queries and downloads 1.5 km/15-minute resolution 2D hydrodynamic current forecast data from the Copernicus Marine Service (CMEMS). Downloads are dynamically partitioned into tidal-lag-safe lunar months with asymmetric margins (+5 days on the trailing end) to guarantee coverage of boundary spring tide lags.
* **`cscm/current/cmems/analyse.py`:** An adaptive spatial analysis engine. To operate globally across changing coastlines (from Belgium to the UK), it computes a localized Principal Component Analysis (PCA) on the velocity vectors ($U$, $V$) of *every single grid cell* over time. This automatically determines each cell's unique principal tidal flow axis, projects the 2D currents onto it, and uses linear sub-step interpolation to pinpoint exact slack water reversals and peak ebbs/floods.
* **`cscm/wellknown.py`:** Built-in configurations for notable coordinates (Koksijde, Nieuwpoort, Kingsgate, Orford Ness, Dover) and verified swimmer profiles (cruising paces, speed jitter, and headings).

---

## 🚀 Future Ambitions & Architecture

1. **Space-Time Trajectory Search ($x, y, t$):**
   Implement a Time-Dependent Space-Time A* (STA*) or 3D Dijkstra graph search. Because currents are primarily a function of time rather than small spatial deviations on the human scale, searching the $(latitude, longitude, epoch\_seconds)$ grid will yield mathematically optimal routing directions.

2. **Serverless Big Data Frontend:**
   To support a fast and cost-effective web app without heavy backend servers, tidal currents will be compressed into some goespatial and cloud-optimised format (parquet or zarr). The browser could then run DuckDB-Wasm, executing extremely efficient HTTP Range Requests to query only the precise geographic cells and time slices needed for the calculation of the swim.

3. **Harmonical Tidal Prediction (UTide):**
   Integrate the Python `UTide` package to perform harmonic analysis on historical Copernicus data. By resolving the amplitude and phase of dominant tidal constituents (e.g., $M_2, S_2$), the system will be capable of predicting tidal flows years into the future without relying on live Copernicus API forecast windows.

4. **Swimmer and Physiological Fatigue Decay Modeling:**
   Develop non-linear speed decay functions. While a swimmer might maintain a steady 3.6 km/h pace ($1.0 \text{ m/s}$) for 10 km, ultra-distances spanning 24 to 40 hours trigger immense physical toll, cold exposure, and sleep deprivation. Processing historical wearable data (Garmin/Polar FIT & TCX exports) will allow us to calibrate empirical fatigue models to accurately predict the late-stage speed decay down to the $2.5 \text{ -- } 2.8 \text{ km/h}$ range.

5. **Environmental impact analysis:** 
   Use additional environmental data (wind, waves, temperature, ...) to investigate possible other meaningful impact-factors on long distance swim performance. 

---

## 🛠️ Usage & Automated Workflows

The codebase is built with modern Python tooling (Poetry, xarray, geopandas). 

### Setup

Steps you like to get over with:
1. Install `poetry` - and then run `poetry install` on this project
2. Copy `dotenv-example`  to `.env` and add your personal settings there.


### Processing Copernicus Data:
To download/update the local CMEMS datastore and run the adaptive PCA current analysis on it to generate `_analysis.json` database files along with verification diagnostic plots:
```bash
poetry run python -m cscm.current.cmems
```
