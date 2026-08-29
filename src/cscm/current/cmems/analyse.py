# src/cscm/current/cmems/analyse.py

# support for analysis of Copernicus CMEMS data
# ideas:

#  - general average analysis
#    - compute average current over the area - extract time-series for that
#    - detect current-cycles from the data -- actual moments of current reversal -- compute offset with moon-phases and the tidal-average
#    - do a FTT transform on the time-series to get dominant frequencies
#  - extract a time-series for a given point (lat, lon) -- within the bounding box of the data
#    -- do so for different locations, compare phases, amplitudes, main frequencies
#    -- and their own local reversal times and offsets so the moon phases
#  - read metadata on start-end, spatial grid
#  - maintain a catalog of extracted derived info to avoid re-computation
#
