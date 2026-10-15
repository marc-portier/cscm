"""CSCM Tide Module for Flemish coastal water levels, MDK sensors, and HIC predictions."""

from cscm.tide.mdk import MdkClient, MdkStation, COASTAL_TIDE_STATIONS
from cscm.tide.hic import HicClient, HicStation, HIC_COASTAL_STATIONS

__all__ = [
    "MdkClient",
    "MdkStation",
    "COASTAL_TIDE_STATIONS",
    "HicClient",
    "HicStation",
    "HIC_COASTAL_STATIONS",
]
