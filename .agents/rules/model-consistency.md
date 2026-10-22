# Domain Model Consistency & Experiment Graduation Policy

## Overview
The core namespace `src/cscm/` represents the authoritative domain model of the project (`cscm.model`).
Experiments in `docs/experiments/` or `scratch/` are encouraged to rapidly prototype algorithms, geometry, and visual concepts using the brokers (`cscm.broker`) and storage managers (`cscm.storage`).
However, promoting or "landing" code from experiments into `src/cscm/` must strictly adhere to the core domain model rather than introducing uncoordinated parallel abstractions.

## Guidelines for Agents

### 1. No Island Abstractions in `src/`
- When moving algorithms or pipelines from `docs/experiments/` into `src/cscm/`, do NOT create duplicate, ad-hoc classes for concepts that belong to the core model (e.g. `Swimmer`, `Position`, `SpeedVector`, `Trajectory`, `Environment`, or `CurrentsModel`).
- Domain logic in `src/` must be integrated with, inherit from, or refactor the central types in `src/cscm/model.py`.

### 2. Refactor the Core Model; Do Not Bypass It
- If `model.py` lacks concepts required by an experiment (e.g. waypoint-constrained alongshore routes, fatigue pacing curves, or broker-backed dynamic environments):
  - **Refactor `model.py` deliberately** to accommodate the new requirement.
  - Do NOT create an isolated sidecar module (e.g., an isolated `cscm.kinematics` that invents its own independent `Checkpoint` or `SwimmerTrajectory`) simply to avoid refactoring `model.py`.
  - In `v0.x`, internal interfaces are explicitly subject to fearless refactoring to maintain clean referential consistency (see `git-workflow.md`).

### 3. Experiment Graduation Criteria
An experiment in `docs/experiments/` is ready to graduate into `src/cscm/` only when:
1. **Model Alignment**: Its domain entities are mapped onto or unified with `cscm.model` (`MovingObject`, `Swimmer`, `TrajectoryCalculator`).
2. **Broker Integration**: Environmental inputs are brokered via `cscm.broker`.
3. **Hermetic Test Suite**: Covered by unit tests in `tests/` without unmocked external dependencies.

### 4. Pragmatic Staging (Option A vs. Option B)
- When a fast deliverable is needed (e.g., an upcoming presentation or panel):
  - **Keep the experiment self-contained (Option A)**: Place exploratory calculation scripts in `docs/experiments/<topic>/` (even when querying `cscm.broker`). This keeps `src/` clean of premature abstractions.
  - **Schedule deep unification on the backlog**: Do not commit half-landed duplicates to `src/` under time pressure. Land them properly via a dedicated model refactoring track (Option B).
