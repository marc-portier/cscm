"""Belgian coastal tidal hydrodynamics, gauge networks, and alongshore models."""

from cscm.tide.be.alongshore import AlongshoreTidalModel, InterpolatedTidePoint
from cscm.tide.be.hic import HIC_COASTAL_STATIONS, HicClient, HicStation
from cscm.tide.be.mdk import COASTAL_TIDE_STATIONS, MdkClient, MdkStation

__all__ = [
    "AlongshoreTidalModel",
    "InterpolatedTidePoint",
    "HicClient",
    "HicStation",
    "HIC_COASTAL_STATIONS",
    "MdkClient",
    "MdkStation",
    "COASTAL_TIDE_STATIONS",
]
