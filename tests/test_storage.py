"""
Unit tests for AbstractDataStoreManager and CatalogEntry in cscm.storage.
"""

from datetime import datetime, timezone, timedelta
import os
from pathlib import Path
import pytest

from cscm.storage.base import AbstractDataStoreManager, CatalogEntry


class DummyStoreManager(AbstractDataStoreManager):
    env_var_name = "DUMMY_DATA_FOLDER"
    default_subfolder_name = "dummy_store"

    def retrieve(self, *args, **kwargs):
        return "retrieved"


def test_catalog_entry_coverage_and_serialization():
    t0 = datetime(2026, 10, 20, 10, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 10, 20, 18, 0, tzinfo=timezone.utc)

    entry = CatalogEntry(
        file_name="test_data.nc",
        start_dt=t0,
        end_dt=t1,
        is_forecast=True,
        metadata={"model": "test_v1"}
    )

    # Full coverage
    assert entry.covers(t0, t1)
    assert entry.covers(t0 + timedelta(hours=1), t1 - timedelta(hours=1))
    assert not entry.covers(t0 - timedelta(hours=1), t1)

    # Overlaps
    assert entry.overlaps(t0 - timedelta(hours=2), t0 + timedelta(hours=1))
    assert entry.overlaps(t1 - timedelta(hours=1), t1 + timedelta(hours=2))
    assert not entry.overlaps(t1 + timedelta(hours=1), t1 + timedelta(hours=2))

    # Serialization roundtrip
    d = entry.to_dict()
    assert d["file_name"] == "test_data.nc"
    assert d["is_forecast"] is True
    reconstructed = CatalogEntry.from_dict(d)
    assert reconstructed.file_name == entry.file_name
    assert reconstructed.start_dt == entry.start_dt
    assert reconstructed.end_dt == entry.end_dt
    assert reconstructed.metadata == entry.metadata


def test_data_store_manager_folder_resolution(tmp_path, monkeypatch):
    # 1. Explicit folder
    explicit_dir = tmp_path / "explicit"
    mgr1 = DummyStoreManager(data_folder=explicit_dir)
    assert mgr1.data_folder == explicit_dir
    assert explicit_dir.exists()

    # 2. Subsystem env var
    subsystem_dir = tmp_path / "from_env"
    monkeypatch.setenv("DUMMY_DATA_FOLDER", str(subsystem_dir))
    mgr2 = DummyStoreManager()
    assert mgr2.data_folder == subsystem_dir
    assert subsystem_dir.exists()

    # 3. Global env var
    monkeypatch.delenv("DUMMY_DATA_FOLDER")
    global_dir = tmp_path / "global"
    monkeypatch.setenv("CSCM_DATA_FOLDER", str(global_dir))
    mgr3 = DummyStoreManager()
    assert mgr3.data_folder == global_dir / "dummy_store"
    assert (global_dir / "dummy_store").exists()


def test_catalog_lifecycle_and_status(tmp_path):
    mgr = DummyStoreManager(data_folder=tmp_path)
    assert mgr.get_catalog() == []

    # Status on empty
    st0 = mgr.status()
    assert st0["total_entries"] == 0
    assert st0["earliest_dt"] is None

    # Register entries
    t0 = datetime(2026, 10, 20, 8, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 10, 20, 14, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 10, 21, 8, 0, tzinfo=timezone.utc)

    e1 = CatalogEntry("file_1.nc", t0, t1, is_forecast=False)
    e2 = CatalogEntry("file_2.nc", t1, t2, is_forecast=True)

    # Create dummy files
    (tmp_path / "file_1.nc").write_text("hello 1")
    (tmp_path / "file_2.nc").write_text("hello 2")

    mgr.register_entry(e1)
    mgr.register_entry(e2)

    assert len(mgr.get_catalog(force_reload=True)) == 2

    # Query covering files
    overlapping = mgr.find_covering_files(t0 + timedelta(hours=2), t1 + timedelta(hours=1))
    assert len(overlapping) == 2

    # Check status
    st = mgr.status()
    assert st["total_entries"] == 2
    assert st["forecast_entries"] == 1
    assert st["earliest_dt"] == t0.isoformat()
    assert st["latest_dt"] == t2.isoformat()

    # Remove entry
    assert mgr.remove_entry("file_1.nc", delete_file=True)
    assert not (tmp_path / "file_1.nc").exists()
    assert len(mgr.get_catalog()) == 1

    # Inspect test
    insp = mgr.inspect()
    assert insp["manager"] == "DummyStoreManager"
    assert "storage_status" in insp