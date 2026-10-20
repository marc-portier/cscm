# Architectural Refactoring & Unified Data Sub-Plan (BL-9 & Road to Saturday)

**Date**: 2026-10-20  
**Status**: Approved Architecture & Phased Implementation Plan  
**Scope**: BL-9 (Unified Hydrodynamic Provider Abstraction), UDAL Data Access, Domain Model Harmonization, and Saturday Delivery  

---

## 1. Executive Summary & Strategic Context

This document captures the architectural consensus established on October 20, 2026, bridging the exploratory graphics prototyping phase (**v1–v5** of the Coastal Swim Trajectory Profile) with the core `cscm` engineering roadmap.

It addresses two intertwined objectives:
1. **Immediate Tactical Goal (Saturday Oct 24, 2026)**: Deliver authentic, production-grade **DIN A3 landscape prints** of the Coastal Swim Trajectory Profile (Bredene Post 4 ➔ Vosseslag ➔ Bredene Post 4) for an expert panel on coastal currents and sea-swimming safety, driven by **real Copernicus CMEMS forecast data** and verified alongshore tidal current projections.
2. **Long-Term Strategic Goal**: Establish a robust, clean, and decoupled data architecture inspired by the **Universal Data Access Layer (UDAL)** principles of **FAIR-EASE**, harmonizing data retrieval, caching, query federation, domain kinematics, and high-level services without accumulating legacy cruft or discarding valuable prior engineering.

---

## 2. The Four Architectural Pillars

The architecture is partitioned into four distinct layers:

```
[ Upstream Data Providers: CMEMS, HIC KiWIS, MDK Meetnet Vlaamse Banken ]
                               │
                               ▼
┌────────────────────────────────────────────────────────────────────────┐
│ 1. DATA RETRIEVAL & CACHING LAYER (DataStoreManager)                   │
│    • Zero-conf local storage (`./data_store/`) + `.env` centralisation │
│    • Discrete managers: CmemsCurrentManager, HicTideManager, etc.      │
│    • Standardized `catalog.json` per store with freshness/status checks │
└──────────────────────────────────┬─────────────────────────────────────┘
                                   │
                                   ▼
┌────────────────────────────────────────────────────────────────────────┐
│ 2. UNIVERSAL DATA ACCESS LAYER / UDAL (DataBroker & NamedQuery)        │
│    • Query protocol: broker.query("urn:cscm:...").execute(...)         │
│    • Standardized schema contracts (DataFrame) & Rich Provenance       │
│    • Seamless future transition to ARCO (Zarr/DuckDB-Wasm client)      │
└──────────────────────────────────┬─────────────────────────────────────┘
                                   │
                                   ▼
┌────────────────────────────────────────────────────────────────────────┐
│ 3. DOMAIN KINEMATICS & OPERATORS (CurrentsModel & model.py)            │
│    • Continuous spatio-temporal interpolators consuming the Broker     │
│    • 2D Open Water Drift (Channel Swims) vs 1D Alongshore Kinematics   │
│    • Strict alongshore current projection: v_ground = v_swim + u_along │
└──────────────────────────────────┬─────────────────────────────────────┘
                                   │
                                   ▼
┌────────────────────────────────────────────────────────────────────────┐
│ 4. SERVICE UNIFORMISATION & CLI ENTRYPOINTS                            │
│    • High-level services: Simulation, Analysis, Viz (Infographics)     │
│    • Predictable python `-m` invocations and `pyproject.toml` scripts  │
└────────────────────────────────────────────────────────────────────────┘
```

---

### Pillar 1: Data Retrieval & Caching (`AbstractDataStoreManager`)

* **Zero-Conf Default with `.env` Flexibility**:
  * By default, each subsystem writes to a local `data_store/` folder adjacent to its package code (e.g., `src/cscm/current/cmems/data_store/`), ensuring zero-configuration friction for developers.
  * Overridable via environment variables (e.g., `CMEMS_DATA_FOLDER`, `HIC_DATA_FOLDER`, or an umbrella `CSCM_DATA_FOLDER`), enabling users to centralize caching to `.cache/cscm/` or an external mount.
* **Separation of Concerns**:
  * Retrieval logic does not contain business kinematics. Its sole duty is managing raw upstream payloads (NetCDF, API JSON/CSV), verifying hashes, and checking completeness.
  * Preserves distinct physical dimensions: `current/` (hydrodynamics) and `tide/` (water level elevations) remain strictly separated, allowing for future providers such as `tide/cmems` (satellite altimetry/tide products) or `current/uk`.
* **Standardized `catalog.json`**:
  * Each `data_store/` maintains a lightweight metadata catalog tracking: `{file_name, start_dt, end_dt, retrieved_at, is_forecast, provider_metadata, hash}`.
* **Status & Freshness Inspection**:
  * Lightweight status command (`python -m cscm.current.cmems.status`, `python -m cscm.tide.be.hic.status`) reporting cached temporal bounds and forecast expiration status.
* **Graceful Offline Fallback**:
  * If upstream APIs fail (e.g., Waterinfo network timeout), the manager falls back to the most recent valid local cache with a warning log, guaranteeing uninterrupted offline development and test execution.

---

### Pillar 2: Universal Data Access Layer (UDAL & `DataBroker`)

Inspired by the FAIR-EASE UDAL philosophy, data access is decoupled from physical storage through a standardized semantic query dialogue:

* **Broker Pattern**:
  * Interactions begin with a `DataBroker` instance (`CscmLocalBroker`), with room for future alternatives (e.g., `ARCOBroker`).
* **Semantic Query Identifiers (URNs)**:
  * Queries are requested via URNs specifying the expected data contract:
    * `urn:cscm:current`: 2D horizontal hydrodynamic velocity vectors.
    * `urn:cscm:tide`: 1D water level elevations relative to a vertical datum.
* **`NamedQuery` Lifecycle**:
  ```python
  qry = broker.query("urn:cscm:current")
  # Inspect parameters and schema
  print(qry.supported_parameters)

  # Execute with uniform temporal & spatial parameters
  result = qry.execute(
      start_time=datetime(2026, 10, 24, 8, 0, tzinfo=timezone.utc),
      end_time=datetime(2026, 10, 24, 14, 0, tzinfo=timezone.utc),
      points=route_points  # Or bbox=(min_lon, min_lat, max_lon, max_lat)
  )

  df: pd.DataFrame = result.data()
  provenance: dict = result.metadata  # Model run, stations used, vertical datum
  ```
* **Canonical Data Contracts (Standardized Schemas)**:
  * **Currents Contract (`urn:cscm:current`)**:
    * Columns: `[timestamp, lat, lon, u_mps, v_mps, speed_mps, direction_deg]`
  * **Tide Contract (`urn:cscm:tide`)**:
    * Columns: `[timestamp, lat, lon, water_level_m, datum, series_type]`
    * `datum`: Explicit vertical benchmark (`TAW`, `NAP`, `LAT`, `ODN`).
    * `series_type`: `observed`, `astronomical`, or `forecast`.
* **Trajectory / Waypoint Sampling**:
  * Built-in support for sampling currents along an ordered trajectory (`list[Position]`), performing spatio-temporal bilinear interpolation inside the broker so downstream services do not duplicate interpolation logic.
* **Future ARCO Alignment (Analysis-Ready Cloud-Optimized)**:
  * This exact dialogue maps directly to client-side TypeScript querying Zarr or GeoParquet via DuckDB-Wasm in Milestone 8 ("Waze for Swimmers").

---

### Pillar 3: Domain Model Integration & Kinematics Harmonization

* **Harmonizing `src/cscm/model.py`**:
  * Resolves historic inconsistencies (e.g., missing `self.converter` in `MovingObject.move()`, ad-hoc tuples in `predict.py`).
  * `SpeedVector` and `Position` remain the canonical mathematical primitives across all modules.
* **`CurrentsModel` as Broker Consumer**:
  * Rather than directly parsing NetCDF files, `CurrentsModel` becomes an abstract continuous operator that consumes data provided by `DataBroker`:
    ```python
    class CurrentsModel(ABC):
        @abstractmethod
        def get_current(self, position: Position, moment: datetime) -> SpeedVector:
            """Spatio-temporal continuous interpolation."""
            ...
    ```
* **Dual Trajectory Kinematics Under One Roof**:
  1. **2D Open Water Drift (`OpenWaterTrajectoryCalculator`)**:
     * Open ocean / English Channel crossing.
     * Integrates forward motion on intended heading $\theta$ with full 2D leeway and drift vectors: $\vec{v}_{\text{eff}} = \vec{v}_{\text{swim}} + \vec{u}_{\text{current}}$.
  2. **1D Alongshore Coastal Kinematics (`AlongshoreTrajectoryCalculator`)**:
     * Coastal trajectory profiles (e.g., Bredene ➔ Vosseslag, Belgian coast swims).
     * Swimmer tracks a 1D alongshore distance metric $s \in [0, L]$.
     * **Alongshore Projection Policy**: Currents are strictly projected onto the coastal tangent vector:
       $$u_{\text{alongshore}} = \vec{u} \cdot \hat{t}_{\text{coast}}$$
       $$v_{\text{ground}} = v_{\text{water}} + u_{\text{alongshore}}$$

---

### Pillar 4: Service Uniformisation & CLI Entrypoints

High-level consumers are structured as uniform **Services**:
* `cscm.simulation`: Trajectory prediction, YAML job runners, automated briefing mailers.
* `cscm.analysis`: Physical diagnostics, tidal harmonic decomposition, peak current classification (PFC/PEC/ZRO), spring-neap envelope analysis.
* `cscm.viz.coastal_swim_profile`: Space-time trajectory diagrams (v5 standard, A3 landscape).
* `cscm.viz.beach_post_profile`: Static station infographics (v11 standard, beach perspective).

Each service exposes:
* A standardized Python module CLI via `__main__.py` (e.g., `python -m cscm.viz.coastal_swim_profile`).
* Registration in `pyproject.toml` under `[project.scripts]` for direct terminal execution.

---

## 3. Target Package Directory Structure

The target layout organizes code into clear domain namespaces while preserving and elevating existing capabilities:

```
src/cscm/
├── __init__.py
├── model.py                      # Primitives: Position, SpeedVector, MovingObject, Swimmer
│
├── storage/                      # PILLAR 1: PHYSICAL STORAGE & CACHING ABSTRACTIONS
│   ├── __init__.py
│   └── base.py                   # AbstractDataStoreManager, CatalogEntry
│
├── landmarks/                    # TOP-LEVEL DOMAIN: COASTAL GEOMETRY & LANDMARKS
│   ├── __init__.py
│   ├── loader.py                 # Unified loader for posts, groynes, harbour channels
│   ├── be_lifeguard_posts.yaml   # Consolidated lifeguard stations
│   └── be_coast_locations.yaml   # Comprehensive Belgian coastal nodes
│
├── current/                      # CURRENT SUBSYSTEM
│   ├── __init__.py
│   ├── cmems/                    # Copernicus CMEMS Current Provider
│   │   ├── __init__.py
│   │   ├── __main__.py           # CLI: python -m cscm.current.cmems (retrieve/status)
│   │   ├── retrieve.py           # CmemsCurrentManager(AbstractDataStoreManager)
│   │   ├── analyse.py            # Diagnostic tools: cell classification, ellipses
│   │   └── data_store/           # Default zero-conf cache (.gitignore)
│   └── model.py                  # Continuous CurrentsModel implementations
│
├── tide/                         # TIDE / WATER LEVEL SUBSYSTEM
│   ├── __init__.py
│   └── be/                       # Belgian Regional Network
│       ├── __init__.py
│       ├── __main__.py           # CLI: python -m cscm.tide.be
│       ├── hic.py                # HicTideManager(AbstractDataStoreManager) - KiWIS API
│       ├── mdk.py                # MdkTideManager(AbstractDataStoreManager) - Meetnet Boeien
│       ├── alongshore.py         # 89-node coastal tidal wave phase interpolator
│       └── data_store/           # Default zero-conf cache (.gitignore)
│
├── moon/                         # CELESTIAL & LUNAR CYCLE SUBSYSTEM
│   ├── __init__.py
│   ├── phases.py                 # Astronomical lunar cycle calculations
│   ├── ephemeris.py              # MoonDataManager(AbstractDataStoreManager) via Skyfield Loader
│   └── data_store/               # Encapsulated de421.bsp cache (.gitignore, no root pollution!)
│
├── broker/                       # PILLAR 2: UNIVERSAL DATA ACCESS LAYER (UDAL)
│   ├── __init__.py
│   ├── base.py                   # DataBroker, NamedQuery, QueryResult
│   ├── local.py                  # CscmLocalBroker (federates local DataStoreManagers)
│   └── queries/
│       ├── __init__.py
│       ├── current.py            # Handler for 'urn:cscm:current'
│       └── tide.py               # Handler for 'urn:cscm:tide'
│
├── kinematics/                   # PILLAR 3: TRAJECTORY CALCULATORS
│   ├── __init__.py
│   ├── open_water.py             # 2D Lagrangian drift integration
│   └── alongshore.py             # 1D coastal 25m fine-grid kinematics & projection
│
├── simulation/                   # PILLAR 4: SERVICES
│   ├── __init__.py
│   ├── __main__.py               # CLI: python -m cscm.simulation
│   ├── predict.py                # Predictive simulation orchestrator
│   ├── jobs.py                   # YAML job runner
│   └── mailer.py                 # Automated dispatch
│
├── analysis/                     # SERVICE: HYDRODYNAMIC ANALYSIS
│   ├── __init__.py
│   └── __main__.py               # CLI: python -m cscm.analysis
│
├── viz/                          # SERVICE: VISUALIZATION & INFOGRAPHICS
│   ├── __init__.py
│   ├── coastal_swim_profile/     # Trajectory Profile (v5 engine)
│   │   ├── __init__.py
│   │   ├── __main__.py           # CLI: python -m cscm.viz.coastal_swim_profile
│   │   ├── generator.py          # Vector SVG generator
│   │   └── data_contract.py      # Schema serializer (data_to_plot.yaml)
│   └── beach_post_profile/       # Strandpost Profile (v11 engine)
│       ├── __init__.py
│       ├── __main__.py           # CLI: python -m cscm.viz.beach_post_profile
│       ├── renderer.py           # Jinja2 SVG template renderer
│       └── template.svg          # SVG template
```

---

## 4. Phased Implementation Roadmap (Tuesday ➔ Friday)

To guarantee that Saturday's expert panel receives authentic, high-impact A3 prints while building cleanly towards the strategic architecture, execution proceeds in four phases:

### Phase 1: Core DataStore & UDAL Abstractions (Wednesday Oct 21)
* Implement `AbstractDataStoreManager` in `src/cscm/storage/base.py` with zero-conf local `./data_store/` and `.env` directory overrides.
* Refactor `src/cscm/current/cmems/retrieve.py` into `CmemsCurrentManager(AbstractDataStoreManager)`.
* Implement `HicTideManager` in `src/cscm/tide/be/hic.py` adopting the same cache and catalog pattern.
* Refactor `src/cscm/moon/phases.py` to use `MoonDataManager` and `skyfield.api.Loader` to store `de421.bsp` inside `moon/data_store/` rather than the workspace root.
* Implement `DataBroker`, `NamedQuery`, and `QueryResult` in `src/cscm/broker/` supporting `urn:cscm:current` and `urn:cscm:tide`.

### Phase 2: Alongshore Kinematics & Real Data Bridge (Thursday Oct 22)
* Implement `AlongshoreTrajectoryCalculator` in `src/cscm/kinematics/alongshore.py`:
  * Samples `urn:cscm:current` via the `DataBroker`.
  * Selects full water cells (avoiding dampened land boundary cells conform `cmems-coastal-grid-cells` skill).
  * Computes coastal tangent vector and alongshore projection ($u_{\text{alongshore}} = \vec{u} \cdot \hat{t}_{\text{coast}}$).
  * Performs 25m fine-grid discrete kinematics for 9 isotachs ($0.6$ to $1.4\text{ m/s}$) across the 8 legs of Bredene P4 ➔ Vosseslag ➔ Bredene P4.
* Create data adapter writing directly to the `data_to_plot_v5.yaml` schema for any arbitrary date and start time.

### Phase 3: Saturday Live Forecast & A3 Print Production (Friday Oct 23)
* Run live forecast retrieval for the upcoming weekend (Saturday Oct 24, 2026).
* Execute trajectory profile generator with authentic tidal current predictions.
* Verify turnaround kentering time, peak velocities, and headwind/tailwind scaling cards.
* Export high-resolution 300 DPI print-ready assets:
  * `ontwerp-kustzwem-profiel-20261024-A3.svg`
  * `ontwerp-kustzwem-profiel-20261024-A3.png` / PDF.
* Deliver print package for Marc's presentation on Saturday morning.

### Phase 4: Service Uniformisation & Core Landing (Week of Oct 26+)
* Harmonize graphics generation approach (Jinja2 SVG template vs Python generator, per BL-10).
* Formalize `src/cscm/viz/` and register CLI entrypoints in `pyproject.toml`.
* Expand automated `pytest` test suite with synthetic fixtures for brokers and stores.
