# Python & Poetry Environment Policy

## Overview
This repository uses **Poetry** for dependency and virtual environment management.

## Guidelines
1. **Always Use Poetry for Execution**:
   - Never run raw system `python`, `python3`, or `pip`.
   - Always prefix execution with `poetry run`, e.g.:
     - `poetry run python ...`
     - `poetry run pytest ...`
2. **Dependencies**:
   - Dependencies must be managed via Poetry (`poetry add ...`).
   - Avoid adding unnecessary external dependencies unless discussed with the user.
