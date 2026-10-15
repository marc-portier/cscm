# Coastal Swim Trajectory Profile Design Evolution (Graphics Changelog)

This document tracks the evolution of the **Coastal Swim Trajectory Profile** in `docs/experiments/graphics/kust-zwem-profiel/`.

---

### Version Overview

| Version | Source Files (in `./hist/`) | Key Features & Architectural Changes |
| :--- | :--- | :--- |
| **v0** | `ontwerp-kustzwem-profiel-v0.png` | **Original Hand Sketch by Marc Portier**: Conceptual space-time diagram featuring fixed 750m distance checkpoints and vertically shifted tidal fishbone spines matching swimmer checkpoint arrival times. Three swimmer pace scenarios (blue, green, orange). |
| **v1** | `generate_v1.py`<br>`ontwerp-kustzwem-profiel-v1.svg`<br>`ontwerp-kustzwem-profiel-v1.png` | **First Digital Vector Prototype**: <br>• 5 checkpoints at 750m intervals (0.0k to 3.0k: Bredene Post 4 ➔ De Haan).<br>• Vertical fishbone spines per checkpoint with hydrodynamic vectors (flood right, ebb left, slack green).<br>• Horizontal green baseline representing the reference swimmer (1.0 m/s cruise pace).<br>• Angled trajectory lines for faster swimmers (blue, rising = earlier) and recreational swimmers (orange, declining = later).<br>• Timing summary cards below each checkpoint.<br>• 100% vector SVG and high-resolution PNG preview. |
| **v2** | *(Parked in Backlog)* | **Isotach Mesh, Isochrones & Scalability (Design Vision)**: <br>• **Decoupled Distance Axis**: Clean metric distance ticks (`0k0`, `0k75`, `1k5`, `2k25`, ... rotated 90°), decoupled from arbitrary lifeguard post numbers.<br>• **Top Coastal Landmark Banner**: Overarching top strip mapping physical coastal landmarks (piers, harbour channels of Nieuwpoort, Oostende, Blankenberge, Zeebrugge).<br>• **Isotach Contours (Velocity Mesh)**: Smooth spectral mesh (0.1 m/s intervals from 0.5 to 1.5 m/s) centered on the swimmer's target pace ($v_0 \pm 0.5\text{ m/s}$).<br>• **Isochrones (Time Contours)**: Thin 15-minute time curves (`HH:MM`) traversing the shifted spines, directly illustrating space-time arrival without bulky tables.<br>• **Out-and-Back Support**: Horizontal folding/mirroring of the return leg on the right.<br>• **Scalability**: Flexible distance layout accommodating 3–5 km training swims up to 16 km, 20 km, or full 67 km Belgian coast swims (*Ommeweg vzw*). |

---

### Active Canonical Files & `./latest` Symlinks
The active version (currently equivalent to **v1**) is accessible in:
- Directory: [`../latest/`](../latest/)
  - `ontwerp-kustzwem-profiel.svg` -> `../hist/ontwerp-kustzwem-profiel-v1.svg`
  - `ontwerp-kustzwem-profiel-preview.png` -> `../hist/ontwerp-kustzwem-profiel-v1.png`
