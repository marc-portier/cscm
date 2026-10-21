"""
Client for the Meetnet Vlaamse Banken (MDK) REST API v2.

Provides authentication, catalog exploration, and water level / tidal data
retrieval for Belgian coastal monitoring stations (e.g. Nieuwpoort, Oostende,
Blankenberge, Zeebrugge, Westhinder).
"""

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from dotenv import load_dotenv
import pandas as pd
import requests

from cscm.storage.base import AbstractDataStoreManager, CatalogEntry

logger = logging.getLogger(__name__)

MDK_BASE_URL = "https://api.meetnetvlaamsebanken.be"
MDK_TOKEN_URL = f"{MDK_BASE_URL}/Token"


@dataclass(frozen=True)
class MdkStation:
    """Represents an MDK coastal monitoring station."""

    code: str  # 3-letter station ID (e.g. 'OHM')
    name: str  # Human readable name
    latitude: float
    longitude: float
    water_level_param_id: str  # 6-character location+parameter key (e.g. 'OHMWS5')
    description: str = ""


# Canonical Flemish coastal water level stations
COASTAL_TIDE_STATIONS: Dict[str, MdkStation] = {
    "NPT": MdkStation(
        code="NPT",
        name="Nieuwpoort",
        latitude=51.147222,
        longitude=2.743056,
        water_level_param_id="NPTWS5",
        description="Nieuwpoort Haven / Getij (cm TAW)",
    ),
    "OHM": MdkStation(
        code="OHM",
        name="Oostende Haven",
        latitude=51.233333,
        longitude=2.916667,
        water_level_param_id="OHMWS5",
        description="Oostende Haven / Getij (cm TAW)",
    ),
    "BLK": MdkStation(
        code="BLK",
        name="Blankenberge",
        latitude=51.316667,
        longitude=3.116667,
        water_level_param_id="BLKWS5",
        description="Blankenberge Haven / Getij (cm TAW)",
    ),
    "ZLD": MdkStation(
        code="ZLD",
        name="Zeebrugge Leopold II dam",
        latitude=51.333333,
        longitude=3.200000,
        water_level_param_id="ZLDWS5",
        description="Zeebrugge Leopold II dam / Getij (cm TAW)",
    ),
    "ZWD": MdkStation(
        code="ZWD",
        name="Zeebrugge Wielingendok",
        latitude=51.339444,
        longitude=3.193056,
        water_level_param_id="ZWDWS5",
        description="Zeebrugge Wielingendok / Getij (cm TAW)",
    ),
    "MP7": MdkStation(
        code="MP7",
        name="Westhinder (Meetpaal 7)",
        latitude=51.388611,
        longitude=2.437778,
        water_level_param_id="MP7WS5",
        description="Westhinder Meetpaal 7 / Getij (cm TAW)",
    ),
}


class MdkClient:
    """Client for the Meetnet Vlaamse Banken (MDK) API v2."""

    def __init__(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        base_url: str = MDK_BASE_URL,
        session: Optional[requests.Session] = None,
        timeout: int = 30,
    ):
        """
        Initialize MdkClient.

        If username and password are not provided, attempts to load them from
        environment variables `MDK_USERNAME` and `MDK_PASSWORD` (including from
        a root `.env` file if present).
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = session or requests.Session()

        # Load environment variables if credentials not supplied
        if not (username and password):
            load_dotenv()
            # Also attempt to load from repository root if running within project
            env_path = Path(__file__).resolve().parents[3] / ".env"
            if env_path.exists():
                load_dotenv(dotenv_path=env_path)

        self.username = username or os.getenv("MDK_USERNAME")
        self.password = password or os.getenv("MDK_PASSWORD")

        self._token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None
        self._catalog_cache: Optional[Dict[str, Any]] = None

    def _ensure_token(self) -> str:
        """Authenticate or refresh bearer token if expired or close to expiry."""
        now = datetime.now(timezone.utc)
        if (
            self._token
            and self._token_expires_at
            and (self._token_expires_at - now).total_seconds() > 60
        ):
            return self._token

        if not self.username or not self.password:
            raise ValueError(
                "MDK credentials missing. Provide username & password or set "
                "MDK_USERNAME and MDK_PASSWORD in environment / .env"
            )

        token_url = f"{self.base_url}/Token"
        payload = {
            "grant_type": "password",
            "username": self.username,
            "password": self.password,
        }
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        }

        try:
            resp = self.session.post(
                token_url, data=payload, headers=headers, timeout=self.timeout
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.HTTPError as exc:
            msg = f"MDK Authentication failed ({resp.status_code}): {resp.text}"
            logger.error(msg)
            raise RuntimeError(msg) from exc
        except Exception as exc:
            msg = f"Failed to connect to MDK token endpoint: {exc}"
            logger.error(msg)
            raise RuntimeError(msg) from exc

        self._token = data.get("access_token")
        expires_in = data.get("expires_in", 3600)
        self._token_expires_at = now + timedelta(seconds=expires_in)
        logger.debug("Acquired MDK bearer token (expires in %ds)", expires_in)
        return self._token

    def _auth_headers(self) -> Dict[str, str]:
        """Headers with valid Bearer token."""
        token = self._ensure_token()
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def ping(self) -> Dict[str, Any]:
        """Call /V2/ping to verify connectivity and API health."""
        url = f"{self.base_url}/V2/ping"
        resp = self.session.get(url, headers=self._auth_headers(), timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def get_catalog(self, force_refresh: bool = False) -> Dict[str, Any]:
        """Retrieve the MDK parameter and station catalog."""
        if self._catalog_cache and not force_refresh:
            return self._catalog_cache

        url = f"{self.base_url}/V2/catalog"
        resp = self.session.get(url, headers=self._auth_headers(), timeout=self.timeout)
        resp.raise_for_status()
        self._catalog_cache = resp.json()
        return self._catalog_cache

    def get_current_data(
        self, ids: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Fetch latest available sensor measurements.

        :param ids: Optional list of 6-character LocationParameterKeys (e.g. ['OHMWS5']).
                    If None or empty, returns latest data for all available sensors.
        """
        url = f"{self.base_url}/V2/currentData"
        body = {"IDs": ids} if ids else {}
        resp = self.session.post(
            url, json=body, headers=self._auth_headers(), timeout=self.timeout
        )
        resp.raise_for_status()
        return resp.json()

    def get_data(
        self,
        ids: List[str],
        start_time: Union[datetime, str],
        end_time: Union[datetime, str],
    ) -> List[Dict[str, Any]]:
        """
        Fetch time series sensor data for given IDs within a time window.

        :param ids: List of 6-character LocationParameterKeys (e.g. ['OHMWS5', 'NPTWS5'])
        :param start_time: Start datetime (ISO string or datetime object)
        :param end_time: End datetime (ISO string or datetime object)
        """
        if isinstance(start_time, datetime):
            if start_time.tzinfo is None:
                start_time = start_time.replace(tzinfo=timezone.utc)
            start_str = start_time.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        else:
            start_str = str(start_time)

        if isinstance(end_time, datetime):
            if end_time.tzinfo is None:
                end_time = end_time.replace(tzinfo=timezone.utc)
            end_str = end_time.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        else:
            end_str = str(end_time)

        url = f"{self.base_url}/V2/getData"
        payload = {
            "StartTime": start_str,
            "EndTime": end_str,
            "IDs": ids,
        }
        resp = self.session.post(
            url, json=payload, headers=self._auth_headers(), timeout=self.timeout
        )
        resp.raise_for_status()
        return resp.json()

    def get_water_levels(
        self,
        stations: Optional[List[str]] = None,
        start_time: Optional[Union[datetime, str]] = None,
        end_time: Optional[Union[datetime, str]] = None,
        in_meters: bool = True,
    ) -> pd.DataFrame:
        """
        Retrieve water levels (Getij TAW) for specified stations as a pandas DataFrame.

        :param stations: Station codes to query (e.g. ['NPT', 'OHM', 'BLK', 'ZLD']).
                         Defaults to all 6 COASTAL_TIDE_STATIONS if None.
        :param start_time: Start timestamp (UTC). Defaults to 24 hours ago.
        :param end_time: End timestamp (UTC). Defaults to now.
        :param in_meters: If True, convert cm TAW to meters TAW.
        :return: DataFrame with columns:
                 ['timestamp', 'station_code', 'station_name', 'water_level_m_taw'] (or _cm_taw)
        """
        if stations is None:
            target_stations = list(COASTAL_TIDE_STATIONS.keys())
        else:
            target_stations = [s.upper() for s in stations]

        now = datetime.now(timezone.utc)
        if start_time is None:
            start_time = now - timedelta(hours=24)
        if end_time is None:
            end_time = now

        # Map station codes to parameter IDs
        id_to_station: Dict[str, MdkStation] = {}
        query_ids: List[str] = []
        for code in target_stations:
            if code in COASTAL_TIDE_STATIONS:
                st = COASTAL_TIDE_STATIONS[code]
                id_to_station[st.water_level_param_id] = st
                query_ids.append(st.water_level_param_id)
            else:
                # Custom parameter ID passed directly?
                query_ids.append(code)

        raw_data = self.get_data(ids=query_ids, start_time=start_time, end_time=end_time)

        series_list = (
            raw_data.get("Values", []) if isinstance(raw_data, dict) else raw_data
        )
        records: List[Dict[str, Any]] = []
        for series in series_list:
            if not isinstance(series, dict):
                continue
            series_id = series.get("ID")
            station = id_to_station.get(series_id)
            code = station.code if station else series_id
            name = station.name if station else series_id

            values = series.get("Values") or []
            for item in values:
                ts_str = item.get("Timestamp")
                val = item.get("Value")
                if ts_str is None or val is None:
                    continue

                ts = pd.to_datetime(ts_str, utc=True)
                val_num = float(val)
                level = val_num / 100.0 if in_meters else val_num

                rec = {
                    "timestamp": ts,
                    "station_code": code,
                    "station_name": name,
                    "water_level": level,
                }
                records.append(rec)

        if not records:
            col_name = "water_level_m_taw" if in_meters else "water_level_cm_taw"
            return pd.DataFrame(
                columns=["timestamp", "station_code", "station_name", col_name]
            )

        df = pd.DataFrame(records)
        val_col = "water_level_m_taw" if in_meters else "water_level_cm_taw"
        df.rename(columns={"water_level": val_col}, inplace=True)
        df.sort_values(by=["timestamp", "station_code"], inplace=True)
        df.reset_index(drop=True, inplace=True)
        return df

    def get_water_levels_pivot(
        self,
        stations: Optional[List[str]] = None,
        start_time: Optional[Union[datetime, str]] = None,
        end_time: Optional[Union[datetime, str]] = None,
        in_meters: bool = True,
        use_names: bool = False,
    ) -> pd.DataFrame:
        """
        Convenience method to retrieve water levels pivoted with timestamp as index
        and stations as columns.
        """
        df = self.get_water_levels(
            stations=stations,
            start_time=start_time,
            end_time=end_time,
            in_meters=in_meters,
        )
        if df.empty:
            return pd.DataFrame()

        val_col = "water_level_m_taw" if in_meters else "water_level_cm_taw"
        pivot_col = "station_name" if use_names else "station_code"
        pivoted = df.pivot(index="timestamp", columns=pivot_col, values=val_col)
        return pivoted


class MdkTideManager(AbstractDataStoreManager):
    """
    Manages local caching and retrieval of Meetnet Vlaamse Banken (MDK) tidal sensor data.
    Indexes cached intervals in catalog.json.
    """
    env_var_name = "MDK_DATA_FOLDER"
    default_subfolder_name = "data_store"

    def __init__(
        self,
        data_folder: Optional[Union[str, Path]] = None,
        client: Optional[MdkClient] = None,
    ):
        super().__init__(data_folder=data_folder)
        self.client = client or MdkClient()

    def retrieve(
        self,
        stations: Optional[List[str]] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        force: bool = False,
        **kwargs,
    ) -> Path:
        """Fetch water levels from MDK and save to CSV in data_store."""
        now_utc = datetime.now(timezone.utc)
        if start_time is None:
            start_time = now_utc - timedelta(hours=24)
        if end_time is None:
            end_time = now_utc

        if start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=timezone.utc)
        if end_time.tzinfo is None:
            end_time = end_time.replace(tzinfo=timezone.utc)

        target_stations = stations or ["OST"]
        # Map OHM synonym to OST or keep original
        canonical_stations = ["OHM" if s == "OST" else s for s in target_stations]

        df = self.client.get_water_levels(
            stations=canonical_stations,
            start_time=start_time,
            end_time=end_time,
            in_meters=True,
        )

        st_tag = "_".join(sorted(target_stations)).lower()
        s_str = start_time.strftime("%Y%m%d%H%M")
        e_str = end_time.strftime("%Y%m%d%H%M")
        file_name = f"mdk_{st_tag}_{s_str}_{e_str}.csv"
        out_path = self.data_folder / file_name
        df.to_csv(out_path, index=False)

        file_hash = self.compute_file_hash(out_path)
        entry = CatalogEntry(
            file_name=file_name,
            start_dt=start_time,
            end_dt=end_time,
            is_forecast=False,
            file_hash=file_hash,
            metadata={
                "stations": target_stations,
                "provider": "mdk",
                "rows": len(df),
            },
        )
        self.register_entry(entry)
        return out_path

    def get_water_levels(
        self,
        stations: Optional[List[str]] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        force: bool = False,
    ) -> pd.DataFrame:
        """Get water levels consulting local cache first."""
        target_stations = [s.upper() for s in (stations or ["OST"])]
        now_utc = datetime.now(timezone.utc)
        if start_time is None:
            start_time = now_utc - timedelta(hours=24)
        if end_time is None:
            end_time = now_utc

        if not force:
            catalog = self.get_catalog()
            for entry in catalog:
                entry_sts = entry.metadata.get("stations", [])
                if set(target_stations).issubset(set(entry_sts)) and entry.covers(start_time, end_time):
                    file_path = self.data_folder / entry.file_name
                    if file_path.exists():
                        df = pd.read_csv(file_path)
                        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
                        mask = (df["timestamp"] >= start_time) & (df["timestamp"] <= end_time)
                        return df[mask].sort_values("timestamp").reset_index(drop=True)

        csv_file = self.retrieve(stations=target_stations, start_time=start_time, end_time=end_time, force=force)
        df = pd.read_csv(csv_file)
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        mask = (df["timestamp"] >= start_time) & (df["timestamp"] <= end_time)
        return df[mask].sort_values("timestamp").reset_index(drop=True)

    def inspect(self) -> Dict[str, Any]:
        """Returns architectural inspection metadata for MDK data store manager."""
        return {
            "manager": self.__class__.__name__,
            "data_folder": str(self.data_folder),
            "catalog_path": str(self.catalog_path),
            "time_delimitation": "Historical sensor observation chunking indexed in catalog.json",
            "supported_stations": sorted(list(COASTAL_TIDE_STATIONS.keys())),
            "storage_status": self.status(),
        }