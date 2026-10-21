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
    HicTideManager,
    InterpolatedTidePoint,
    MdkClient,
    MdkStation,
    MdkTideManager,
)

__all__ = [
    "MdkClient",
    "MdkStation",
    "MdkTideManager",
    "COASTAL_TIDE_STATIONS",
    "HicClient",
    "HicStation",
    "HicTideManager",
    "HIC_COASTAL_STATIONS",
    "AlongshoreTidalModel",
    "InterpolatedTidePoint",
]