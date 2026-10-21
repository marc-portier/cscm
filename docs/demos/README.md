# Demos & Feature Guides

This section provides practical, snippet-driven guides demonstrating the core capabilities of the `cscm` library. Each demo includes CLI usage instructions, Python code samples, configuration options (including environment variables), and expected data outputs.

---

## 📚 Available Demos

### 1. [Physical Storage & Data Store Managers](./storage-datamanagers.md)
* **Scope**: Physical data caching, atomic manifests (`catalog.json`), zero-configuration subfolder paths, and CLI cache inspection.
* **Covers**:
  - `CmemsCurrentManager` (Copernicus 1.5 km hydrodynamic NetCDFs)
  - `HicTideManager` (Flemish HIC KiWIS forecast cache)
  - `MdkTideManager` (MDK historical 5-minute gauge readings)
  - `MoonPhaseDataManager` (NASA JPL ephemeris `de421.bsp` & Skyfield timescales)
  - CLI command: `poetry run python -m cscm.current.cmems status`
  - Environment variables: `CMEMS_DATA_FOLDER`, `TIDE_DATA_FOLDER`, `MOON_DATA_FOLDER`

### 2. [Universal Data Access Layer (UDAL) & Data Brokers](./broker-udal.md)
* **Scope**: High-level data access abstraction decoupling science engines and visualization pipelines from upstream APIs.
* **Covers**:
  - Semantic query URIs (`urn:cscm:query:current`, `urn:cscm:query:tide`, `urn:cscm:query:moonphase`) and simple shorthands (`"current"`, `"tide"`)
  - Format negotiation: `.to_dataframe()`, `.to_xarray()`, `.to_records()`, `.to_dict()`
  - Fluent `QueryBuilder` method chaining (`broker.build("current").param(...).execute()`)
  - Belgian Composite Tide Brokering (seamless past MDK sensor observations + future HIC KiWIS forecasts)
  - Domain boundary exceptions (`GeographicOutOfDomainError`, `TemporalOutOfDomainError`)

---

## 🧭 How Demos Relate to Experiments

While the guides in this directory focus on **clean library interfaces and operational usage**, experimental visualizations and exploratory prototypes are documented in [docs/experiments/](../experiments/README.md). As experimental graphics mature and become part of the library, corresponding usage demos are added here.