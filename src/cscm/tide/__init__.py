"""
CSCM Tide Module for coastal water levels, regional models, and gauge networks.

Re-exports Belgian regional models and clients (MDK, HIC) from cscm.tide.be
for backward compatibility.
"""

from cscm.tide.be import (
    AlongshoreTidalModel,
    COASTAL_TIDE_STATIONS,
    HIC_COASTAL_STATIONS,
    HicClient,
    HicStation,
    InterpolatedTidePoint,
    MdkClient,
    MdkStation,
)

__all__ = [
    "MdkClient",
    "MdkStation",
    "COASTAL_TIDE_STATIONS",
    "HicClient",
    "HicStation",
    "HIC_COASTAL_STATIONS",
    "AlongshoreTidalModel",
    "InterpolatedTidePoint",
]
