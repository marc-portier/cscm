# cscm (Channel Swimmer Crossing Module) 

Assists in Current Modeling & Trajectory Optimization for swimmers in the North Sea.

A tactical routing, tidal analysis, and trajectory optimization system designed specifically for ultra-distance open-water swimmers operating in highly dynamic, non-linear coastal current fields.

---

## 🎯 Project Goals

The ultimate objective of `cscm` is to solve **Zermelo's Navigation Problem** for human athletes. In open-water swimming, currents can easily equal or exceed a swimmer's cruising speed. By vectorially combining localized tidal stream velocities with human endurance profiles, `cscm` computes the optimal steering angles (headings) over time to yield the fastest path from A to B.

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

6. **Connect to other initiatives: ** 

* https://openwaters.io/tides/

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


### Running Simulation jobs

This can now run simulation jobs - calculating the expected actual trajectories resulting from the intended movement (heading and speed) combined with the displacement by the currents.

#### define jobs

A simulation job definition is to be provided in a yaml file that looks like below:

```yaml
title: My Planned swim in October 2027
tz: Europe/Brussels    # Local timezone for visuals, user facing stuff, this file too

active:
  if-on: true          # job only executes if true - quickly enables / disables this job
  if-now-in-range:     # active job still only executes when the date this code is running is in this range
    begin: 2027-10-04
    end: 2027-10-11

date:                  # For which days should the simulation apply 
  range: 0d, 1d, 2d    # Today, Tomorrow, day after - can be up to 6d - can also be a fixed day 

calc:
  - id: "{date}-myname-{time}-pec"
    from: KOKSIJDE     # one of the wellknown positions in this code
    by: MBL_MIDR       # one of the wellknown swimmers in this code
    bearing: 333       # angle relative to °N
    duration: 6h       # for how long the swim is maintained
    time:              # at what time should the simulation start
      detect:          #   -- allows to detect times automatically
        types: pec     #   -- available types are PEC (Peak Ebb Current) and PFC (Peak Flood Current)
        in-range: 05:00-17:00  # ignore detected times that fall outside this window

extra:                 # optionally reference extra content to be included 
  qotd: ./data/simulation/qotd.yml                      # quotes and their authors
  obstructions: ./data/simulation/obstructions.wkt.csv  # danger areas to mark on the map
  coastline: ./data/simulation/coastline.wkt.csv        # coastline backdrop

results:
  folder: /tmp/results/2027-09-koksijde/{now}/          # where results should be stored locally
  labels:                                               # configurable labels
    ribs: deviationdistance                             # labels on the 'ribs' of the spine-diagram
    spine: bearing|duration|totaldistance               # label along the spine
  files:
    overview: ./{date}-overview.png                     # overview png
    gpx: ./{date}-{calc.id}.gpx                         # track gpx
  mail:                                                 # details for mail to send out
    to: Marc Portier <marc.portier@gmail.com>
    subject: Koksijde Test Results for {date}
    template: ./data/simulation/email-template.html
    attach: all

```

These job-files should be placed in `./data/simulation`

Additional files mentioned are

##### *wkt.csv files for obstructions and coastlines

```csv
WKT,fid,name,description
"MULTIPOLYGON ((( ... )))",276,geometry name,where we should not ever want to be ending up

```

##### quotes in yml format

```yaml
- txt: "How I wish I could mention something worth quoting"
  by: Anonymous
```

##### email-template

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>CSCM Simulation Update: {{ job_title }}</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; line-height: 1.6; color: #333; margin: 20px; }
        .qotd { font-style: italic; color: #555; border-left: 4px solid #004488; padding-left: 15px; margin: 20px 0; }
        .author { font-weight: bold; color: #004488; }
        .overview-map { max-width: 100%; height: auto; border: 1px solid #ddd; border-radius: 8px; margin: 20px 0; }
        .footer { font-size: 0.8em; color: #777; margin-top: 30px; border-top: 1px solid #eee; padding-top: 10px; }
        ul { padding-left: 20px; }
        li { margin-bottom: 5px; }
    </style>
</head>
<body>
    <p>Howdy,</p>

    {% if qotd_text %}
    <div class="qotd">
        "{{ qotd_text }}" <br>
        <span class="author">-- {{ qotd_author }}</span>
    </div>
    {% endif %}

    <p>Below the latest update for <strong>{{ date }}</strong>.</p>

    <img src="cid:overview" alt="Trajectory Overview" class="overview-map">

    <h3>Simulatie Details:</h3>
    <ul>
        <li><strong>Job:</strong> {{ job_title }}</li>
        <li><strong>Generated at:</strong> {{ now }} ({{ tz_name }})</li>
        <li><strong>Timezone:</strong> All times mentioned are in <strong>{{ tz_name }}</strong>.</li>
    </ul>

    <h3>Found options:</h3>
    <ul>
        {% for calc in calculations %}
        <li>
            <strong>Start: {{ calc.start_time_local }} {{ tz_name }}</strong> ({{ calc.type }})<br>
            Heading: {{ calc.bearing }}° N | Duration: {{ calc.duration }}<br>
            GPX-attachement: <code>{{ calc.gpx_filename }}</code>
        </li>
        {% endfor %}
    </ul>

    <p class="footer">
        This email is automatically generated by the CSCM Simulator.<br>
        Data source: Copernicus Marine (CMEMS) 1.5km North West Shelf Model.
    </p>
</body>
</html>
```

#### run the simulator

```bash
# by default the pipeline includes a CMEMS-data-update, handy for last minute updates
poetry run python -m cscm.simulation

# to skip that download step one can also
poetry run python -m cscm.simulation --skip-update
```