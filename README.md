# cscm (Channel Swimmer Crossing Module) 

Assists in Current Modeling & Trajectory Optimization for swimmers in the North Sea.

A tactical routing, tidal analysis, and trajectory optimization system designed specifically for ultra-distance open-water swimmers operating in highly dynamic, non-linear coastal current fields.

Note: AI assisted documentation is available through [Mintlify](https://mintlify.wiki/marc-portier/cscm)

---

## 🎯 Project Goals

The ultimate objective of `cscm` is to solve **Zermelo's Navigation Problem** for human athletes. In open-water swimming, currents can easily equal or exceed a swimmer's cruising speed. By vectorially combining localized tidal stream velocities with human endurance profiles, `cscm` computes the optimal steering angles (headings) over time to yield the fastest path from A to B.

### Major Milestones:
* **Short-Term (September 2026 - Active):** Validate the kinematics model to support a 6-hour experimental test swim in Koksijde, Belgium. Models will predict the exact trajectories of two alternative courses (316° at high tide vs. 333° at low tide) designed to safely clear the local Colruyt mussel farm.
* **Mid-Term (September 2027):** Deliver a tactical pacing, timing, and routing plan for a potential historic ultra-crossing. Factoring in swimmer fatigue models, based on results from actual swims by various people.
* **Long-Term (The "Waze for Swimmers" App):** Build a serverless, highly optimized web application where users can input start/end coordinates and instantly receive the optimal start time window and head-over-time routing strategy. This should involve the production of a tuned "cloud optimised" statistical model for the currents in the North Sea.

---

## 🏗️ Architecture & Modular Layers

The repository is organized under a modular Python package (`cscm`), structured into clean architectural layers:

```text
┌────────────────────────────────────────────────────────────────────────┐
│                      Kinematics, Routing & Simulation                  │
│       cscm.simulation  │  cscm.model  │  docs/experiments/graphics     │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼────────────────────────────────────┐
│                  Universal Data Access Layer (UDAL)                    │
│      cscm.broker: CompositeDataBroker, NamedQuery / QueryBuilder       │
│      Semantic URIs, Format Negotiation (pandas, xarray, records, dict) │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼────────────────────────────────────┐
│                    Physical Storage & Caching Layer                    │
│      cscm.storage: AbstractDataStoreManager, atomic catalog.json        │
├─────────────────────┬───────────────────────────┬──────────────────────┤
│ cscm.current.cmems  │       cscm.tide.be        │      cscm.moon       │
│ Copernicus 1.5 km   │ HIC KiWIS & MDK Sensors   │ NASA JPL Ephemeris   │
│ Current NetCDFs     │ Alongshore Phase Models   │ Moon Phases & Cycles │
└─────────────────────┴───────────────────────────┴──────────────────────┘
```

* **Universal Data Access Layer (UDAL) (`cscm.broker`):** Decouples consumer applications from upstream data sources. Offers one-line and fluent query access (`broker.query("current", ...)`, `broker.build("tide").param(...).execute()`), automatic format negotiation (`.to_dataframe()`, `.to_xarray()`, `.to_records()`), and composite brokering (merging past sensor data from MDK with future forecasts from HIC KiWIS across `now`).
* **Physical Storage & Caching (`cscm.storage`):** Hash-validated, offline-first local data stores with atomic `catalog.json` indexing, zero-configuration local paths, and environment variable overrides.
* **Hydrodynamic Currents (`cscm.current.cmems`):** Programmatic ingestion and caching of Copernicus Marine (CMEMS) 1.5 km hydrodynamic forecasts, paired with adaptive spatial Principal Component Analysis (PCA) to extract localized tidal flow axes and slack water timing.
* **Coastal Tidal Models (`cscm.tide.be`):** Flemish coastal gauge connectors (HIC KiWIS forecasts and MDK historical observations) combined with alongshore coordinate interpolation and phase propagation models.
* **Astronomical Ephemeris (`cscm.moon`):** High-precision lunar phase and synodic cycle calculations using NASA JPL ephemeris files via `skyfield`, establishing astronomical spring/neap tidal cycle baselines.
* **Kinematics & Routing (`cscm.model`, `cscm.simulation`, `cscm.wellknown`):** Discrete trajectory calculation combining swimmer propulsion, endurance curves, and current fields.

---

## 📖 Documentation, Demos & Experiments

Detailed guides and interactive previews are maintained under `docs/`:

* **[Feature Demos & Usage Guides (`docs/demos/`)](./docs/demos/README.md):**
  - **[Physical Storage & Data Store Managers](./docs/demos/storage-datamanagers.md):** Managing cached NetCDFs, CSVs, and ephemeris files, CLI status checks, and environment variables.
  - **[UDAL & Data Brokers](./docs/demos/broker-udal.md):** Querying currents and tides via semantic contracts, fluent builders, and format negotiation.
* **[Visualizations & Experimental Profiles (`docs/experiments/`)](./docs/experiments/README.md):**
  - **[Coastal Swim Trajectory Profile](./docs/experiments/graphics/kust-zwem-profiel/):** High-resolution DIN A3 landscape pacing and current profile (Bredene Post 4 ➔ Vosseslag).
  - **[Beach Post Hydrodynamic Profile](./docs/experiments/graphics/strandpost-profiel/):** Daily swim-safety tidal curve and current forecast for beach lifeguard stations.
* **[Project Roadmap & Backlog (`docs/plans.md`)](./docs/plans.md):** Active priorities, architectural sub-plans, and consolidated task backlog.

---

## 🛠️ Usage & Automated Workflows

The codebase is built with modern Python tooling (Poetry, xarray, geopandas). 

### Setup

1. Install `poetry` (see [Poetry documentation](https://python-poetry.org/docs/#installing-with-the-official-installer)).
2. Configure local virtualenv:
```bash
poetry config virtualenvs.in-project true --local
poetry env use python3.14
poetry install
```
3. Copy `.env.example` to `.env` and configure your credentials.

### Inspecting Local Data Stores:
To inspect the status of cached Copernicus datasets without running full simulations:
```bash
poetry run python -m cscm.current.cmems status
```

### Processing Copernicus Data:
To download/update the local CMEMS datastore and run the adaptive PCA current analysis:
```bash
poetry run python -m cscm.current.cmems
```

### Running Simulation Jobs
Simulation jobs calculate expected ground tracks resulting from swimmer velocity combined with hydrodynamic drift.

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
