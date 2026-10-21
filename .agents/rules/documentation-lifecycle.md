# Documentation Structure & Lifecycle Policy

## Overview
All documentation in `docs/` is public-facing repository documentation and MUST be written in **English (EN)**. The documentation architecture distinguishes clearly between strategic planning, exploratory prototyping, and user/developer usage guides.

---

## 1. Documentation Structure & Roles

### `docs/plans.md` & `docs/history.md` (Strategy & Tracking)
* **`plans.md`**: Main operational roadmap, milestones, and the active consolidated backlog table (`BL-*`). Every new feature or architectural track must have an assigned backlog item.
* **`history.md`**: Chronological record of major completed milestones and breakthroughs.
* **Sub-Plans** (e.g. `docs/2026-10-20-refactoring-subplan.md`): Deep technical architecture documents linking specific backlog epics to implementation phases.

### `docs/experiments/` (Exploration & Design Evolution)
* **Purpose**: Serves as a sandbox and preview for upcoming features and visualizations being actively explored (e.g., in `docs/experiments/graphics/`).
* **Index Upkeep (`docs/experiments/README.md`)**:
  * Must maintain a comprehensive markdown table of all available experiments, sorted by **Start Date descending**:
    * **Name**: Double as a relative link to the nested folder.
    * **Purpose / Goal**: Concise 1–2 sentence description.
    * **Status**: `Active`, `Completed`, `Stalled`, or `Superseded`.
    * **Dates**: `Start Date` and `End Date` (or `Ongoing`).
    * **Demo Link**: Direct link to the matching user guide in `docs/demos/` once landed.
* **Landing Lifecycle**:
  * Once an experimental feature is implemented into the core library (`src/cscm/`), its experimental folder is preserved as a "how we got there" design narrative and historical record.
  * The experiment page must then include a prominent cross-link to the production usage guide in `docs/demos/`.

### `docs/demos/` (Production User & Developer Guides)
* **Purpose**: Provides atomic, reference-grade usage documentation showcasing library features, intended for external users and developers integrating `cscm`.
* **Standard Content per Demo**:
  * Practical CLI usage examples (`python -m cscm...`).
  * Self-contained Python code snippets.
  * Required environment variables (`.env`) and CLI arguments.
  * Visual previews (rendered SVGs/PNGs) or sample terminal outputs showing the expected results.

---

## 2. Maintenance & Synchronization Rule
* Whenever an experiment is initiated, updated, or completed, its entry in `docs/experiments/README.md` must be updated immediately.
* Whenever a backlog issue lands in core, the agent and user should proactively prepare or plan its corresponding atomic guide under `docs/demos/`.
