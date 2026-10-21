"""
CSCM Physical Storage & Caching Layer.

Provides abstract data store managers, catalog manifests, and zero-conf
directory resolution with environment variable overrides.
"""

from .base import AbstractDataStoreManager, CatalogEntry

__all__ = ["AbstractDataStoreManager", "CatalogEntry"]
