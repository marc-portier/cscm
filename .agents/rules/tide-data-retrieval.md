# Coastal Tide & Water Level Retrieval Policy

## Overview
All water level observations and tidal forecasts must be retrieved and managed through the central `cscm.tide` module (`cscm.tide.hic` for operational forecasts and `cscm.tide.mdk` for historical sensor observations), rather than via ad-hoc API requests or one-off scraping scripts.

## Guidelines

1. **Always Use `cscm.tide` Clients**:
   - For operational water level forecasts (`today + 1` to `today + 2`), astronomical predictions, and extreme tides (HW/LW):
     ```python
     from cscm.tide.hic import HicClient
     client = HicClient()
     df = client.get_operational_forecast("Oostende Haven", start_dt, end_dt)
     ```
   - For measured historical sensor gauge series:
     ```python
     from cscm.tide.mdk import MdkClient
     client = MdkClient()
     df = client.get_water_level_series("OHMWS5", start_dt, end_dt)
     ```
2. **Never Write One-Off Fetch Scripts**:
   - Do not bypass `cscm.tide` by making standalone `requests` calls or direct raw KiWIS queries in application or visualization code.
3. **Future Regional Modularization (Backlog BL-9)**:
   - As `cscm` expands across the English Channel and North Sea, regional clients will be organized under `cscm.tide.<region>` (e.g. `cscm.tide.be`, `cscm.tide.nl`, `cscm.tide.fr`, `cscm.tide.uk`).
   - A unified `TideModel` facade will automatically route queries by `(lat, lon)` and time window.
4. **Local Caching & Rate Limiting**:
   - Cache historical gauge series locally to avoid redundant upstream hits to HIC Waterinfo and MDK servers.
   - Respect upstream rate limits and handle network timeouts gracefully with clear fallback strategies.
5. **Datum & Metadata Preservation**:
   - Always preserve vertical datum information (e.g. `TAW` for Belgium, `NAP` for the Netherlands, `LAT` for marine charts) in downstream data contracts and metadata manifests.
