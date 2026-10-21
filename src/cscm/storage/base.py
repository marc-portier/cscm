"""
Abstract Data Store Manager & Catalog Manifest.

Establishes a unified base for caching raw upstream payloads, tracking temporal
coverage in standardized `catalog.json` manifests, and providing zero-conf
directory resolution with environment variable overrides.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import sys
from typing import Optional, List, Dict, Any, Union

log = logging.getLogger(__name__)


def _to_utc(dt: datetime) -> datetime:
    """Ensure datetime has timezone UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


@dataclass
class CatalogEntry:
    """
    Metadata describing a cached data file.
    All datetimes are strictly stored and serialized in UTC ISO-8601 format.
    """
    file_name: str
    start_dt: datetime
    end_dt: datetime
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    is_forecast: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)
    file_hash: Optional[str] = None

    def __post_init__(self):
        self.start_dt = _to_utc(self.start_dt)
        self.end_dt = _to_utc(self.end_dt)
        self.retrieved_at = _to_utc(self.retrieved_at)

    def covers(self, query_start: datetime, query_end: datetime) -> bool:
        """Returns True if this file fully covers the requested query window."""
        q_start = _to_utc(query_start)
        q_end = _to_utc(query_end)
        return self.start_dt <= q_start and self.end_dt >= q_end

    def overlaps(self, query_start: datetime, query_end: datetime) -> bool:
        """Returns True if this file overlaps with the requested query window."""
        q_start = _to_utc(query_start)
        q_end = _to_utc(query_end)
        return max(self.start_dt, q_start) <= min(self.end_dt, q_end)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize entry to dictionary with ISO-formatted timestamps."""
        return {
            "file_name": self.file_name,
            "start_dt": self.start_dt.isoformat(),
            "end_dt": self.end_dt.isoformat(),
            "retrieved_at": self.retrieved_at.isoformat(),
            "is_forecast": self.is_forecast,
            "metadata": self.metadata,
            "file_hash": self.file_hash,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CatalogEntry":
        """Deserialize entry from dictionary."""
        return cls(
            file_name=data["file_name"],
            start_dt=datetime.fromisoformat(data["start_dt"]),
            end_dt=datetime.fromisoformat(data["end_dt"]),
            retrieved_at=datetime.fromisoformat(data.get("retrieved_at", datetime.now(timezone.utc).isoformat())),
            is_forecast=bool(data.get("is_forecast", False)),
            metadata=dict(data.get("metadata", {})),
            file_hash=data.get("file_hash"),
        )


class AbstractDataStoreManager(ABC):
    """
    Abstract base class for all physical data store managers (CMEMS, HIC, MDK, Moon).
    
    Resolution Order for Storage Directory:
    1. Explicit `data_folder` passed to __init__.
    2. Subsystem environment variable (defined by `env_var_name`, e.g. `CMEMS_DATA_FOLDER`).
    3. Global environment variable `CSCM_DATA_FOLDER` / `default_subfolder_name`.
    4. Default local `./data_store/` directory adjacent to the concrete subclass module file.
    """

    env_var_name: Optional[str] = None
    default_subfolder_name: str = "data_store"

    def __init__(self, data_folder: Optional[Union[str, Path]] = None):
        self._data_folder = self._resolve_data_folder(data_folder)
        self._data_folder.mkdir(parents=True, exist_ok=True)
        self._catalog_cache: Optional[List[CatalogEntry]] = None

    @property
    def data_folder(self) -> Path:
        """The absolute path to the managed local data directory."""
        return self._data_folder

    @property
    def catalog_path(self) -> Path:
        """The path to the catalog.json manifest file."""
        return self._data_folder / "catalog.json"

    def _resolve_data_folder(self, explicit_folder: Optional[Union[str, Path]]) -> Path:
        """Resolves the active storage folder following the precedence hierarchy."""
        # 1. Explicit argument
        if explicit_folder is not None:
            return Path(explicit_folder).resolve()

        # 2. Specific environment variable
        if self.env_var_name:
            env_val = os.environ.get(self.env_var_name)
            if env_val:
                return Path(env_val).resolve()

        # 3. Global environment variable
        global_env = os.environ.get("CSCM_DATA_FOLDER")
        if global_env:
            return (Path(global_env) / self.default_subfolder_name).resolve()

        # 4. Zero-conf default: ./data_store relative to the subclass module file
        subclass_file = sys.modules[self.__class__.__module__].__file__
        if subclass_file:
            subclass_dir = Path(subclass_file).parent
            return (subclass_dir / self.default_subfolder_name).resolve()

        # Fallback to current working directory
        return (Path.cwd() / self.default_subfolder_name).resolve()

    def get_catalog(self, force_reload: bool = False) -> List[CatalogEntry]:
        """Loads and returns the list of catalog entries from catalog.json."""
        if self._catalog_cache is not None and not force_reload:
            return self._catalog_cache

        if not self.catalog_path.exists():
            self._catalog_cache = []
            return self._catalog_cache

        try:
            with open(self.catalog_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            entries = [CatalogEntry.from_dict(item) for item in data.get("entries", [])]
            self._catalog_cache = entries
            return self._catalog_cache
        except Exception as e:
            log.warning(f"Failed to read catalog at {self.catalog_path}: {e}. Initializing empty catalog.")
            self._catalog_cache = []
            return self._catalog_cache

    def save_catalog(self, entries: List[CatalogEntry]) -> None:
        """Atomically saves the catalog entries to catalog.json."""
        self._catalog_cache = entries
        catalog_dict = {
            "version": "1.0",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "entries": [entry.to_dict() for entry in entries]
        }

        temp_path = self.catalog_path.with_suffix(".tmp")
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(catalog_dict, f, indent=2)
        temp_path.replace(self.catalog_path)

    def register_entry(self, entry: CatalogEntry) -> None:
        """Adds or updates a catalog entry keyed by its file_name."""
        catalog = self.get_catalog()
        updated = [e for e in catalog if e.file_name != entry.file_name]
        updated.append(entry)
        # Keep entries sorted chronologically by start_dt
        updated.sort(key=lambda x: x.start_dt)
        self.save_catalog(updated)

    def remove_entry(self, file_name: str, delete_file: bool = True) -> bool:
        """Removes a file from the catalog and optionally deletes it from disk."""
        catalog = self.get_catalog()
        initial_len = len(catalog)
        updated = [e for e in catalog if e.file_name != file_name]
        if len(updated) != initial_len:
            self.save_catalog(updated)
            if delete_file:
                target_file = self.data_folder / file_name
                if target_file.exists():
                    target_file.unlink()
            return True
        return False

    def find_covering_files(self, start_dt: datetime, end_dt: datetime) -> List[CatalogEntry]:
        """Finds all catalog entries whose time window overlaps with the requested window."""
        catalog = self.get_catalog()
        return [entry for entry in catalog if entry.overlaps(start_dt, end_dt)]

    def compute_file_hash(self, file_path: Union[str, Path]) -> str:
        """Computes SHA-256 hash of a local file."""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    def status(self) -> Dict[str, Any]:
        """
        Returns a concise operational status report of this data store:
        time bounds, entry counts, forecast files, and disk size.
        """
        catalog = self.get_catalog(force_reload=True)
        total_size = sum(
            (self.data_folder / e.file_name).stat().st_size
            for e in catalog
            if (self.data_folder / e.file_name).exists()
        )
        if not catalog:
            return {
                "manager": self.__class__.__name__,
                "data_folder": str(self.data_folder),
                "catalog_path": str(self.catalog_path),
                "total_entries": 0,
                "total_size_bytes": total_size,
                "earliest_dt": None,
                "latest_dt": None,
                "forecast_entries": 0,
                "stale_forecast_entries": 0,
            }

        start_times = [e.start_dt for e in catalog]
        end_times = [e.end_dt for e in catalog]
        now_utc = datetime.now(timezone.utc)
        forecast_count = sum(1 for e in catalog if e.is_forecast)
        stale_count = sum(1 for e in catalog if e.is_forecast and e.end_dt < now_utc)

        return {
            "manager": self.__class__.__name__,
            "data_folder": str(self.data_folder),
            "catalog_path": str(self.catalog_path),
            "total_entries": len(catalog),
            "total_size_bytes": total_size,
            "earliest_dt": min(start_times).isoformat(),
            "latest_dt": max(end_times).isoformat(),
            "forecast_entries": forecast_count,
            "stale_forecast_entries": stale_count,
        }

    def inspect(self) -> Dict[str, Any]:
        """
        Returns architectural inspection metadata for this data store manager,
        combining storage statistics with manager identity.
        """
        return {
            "manager": self.__class__.__name__,
            "data_folder": str(self.data_folder),
            "catalog_path": str(self.catalog_path),
            "storage_status": self.status(),
        }

    @abstractmethod
    def retrieve(self, *args, **kwargs) -> Any:
        """Fetch or synchronize data from upstream provider into the managed data store."""
        pass