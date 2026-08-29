# src/cscm/current/cmems/retrieve.py

from cscm.moon.phases import get_newmoon_cycles, Mooncycle
from datetime import datetime, timedelta, timezone
from pathlib import Path
import os
import json
import pandas as pd
import copernicusmarine as cmems

# ✅ manage gets in a local data folder >> do not get what you already have (unless it was incomplete)
# ✅ get current_vector(time,x,y) data between dates >> group downloads from new moon to new moon
# ✅ > margin with two days extra on both sides
# ✅ keep catalog / metadata of the cycles we have: update-time, start, end, lunar-cycle-info, ...
# mark datasets that have predictive data >> so we do remove and update those in later runs


def _cmems_storage_folder() -> Path:
    """
    Returns the path to the local storage folder for Copernicus CMEMS data.
    Fallback mechanism:
    - If the environment variable 'CMEMS_DATA_FOLDER' is set, use that as the storage folder.
    - Otherwise, use the default folder './data_store/' relative to this __file__
    """
    cmems_data_folder = os.environ.get('CMEMS_DATA_FOLDER')
    if cmems_data_folder:
        cmems_storage_folder = Path(cmems_data_folder)
    else:
        cmems_storage_folder = Path(__file__).parent / "data_store"

    cmems_storage_folder.mkdir(parents=True, exist_ok=True)
    return cmems_storage_folder


def _cmems_start_date() -> datetime:
    """
    Returns the start date for Copernicus CMEMS data retrieval.
    Fallback mechanism:
    - If the environment variable 'CMEMS_START_DATE' is set, use that as the start date.
    - Otherwise, use the default start date of Sept 1, 2024.
    """
    cmems_start_date_str = os.environ.get('CMEMS_START_DATE')
    if cmems_start_date_str:
        return datetime.fromisoformat(cmems_start_date_str)
    else:
        return datetime(2024, 9, 1)


def _cmems_max_date() -> datetime:
    """
    Returns the maximum date for Copernicus CMEMS data retrieval.
    This is 7 days from `now()` (in UTC time, rounded to the start of the day)
    """
    return datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=7)


def _cmems_end_date() -> datetime:
    """
    Returns the end date for Copernicus CMEMS data retrieval.
    Fallback mechanism:
    - If the environment variable 'CMEMS_END_DATE' is set, use that as the end date.
    - Otherwise, use the default end date of Today + 29 days -- to reach up to the next new moon cycle
    """
    cmems_end_date_str = os.environ.get('CMEMS_END_DATE')
    if cmems_end_date_str:
        return datetime.fromisoformat(cmems_end_date_str)
    else:
        return datetime.now(timezone.utc) + timedelta(days=29)


GeoExtent = tuple[float, float, float, float]  # min_lon, max_lon, min_lat, max_lat


def _cmems_geo_extent() -> GeoExtent:
    """
    Returns the geographic extent for Copernicus CMEMS data retrieval.
    Fallback mechanism:
    - If the environment variable 'CMEMS_GEO_EXTENT' is set, use that as the geographic extent.
      The format should be "min_lon,max_lon,min_lat,max_lat".
    - Otherwise, use the default geographic extent of (-180.0, 180.0, -90.0, 90.0).
    """
    cmems_geo_extent_str = os.environ.get('CMEMS_GEO_EXTENT')
    if cmems_geo_extent_str:
        min_lon, max_lon, min_lat, max_lat = map(float, cmems_geo_extent_str.split(','))
        return (min_lon, max_lon, min_lat, max_lat)
    else:
        return (-180.0, 180.0, -90.0, 90.0)


class CMEMSDataManager:
    COLUMNS = [
        "data_start_dt",
        "data_end_dt",
        "nwmn_start_dt",
        "nwmn_end_dt",
        "lunarperiod_d",
        "tidalperiod_h",
        "metadata_file",
        "data_file",
        "data_size",
        "data_variables",
        "data_geo_extent",
        "data_status",
        "historic_complete",
    ]

    """
    Manages the retrieval and storage of Copernicus CMEMS data.
    Maintains an internal catalog of downloaded data to avoid re-downloading.
    Provides methods to download data for specific moon cycles and update the local storage based on new moon cycles.
    """
    def __init__(self, *, storage_folder: Path = None):
        self.storage_folder = storage_folder or _cmems_storage_folder()
        self.geo_extent: GeoExtent = _cmems_geo_extent()
        self.init_catalog()

    def init_catalog(self) -> None:
        # Initialize the catalog of downloaded data
        # glob over the storage folder and read metadata files to build the catalog
        self.catalog: pd.DataFrame = None
        all_md_json: list = []
        for metadata_file in self.storage_folder.glob("*.json"):
            # read metadata file and append to catalog
            with open(metadata_file, "r") as f:
                md_json = json.load(f)
                all_md_json.append(md_json)
        self.catalog = pd.DataFrame(all_md_json, columns=CMEMSDataManager.COLUMNS)

    @staticmethod
    def _metadata_filepath(data_file: Path) -> Path:
        return data_file.with_suffix(".json")

    def _write_metadata_file(self, metadict: dict) -> None:
        """
        Creates a metadata file for the given moon cycle.
        The metadata file location itself is listed in the dict that will contain it.
        """
        metadata_file = Path(metadict["metadata_file"])
        metadict["metadata_file"] = str(metadata_file)  # ensure it's a string path
        metadict["data_file"] = str(metadict["data_file"])  # ensure it's a string path
        with open(metadata_file, "w") as f:
            json.dump(metadict, f, indent=4)

    def _download_cmems_data(self, data_start_dt: datetime, data_end_dt: datetime) -> dict:
        """
        Downloads Copernicus CMEMS data for the given date boundaries and geographic extent.
        The data is stored in the local storage folder, and a metadata file is created to keep track of the downloaded data.
        Filename format as decided by the CMEMS API.
        returns path to the downloaded data file.
        """
        cmems_meta: cmems.ResponseSubset = cmems.subset(
            output_directory=self.storage_folder,
            dataset_id="cmems_mod_nws_phy-cur_anfc_1.5km-2D_PT15M-i",
            dataset_version="202511",
            variables=["uo", "vo"],
            minimum_longitude=self.geo_extent[0],
            maximum_longitude=self.geo_extent[1],
            minimum_latitude=self.geo_extent[2],
            maximum_latitude=self.geo_extent[3],
            start_datetime=data_start_dt.isoformat(),
            end_datetime=data_end_dt.isoformat(),
            coordinates_selection_method="strict-inside",
            netcdf_compression_level=1,
            disable_progress_bar=True,
        )
        lat_extend: cmems.GeographicalExtent = [
            ext for ext in cmems_meta.coordinates_extent
            if isinstance(ext, cmems.GeographicalExtent) and ext.coordinate_id == 'latitude'
        ][0]
        lon_extend: cmems.GeographicalExtent = [
            ext for ext in cmems_meta.coordinates_extent
            if isinstance(ext, cmems.GeographicalExtent) and ext.coordinate_id == 'longitude'
        ][0]
        dt_extend: cmems.TimeExtent = [
            ext for ext in cmems_meta.coordinates_extent
            if isinstance(ext, cmems.TimeExtent)
        ][0]
        return dict(
            data_file=cmems_meta.file_path,
            data_size=cmems_meta.file_size,
            data_variables=cmems_meta.variables,
            data_geo_extent=[lat_extend, lon_extend],
            data_time_extent=dt_extend,
            data_status=cmems_meta.status,
        )

    def add_cmems_data_to_catalog(self, mc: Mooncycle) -> None:
        """
        Adds the Copernicus CMEMS data for the given moon cycle to the catalog.
        uses the _download_cmems_data method to download the data 
        and the _make_metadata_file method to create the metadata file.
        The metadata itself is appended to the internal catalog.
        The actual data is not loaded into memory, only the metadata is kept in the catalog.
        The data-ranges are extended by 2 days on both sides as well as rounded to whole days (UTC) 
        to ensure we have the full data for the moon cycle.
        """
        nwmn_start_dt: datetime = mc[0]
        nwmn_end_dt: datetime = mc[1]
        request_data_start_dt: datetime = (nwmn_start_dt - timedelta(days=2)).replace(hour=0, minute=0, second=0, microsecond=0)
        request_data_end_dt: datetime = (nwmn_end_dt + timedelta(days=2)).replace(hour=0, minute=0, second=0, microsecond=0)
        max_date_end_dt: datetime = _cmems_max_date()
        if request_data_end_dt > max_date_end_dt:
            request_data_end_dt = max_date_end_dt
        cmems_meta: dict = self._download_cmems_data(request_data_start_dt, request_data_end_dt)
        data_file: Path = Path(cmems_meta["data_file"])
        actual_data_start_dt: datetime = cmems_meta["data_time_extent"].minimum
        actual_data_end_dt: datetime = cmems_meta["data_time_extent"].maximum
        now = datetime.now(timezone.utc)
        has_future_data: bool = bool(datetime.fromisoformat(actual_data_end_dt) > now)
        actual_geo_extent: GeoExtent = (
            cmems_meta["data_geo_extent"][1].minimum,  # min_lon
            cmems_meta["data_geo_extent"][1].maximum,  # max_lon
            cmems_meta["data_geo_extent"][0].minimum,  # min_lat
            cmems_meta["data_geo_extent"][0].maximum,  # max_lat
        )

        metadict: dict = dict(
            data_start_dt=actual_data_start_dt,
            data_end_dt=actual_data_end_dt,
            nwmn_start_dt=nwmn_start_dt.isoformat(),
            nwmn_end_dt=nwmn_end_dt.isoformat(),
            lunarperiod_d=mc[2],
            tidalperiod_h=mc[3],
            metadata_file=str(CMEMSDataManager._metadata_filepath(data_file)),
            data_file=str(data_file),
            data_size=cmems_meta["data_size"],
            data_variables=", ".join(cmems_meta["data_variables"]),
            data_geo_extent=", ".join(str(x) for x in actual_geo_extent),
            data_status=cmems_meta["data_status"],
            historic_complete=not has_future_data,
        )
        self._write_metadata_file(metadict)
        self.catalog = pd.concat([self.catalog, pd.DataFrame([metadict], columns=CMEMSDataManager.COLUMNS)], ignore_index=True)

    def update_cmems_date(self, start_date: datetime = None, end_date: datetime = None, force: bool = False) -> None:
        """
        Updates the date range for Copernicus CMEMS data retrieval.
        Checks the current catalog of downloaded data and downloads any missing data for the specified date range.
        If 'force' is True, re-downloads data even if it already exists in the catalog.
        If start_date or end_date are not provided, they will be determined based on the current catalog
        and the default start and end dates.
        """
        start_date = start_date or _cmems_start_date()
        end_date = end_date or _cmems_end_date()

        # Get the new moon cycles between the start and end dates
        newmoon_cycles: list[Mooncycle] = get_newmoon_cycles(start_date, end_date)

        for mc in newmoon_cycles:
            tolerance: timedelta = timedelta(hours=1)  # 1 hour tolerance for date comparisons -- as there is some variation on the newmoon exact times
            nwmn_start_dt: datetime = mc[0]
            nwmn_start_dt_min: datetime = nwmn_start_dt - tolerance
            nwmn_start_dt_max: datetime = nwmn_start_dt + tolerance
            nwmn_end_dt: datetime = mc[1]
            nwmn_end_dt_min: datetime = nwmn_end_dt - tolerance
            nwmn_end_dt_max: datetime = nwmn_end_dt + tolerance

            # Check if this moon cycle is already in the catalog
            # and if it is, and it is historic_complete we can skip it, unless force is True 
            existing_entry = self.catalog[
                (self.catalog["nwmn_start_dt"] >= nwmn_start_dt_min.isoformat()) &
                (self.catalog["nwmn_start_dt"] <= nwmn_start_dt_max.isoformat()) &
                (self.catalog["nwmn_end_dt"] >= nwmn_end_dt_min.isoformat()) &
                (self.catalog["nwmn_end_dt"] <= nwmn_end_dt_max.isoformat()) &
                (self.catalog["historic_complete"])
            ]

            if existing_entry.empty or force:
                # If not, download the data and add it to the catalog
                self.add_cmems_data_to_catalog(mc)
