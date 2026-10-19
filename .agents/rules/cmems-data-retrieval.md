# CMEMS Hydrodynamic Data Retrieval Policy

## Overview
All hydrodynamic current data from the Copernicus Marine Service (CMEMS) must be retrieved and managed through the central `cscm.current.cmems` pipeline rather than via ad-hoc scripts or direct `copernicusmarine` CLI calls.

## Guidelines

1. **Always Use `cscm.current.cmems`**:
   - To update the local CMEMS data store with recent or forecast data:
     ```bash
     poetry run python -m cscm.current.cmems --limit 1 --skip-analysis
     ```
   - Or programmatically via `from cscm.current.cmems.retrieve import CMEMSDataManager`:
     ```python
     dm = CMEMSDataManager()
     dm.update_cmems_data(limit=1)
     ```
2. **Never Write One-Off Download Scripts**:
   - Do not bypass `cscm.current.cmems` by writing standalone scripts calling `copernicusmarine.subset()` or `copernicusmarine login`.
3. **Rationale**:
   - Automatically loads credentials from `.env` (`COPERNICUSMARINE_SERVICE_USERNAME` and `COPERNICUSMARINE_SERVICE_PASSWORD`).
   - Ensures astronomical lunar cycle partitioning (synodic month chunks with +5 days tidal age margin).
   - Manages metadata JSON files, catalog indexing, and atomic cleanup of superseded forecast files.
   - Keeps the shared local cache (`src/cscm/current/cmems/data_store/`) consistent and up-to-date for all consumers (analysis, trajectory simulations, and infographic renderers).
