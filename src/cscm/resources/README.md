# Coastal Spatial Resources & Location Registries

This directory contains standardized geographic and nautical registries used by the Coastal Swim Current Model (CSCM) to generate alongshore tidal interpolation models, swim current profiles, and safety analytics.

## Naming Convention

Location registries follow the standardized pattern:
```
{country-code}-{region-label}-locations.yaml
```

Examples:
* `be-full-coast-locations.yaml`: Complete 66.5 km Belgian North Sea coastline (De Panne to Het Zwin).
* `nl-zeeland-locations.yaml`: (Future extension) Zeeland coastal and delta waters.
* `fr-opal-coast-locations.yaml`: (Future extension) Côte d'Opale (Bray-Dunes to Cap Gris-Nez).

*(For backward compatibility with existing profile generators, `be_lifeguard_posts.yaml` is provided as a symlink to `be-full-coast-locations.yaml`).*

---

## Schema Overview

A location registry YAML file consists of five standardized root sections:

```yaml
metadata:
  country_code: "BE"
  region: "Flemish North Sea Coast"
  timezone: "Europe/Brussels"
  seaward_bearing_deg: 335.0         # Default seaward normal (degrees compass)
  tidal_cycle_hours: 12.42           # M2 tidal cycle duration (12h 25m)
  total_chainage_km: 66.0
  chainage_step_m: 750

water_level_stations:
  # MDK / Rijkswaterstaat / SHOM tide gauge reference stations
  <station_id>:
    station_code: "OST"
    name: "Oostende Haven / Staketsel"
    chainage_km: 31.5
    lat: 51.2333
    lon: 2.9167
    api_endpoint: "..."
    params: { ... }

landmarks:
  # Prominent visual landmarks, lighthouses, pier structures, and harbor transits
  - name: "Wenduine De Spioenkop"
    type: "uitkijkpunt"              # monument | architectuur | erfgoed | haven_transitie | natuur | grens
    chainage_km: 45.0
    lat: 51.3030
    lon: 3.0805
    description: "Wit paviljoentje op de hoge duin (31m TAW) / primair zeebaken"

chainage_750m:
  # 1D alongshore polyline backbone discretized at regular swimmer-pace intervals
  - marker: "0k750"
    chainage_km: 0.75
    lat: 51.094
    lon: 2.5543
    nearest_cmems_cell: "cell_68_28" # Nearest offshore pure-water CMEMS hydrodynamic cell
    cmems_dist_m: 1687.0

municipalities:
  # Administrative coastal units and their active lifeguard rescue stations (IKWV)
  <municipality_key>:
    name: "Bredene"
    water_level_station: "oostende"
    seaward_bearing_deg: 335.0
    posts:
      post_4:
        code: "4"
        name: "Bredene - Post 4 (Droogen Opganck)"
        description: "Strand Bredene / De Droge Opgang - K. Astridlaan"
        lat: 51.2548
        lon: 2.9724
        guarded_zone_m: 240
        chainage_km: 35.25
        nearest_marker: "35k250"
        nearest_cmems_cell: "cell_81_40"
        is_hp: false                 # First aid station (Hulppost / Rode Kruis)
        season: "01/07-31/08"
        is_default_benchmark: true
```

---

## Alongshore Backbone & Extrapolation / Interpolation

The `chainage_750m` nodes form the spatial curve coordinate $s \in [0.0, 66.5\text{ km}]$ along the coastline:
1. **$0.0 - 15.0\text{ km}$ (De Panne to Nieuwpoort)**: Extrapolated westward from Nieuwpoort tide gauge towards the French border.
2. **$15.0 - 53.25\text{ km}$ (Nieuwpoort through Oostende to Zeebrugge)**: Interpolated between active primary tide gauges.
3. **$53.25 - 66.5\text{ km}$ (Zeebrugge to Het Zwin)**: Extrapolated eastward towards Cadzand and the Western Scheldt mouth.
