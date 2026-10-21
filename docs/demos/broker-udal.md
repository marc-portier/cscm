# Universal Data Access Layer (UDAL) & Data Brokers

The `cscm.broker` module provides the **Universal Data Access Layer (UDAL)** for `cscm`. It abstracts data fetching across disparate providers (Copernicus CMEMS, HIC KiWIS, MDK sensors) behind unified semantic query URIs, format negotiation, and robust domain boundary guards.

---

## 🌟 Key Capabilities

* **Semantic Query URIs & Shorthands**: Standardized query contracts (`urn:cscm:query:current`, `urn:cscm:query:tide`, `urn:cscm:query:moonphase`) or simple keywords (`"current"`, `"tide"`).
* **Format Negotiation**: One-call export to your preferred data representation: `pandas.DataFrame`, `xarray.Dataset`, list of record dicts, or column dictionaries.
* **Fluent QueryBuilder Pattern**: Clean method-chaining for constructing complex multi-point or temporal queries.
* **Belgian Tide Composite Brokering**: Automatically splits a query spanning past and future across `now`: historical sensor data is retrieved from MDK, future forecasts are retrieved from HIC KiWIS, and both are stitched into a continuous, deduplicated dataset.
* **Domain Boundary Protection**: Explicit, informative exceptions when queries fall outside the physical, geographic, or temporal capabilities of the underlying provider.

---

## 📋 Semantic Query Catalogue

| Query URI | Shorthands | Primary Broker | Key Parameters | Schema Highlights |
| :--- | :--- | :--- | :--- | :--- |
| `urn:cscm:query:current` | `"current"` | `CmemsCurrentBroker` | `lat`, `lon`, `positions`, `start_time`, `end_time`, `avoid_boundary_damping` | `current_speed_m_s`, `current_direction_deg`, `current_speed_eastward_m_s`, `current_speed_northward_m_s` |
| `urn:cscm:query:tide` | `"tide"` | `BelgianTideBroker` (composite) | `station`, `lat`, `lon`, `start_time`, `end_time`, `source`, `time_offset_minutes` | `water_level_m_taw`, `source`, `station`, `lat`, `lon` |
| `urn:cscm:query:moonphase` | `"moonphase"`, `"moon"` | *(In progress)* | *(TBD)* | Synodic cycles, lunar phases |

---

## 🚀 Quick Start: Direct One-Liner Queries

Use the `get_broker()` singleton factory to access the shared composite broker:

```python
from datetime import datetime, timezone, timedelta
from cscm.broker import get_broker

broker = get_broker()

# 1. Query Hydrodynamic Currents for a route or point
now_utc = datetime.now(timezone.utc)
result = broker.query(
    "current",
    lat=51.25,
    lon=2.97,
    start_time=now_utc,
    end_time=now_utc + timedelta(hours=6),
    avoid_boundary_damping=True,
)

# Access tabular data as a pandas DataFrame
df_currents = result.to_dataframe()
print(df_currents[["timestamp", "current_speed_m_s", "current_direction_deg"]].head())

# Inspect query provenance and metadata
print(result.inspect())
```

---

## 🔄 Format Negotiation

Every `QueryResult` returned by a broker supports multi-format conversion:

```python
result = broker.query("tide", station="OST", start_time=now_utc, end_time=now_utc + timedelta(hours=3))

# 1. Pandas DataFrame
df = result.to_dataframe()          # or result.data("pandas")

# 2. Xarray Dataset (indexed by UTC timestamp)
ds = result.to_xarray()             # or result.data("xarray")

# 3. List of row dictionaries (JSON/API-ready)
records = result.to_records()       # or result.data("records")

# 4. Column-oriented dictionary
col_dict = result.to_dict()         # or result.data("dict")
```

---

## 🏗️ Fluent QueryBuilder

For complex queries with multiple parameters or when constructing queries dynamically across application layers:

```python
from datetime import datetime, timezone, timedelta
from cscm.broker import get_broker

broker = get_broker()

# Build query with fluent chaining
query = (
    broker.build("current")
    .param("lat", 51.234)
    .param("lon", 2.926)
    .param("start_time", datetime(2026, 10, 24, 8, 0, tzinfo=timezone.utc))
    .param("end_time", datetime(2026, 10, 24, 14, 0, tzinfo=timezone.utc))
    .param("avoid_boundary_damping", True)
)

# Inspect query contract and parameters before execution
print("Supported parameters:", query.supported_params)
print("Result schema:", query.result_schema)

# Execute query
result = query.execute()
print(f"Retrieved {len(result)} current vectors from {result.metadata['provider']}.")
```

---

## 🌊 Belgian Composite Tide Brokering (Past + Future)

When planning or analyzing swims around the present moment, historical observations and future forecasts must often be merged. `BelgianTideBroker` handles this transparently:

```python
from datetime import datetime, timezone, timedelta
from cscm.broker import get_broker

broker = get_broker()

# A 24-hour window: 12 hours in the past to 12 hours in the future
now_utc = datetime.now(timezone.utc)
t_past = now_utc - timedelta(hours=12)
t_future = now_utc + timedelta(hours=12)

result = broker.query(
    "tide",
    station="OST",
    start_time=t_past,
    end_time=t_future,
    source="auto",
)

df = result.to_dataframe()

# The result is a seamless, continuous timeseries:
# - Past points (timestamp < now): from MDK sensor observations
# - Future points (timestamp >= now): from HIC KiWIS operational forecast
print(df.tail())
print("Multi-segment provenance:", result.metadata["segments"])
```

---

## ⚠️ Domain Boundary Protections & Exceptions

The UDAL layer validates query parameters against physical and operational constraints, raising descriptive exceptions from `cscm.broker`:

### 1. `GeographicOutOfDomainError`
Raised when requested coordinates fall outside the provider's valid grid or coastal model:
```python
from cscm.broker import GeographicOutOfDomainError

try:
    # Querying the Belgian tide model in Paris (> 250 km away)
    broker.query("tide", lat=48.8566, lon=2.3522)
except GeographicOutOfDomainError as e:
    print(f"Handled geographic boundary violation: {e}")
```

### 2. `TemporalOutOfDomainError`
Raised when requesting future data from historical-only sensor networks (e.g. MDK), or requesting dates beyond operational forecast lookahead limits (e.g. > 7 days ahead for CMEMS):
```python
from cscm.broker import TemporalOutOfDomainError

try:
    # Asking MDK sensor broker for tomorrow's water levels
    tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
    mdk_broker.query("tide", station="OST", start_time=tomorrow)
except TemporalOutOfDomainError as e:
    print(f"Handled temporal capability mismatch: {e}")
```

### 3. `InvalidQueryParameterError`
Raised for invalid parameter combinations, such as `start_time > end_time`.
