# Storage & Data Store Managers

The `cscm.storage` module provides an automated, hash-validated, and offline-capable physical storage layer for external oceanographic datasets. It guarantees zero redundant downloads, clean repository isolation, and predictable UTC temporal query resolution.

---

## 🌟 Key Capabilities

* **Zero-Configuration Paths**: Default subdirectories (`data_store/`) inside each domain module, automatically excluded by `.gitignore`.
* **Atomic `catalog.json` Manifests**: Every downloaded file (NetCDF, CSV, Skyfield BSP ephemeris) is registered with UTC start/end timestamps, SHA-256 hashes, forecast flags, and provider metadata.
* **Overriding via Environment Variables**: Redirect data storage paths seamlessly in production, HPC clusters, or Docker environments.
* **CLI Inspection**: Inspect cache volume, file counts, and stale forecast files without loading heavy science dependencies.

---

## ⚙️ Environment Variables

Each domain manager supports an environment variable to override its default physical storage folder:

| Environment Variable | Default Location | Managed Datasets |
| :--- | :--- | :--- |
| `CMEMS_DATA_FOLDER` | `src/cscm/current/cmems/data_store/` | Copernicus Marine 1.5 km hydrodynamic current NetCDFs (`uo`, `vo`) |
| `TIDE_DATA_FOLDER` | `src/cscm/tide/be/data_store/` | HIC KiWIS forecast CSVs & MDK 5-minute historical sensor CSVs |
| `MOON_DATA_FOLDER` | `src/cscm/moon/data_store/` | NASA JPL ephemeris kernels (`de421.bsp`) & Skyfield timescale files |

---

## 💻 CLI Usage: Inspecting Storage

To inspect the status of the local Copernicus Marine (CMEMS) data store from the command line:

```bash
poetry run python -m cscm.current.cmems status
```

**Sample Output:**
```text
==================================================
CSCM CMEMS Current Data Store Status
==================================================
Data folder:     /path/to/cscm/src/cscm/current/cmems/data_store
Catalog file:    /path/to/cscm/src/cscm/current/cmems/data_store/catalog.json
Entries count:   14
Total size:      412.50 MB
Earliest data:   2026-08-12T17:36:00+00:00
Latest data:     2026-10-27T12:00:00+00:00
Forecast files:  2
Stale forecasts: 0
==================================================
```

---

## 🐍 Python Usage Examples

### 1. Copernicus Hydrodynamic Currents (`CmemsCurrentManager`)

```python
from datetime import datetime, timezone, timedelta
from cscm.current.cmems.retrieve import CmemsCurrentManager

manager = CmemsCurrentManager()

# Inspect storage health and catalog metadata
status = manager.status()
print(f"Total entries cached: {status['total_entries']} ({status['total_size_bytes'] / (1024*1024):.1f} MB)")

# Find existing files covering a specific swimming window
t0 = datetime(2026, 10, 24, 8, 0, tzinfo=timezone.utc)
t1 = t0 + timedelta(hours=6)

covering_files = manager.find_covering_files(t0, t1)
for entry in covering_files:
    print(f"Covering file: {entry.file_name} [{entry.start_dt.isoformat()} to {entry.end_dt.isoformat()}]")
```

### 2. Flemish Coastal Tide Water Levels (`HicTideManager` & `MdkTideManager`)

```python
from datetime import datetime, timezone, timedelta
from cscm.tide.be import HicTideManager, MdkTideManager

# HIC KiWIS: Operational water level forecasts (KT-Last) & astronomical predictions (Astro.05)
hic_mgr = HicTideManager()

t_start = datetime.now(timezone.utc)
t_end = t_start + timedelta(hours=12)

# Queries the cache first; fetches from HIC KiWIS API only if un-cached or stale (> 6h)
df_forecast = hic_mgr.get_water_levels(
    station_code="OST",
    start_time=t_start,
    end_time=t_end,
    source="forecast",
)
print(df_forecast.head())

# MDK: High-resolution 5-minute historical sensor observations
mdk_mgr = MdkTideManager()
t_past = t_start - timedelta(days=2)

df_observed = mdk_mgr.get_water_levels(
    station_code="OST",
    start_time=t_past,
    end_time=t_start,
)
print(df_observed.head())
```

### 3. Planetary Ephemeris & Moon Phases (`MoonPhaseDataManager`)

```python
from cscm.moon import MoonPhaseDataManager

# Thread-safe singleton manager encapsulated in src/cscm/moon/data_store/
moon_mgr = MoonPhaseDataManager()

# Loads Skyfield JPL ephemeris kernel (automatically downloaded on first use)
eph = moon_mgr.get_ephemeris("de421.bsp")
ts = moon_mgr.get_timescale()

print(f"Ephemeris loaded from: {moon_mgr.data_folder}/de421.bsp")
```

---

## 🔒 Cache Invalidation & Hash Verification

1. **SHA-256 Checksums**: Whenever a file is retrieved or registered, its cryptographic SHA-256 hash is computed and stored in `catalog.json`.
2. **Forecast Freshness Window**: Forecast entries (`is_forecast=True`) have an operational freshness threshold (default 6 hours for HIC tides). Queries requesting newer horizons trigger automatic upstream refreshes while archiving older forecasts.
3. **Atomic Writes**: Catalog metadata is updated atomically via tempfile replacement, preventing catalog corruption during unexpected interruptions.
