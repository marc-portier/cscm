"""
CSCM Moon Data Store Manager.

Encapsulates NASA JPL Ephemeris files (e.g. de421.bsp) and Skyfield timescale data
inside a managed data_store folder, preventing root repository pollution.
"""

from datetime import datetime, timezone
import logging
from pathlib import Path
import shutil
from typing import Optional, Union

from skyfield.api import Loader

from cscm.commons import singleton
from cscm.storage.base import AbstractDataStoreManager, CatalogEntry

log = logging.getLogger(__name__)


@singleton
class MoonDataManager(AbstractDataStoreManager):
    """
    Manages local caching and access for astronomical ephemeris and timescale data.
    Decorated with @singleton to prevent multiple Loader instances.
    """
    env_var_name = "MOON_DATA_FOLDER"
    default_subfolder_name = "data_store"

    def __init__(self, data_folder: Optional[Union[str, Path]] = None):
        super().__init__(data_folder=data_folder)
        self.loader = Loader(str(self.data_folder))
        self._check_root_migration()

    def _check_root_migration(self) -> None:
        """
        Migrate legacy de421.bsp from project root to the managed storage folder
        if present in root and missing in storage folder.
        """
        root_bsp = Path.cwd() / "de421.bsp"
        dest_bsp = self.data_folder / "de421.bsp"
        if root_bsp.exists() and not dest_bsp.exists():
            log.info(f"Migrating {root_bsp} into managed store {dest_bsp}")
            try:
                shutil.copy2(root_bsp, dest_bsp)
            except Exception as e:
                log.warning(f"Failed to copy de421.bsp to {dest_bsp}: {e}")

        # Register de421.bsp in catalog if file exists
        if dest_bsp.exists():
            catalog = self.get_catalog()
            if not any(e.file_name == "de421.bsp" for e in catalog):
                entry = CatalogEntry(
                    file_name="de421.bsp",
                    start_dt=datetime(1900, 1, 1, tzinfo=timezone.utc),
                    end_dt=datetime(2050, 12, 31, 23, 59, 59, tzinfo=timezone.utc),
                    is_forecast=False,
                    file_hash=self.compute_file_hash(dest_bsp),
                    metadata={"description": "NASA JPL Planetary and Lunar Ephemeris DE421"},
                )
                self.register_entry(entry)

    def retrieve(self, filename: str = "de421.bsp", force: bool = False, **kwargs) -> Path:
        """
        Download or load the ephemeris kernel into managed data storage.
        """
        target_path = self.data_folder / filename
        if not target_path.exists() or force:
            self.loader(filename)

        if target_path.exists():
            entry = CatalogEntry(
                file_name=filename,
                start_dt=datetime(1900, 1, 1, tzinfo=timezone.utc),
                end_dt=datetime(2050, 12, 31, 23, 59, 59, tzinfo=timezone.utc),
                is_forecast=False,
                file_hash=self.compute_file_hash(target_path),
                metadata={"description": f"Astronomical data file {filename}"},
            )
            self.register_entry(entry)

        return target_path

    def get_ephemeris(self, filename: str = "de421.bsp"):
        """Load and return the Skyfield ephemeris kernel."""
        return self.loader(filename)

    def get_timescale(self):
        """Load and return the Skyfield timescale."""
        return self.loader.timescale()

    def inspect(self) -> dict:
        """Returns architectural inspection metadata for moon / ephemeris data store."""
        return {
            "manager": self.__class__.__name__,
            "data_folder": str(self.data_folder),
            "catalog_path": str(self.catalog_path),
            "storage_status": self.status(),
        }


# Domain-specific alias
MoonPhaseDataManager = MoonDataManager