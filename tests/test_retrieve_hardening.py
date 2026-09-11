# tests/test_retrieve_hardening.py

import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone, timedelta
from pathlib import Path
import tempfile
import json
import shutil
import pandas as pd

from cscm.moon.phases import get_newmoon_cycles
from cscm.current.cmems.retrieve import (
    _cmems_start_date,
    _cmems_end_date,
    CMEMSDataManager,
)
from cscm.simulation.__main__ import get_latest_forecast_nc


class TestCMEMSRetrieveHardening(unittest.TestCase):

    def test_cmems_end_date_lookahead(self):
        """Verify _cmems_end_date looks ahead at least 35 days."""
        now_utc = datetime.now(timezone.utc)
        end_dt = _cmems_end_date()
        self.assertGreaterEqual(end_dt, now_utc + timedelta(days=34))

    def test_newmoon_cycle_detection_on_new_moon(self):
        """Verify that with the 35d lookahead, the active lunar cycle starting on 2026-09-11 is captured."""
        start_date = datetime(2026, 8, 1, tzinfo=timezone.utc)
        now_dt = datetime(2026, 9, 11, 7, 30, tzinfo=timezone.utc)
        end_date = now_dt + timedelta(days=35)
        cycles = get_newmoon_cycles(start_date, end_date)

        # The new moon occurred on 2026-09-11 at ~03:26 UTC.
        # It must be present as a cycle start date in the returned cycles.
        cycle_starts = [c[0].strftime("%Y-%m-%d") for c in cycles]
        self.assertIn("2026-09-11", cycle_starts)

    def test_historic_complete_saturation(self):
        """Verify that a cycle that has reached its trailing 5-day cap is marked complete."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = CMEMSDataManager(storage_folder=Path(tmpdir))

            # Simulate a cycle: 2026-08-12 to 2026-09-11
            nwmn_start = datetime(2026, 8, 12, 17, 36, tzinfo=timezone.utc)
            nwmn_end = datetime(2026, 9, 11, 3, 26, tzinfo=timezone.utc)
            mc = (nwmn_start, nwmn_end, 29.4, 12.4)

            dummy_nc = Path(tmpdir) / "test_data.nc"
            dummy_nc.write_text("dummy")

            # Mock _download_cmems_data to return data covering up to nwmn_end + 5 days (2026-09-16)
            mock_meta = {
                "data_file": str(dummy_nc),
                "data_size": 1000,
                "data_variables": ["uo", "vo"],
                "data_geo_extent": [
                    MagicMock(minimum=50.0, maximum=52.0),
                    MagicMock(minimum=0.0, maximum=3.0),
                ],
                "data_time_extent": MagicMock(
                    minimum="2026-08-10T00:00:00+00:00",
                    maximum="2026-09-16T00:00:00+00:00",
                ),
                "data_status": "000",
            }

            with patch.object(manager, "_download_cmems_data", return_value=mock_meta):
                metadict = manager.add_cmems_data_to_catalog(mc)

            # Since now >= nwmn_end (2026-09-11) and actual_end >= 2026-09-16, historic_complete should be True
            self.assertTrue(metadict["historic_complete"])

    def test_non_destructive_update_retains_files_on_failure(self):
        """Verify that when a download fails during update_cmems_data, existing files are NOT deleted."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir)
            manager = CMEMSDataManager(storage_folder=storage_path)

            # Create existing data and metadata files
            existing_nc = storage_path / "cmems_cycle.nc"
            existing_nc.write_text("existing netcdf content")
            existing_json = storage_path / "cmems_cycle.json"

            nwmn_start = datetime(2026, 8, 12, 17, 36, tzinfo=timezone.utc)
            nwmn_end = datetime(2026, 9, 11, 3, 26, tzinfo=timezone.utc)

            metadata_content = {
                "data_start_dt": "2026-08-10T00:00:00+00:00",
                "data_end_dt": "2026-09-15T00:00:00+00:00",
                "nwmn_start_dt": nwmn_start.isoformat(),
                "nwmn_end_dt": nwmn_end.isoformat(),
                "lunarperiod_d": 29.4,
                "tidalperiod_h": 12.4,
                "metadata_file": str(existing_json),
                "data_file": str(existing_nc),
                "data_size": 100,
                "data_variables": "uo, vo",
                "data_geo_extent": "0, 3, 50, 52",
                "data_status": "000",
                "historic_complete": False,  # Triggers update attempt
            }
            with open(existing_json, "w") as f:
                json.dump(metadata_content, f)

            manager.init_catalog()
            self.assertEqual(len(manager.catalog), 1)

            # Simulate download failure
            with patch.object(manager, "add_cmems_data_to_catalog", side_effect=ConnectionError("S3 timeout")):
                success = manager.update_cmems_data(
                    start_date=datetime(2026, 8, 1),
                    end_date=datetime(2026, 9, 15),
                )

            self.assertFalse(success)
            # CRITICAL CHECK: Existing files must still exist on disk!
            self.assertTrue(existing_nc.exists(), "Existing .nc file was erroneously deleted on failure!")
            self.assertTrue(existing_json.exists(), "Existing .json metadata was erroneously deleted on failure!")
            self.assertEqual(len(manager.catalog), 1, "Catalog row was erroneously dropped on failure!")

    def test_retry_mechanism_in_download(self):
        """Verify _download_cmems_data retries on transient errors and succeeds."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir)
            manager = CMEMSDataManager(storage_folder=storage_path)

            mock_response = MagicMock()
            mock_response.file_path = str(storage_path / ".staging" / "test.nc")
            mock_response.file_size = 500
            mock_response.variables = ["uo", "vo"]
            mock_response.status = "000"

            import copernicusmarine as cmems
            lat_ext = cmems.GeographicalExtent(coordinate_id="latitude", minimum=50.0, maximum=52.0, unit="degrees_north")
            lon_ext = cmems.GeographicalExtent(coordinate_id="longitude", minimum=0.0, maximum=3.0, unit="degrees_east")
            time_ext = cmems.TimeExtent(coordinate_id="time", minimum="2026-09-01T00:00:00+00:00", maximum="2026-09-07T00:00:00+00:00", unit="seconds")
            mock_response.coordinates_extent = [lat_ext, lon_ext, time_ext]

            # Write staging file so move succeeds
            staging_dir = storage_path / ".staging"
            staging_dir.mkdir(parents=True, exist_ok=True)
            Path(mock_response.file_path).write_text("data")

            # Fail twice, succeed on 3rd attempt
            with patch("copernicusmarine.subset", side_effect=[IOError("504"), IOError("reset"), mock_response]):
                result = manager._download_cmems_data(
                    datetime(2026, 9, 1),
                    datetime(2026, 9, 7),
                    retries=3,
                    retry_delay=0.01,
                )

            self.assertEqual(result["data_file"], str(storage_path / "test.nc"))
            self.assertTrue((storage_path / "test.nc").exists())

    def test_get_latest_forecast_nc_ignores_staging(self):
        """Verify get_latest_forecast_nc ignores hidden and .staging files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dir_path = Path(tmpdir)
            staging = dir_path / ".staging"
            staging.mkdir()
            (staging / "staged_2026-09-20.nc").write_text("tmp")
            (dir_path / ".hidden.nc").write_text("tmp")
            valid_file = dir_path / "cmems_2026-09-10-2026-09-16.nc"
            valid_file.write_text("valid")

            latest = get_latest_forecast_nc(dir_path)
            self.assertEqual(latest, valid_file)


if __name__ == "__main__":
    unittest.main()
