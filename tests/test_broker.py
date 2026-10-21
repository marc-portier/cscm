"""Unit tests for CSCM UDAL Broker Layer, Catalogue, and Domain Brokers."""

from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock
import numpy as np
import pandas as pd
import pytest
import xarray as xr

from cscm.broker import (
    BelgianTideBroker,
    CmemsCurrentBroker,
    CompositeDataBroker,
    HicTideBroker,
    MdkTideBroker,
    NamedQuery,
    QueryResult,
    URI_QUERY_CURRENT,
    URI_QUERY_TIDE,
    get_broker,
    resolve_query_contract,
    QUERY_CATALOGUE,
    BrokerError,
    GeographicOutOfDomainError,
    InvalidQueryParameterError,
    TemporalOutOfDomainError,
)
from cscm.commons import is_singleton
from cscm.storage.base import CatalogEntry


def test_catalogue_resolution():
    """Verify semantic URI and shorthand resolution."""
    c1 = resolve_query_contract("urn:cscm:query:current")
    c3 = resolve_query_contract("current")
    assert c1.uri == URI_QUERY_CURRENT
    assert c1 is c3
    assert "start_time" in c1.supported_params

    with pytest.raises(ValueError, match="Unknown query URI"):
        resolve_query_contract("urn:cscm:nonexistent")


def test_query_inspection_and_chaining():
    """Verify that NamedQuery can be inspected and chained with set_param."""
    broker = CompositeDataBroker()
    qry = broker.named_query(URI_QUERY_CURRENT)
    assert qry.uri == URI_QUERY_CURRENT
    assert "start_time" in qry.supported_params
    assert "current_speed_m_s" in qry.result_schema

    qry.set_param("lat", 51.25).set_param("lon", 2.97)
    assert qry.params["lat"] == 51.25
    assert qry.params["lon"] == 2.97

    info = qry.inspect()
    assert info["broker"] == "CompositeDataBroker"
    assert info["current_params"]["lat"] == 51.25


def test_format_negotiation():
    """Verify QueryResult format negotiation for pandas, xarray, and records."""
    df = pd.DataFrame({
        "timestamp": [
            pd.Timestamp("2026-10-24 10:00:00+00:00"),
            pd.Timestamp("2026-10-24 10:15:00+00:00"),
        ],
        "current_speed_m_s": [1.1, 1.2],
        "current_direction_deg": [60.0, 65.0],
    })
    res = QueryResult(_df=df, metadata={"uri": URI_QUERY_CURRENT, "provider": "cmems"})

    # Pandas
    res_df = res.data(as_format="pandas")
    assert isinstance(res_df, pd.DataFrame)
    assert len(res_df) == 2

    # Xarray
    res_xr = res.data(as_format="xarray")
    assert isinstance(res_xr, xr.Dataset)
    assert "current_speed_m_s" in res_xr

    # Records / List[dict]
    records = res.data(as_format="records")
    assert isinstance(records, list)
    assert len(records) == 2
    assert records[0]["current_speed_m_s"] == 1.1

    # Shortcuts
    assert isinstance(res.to_dataframe(), pd.DataFrame)
    assert isinstance(res.to_xarray(), xr.Dataset)
    assert isinstance(res.to_records(), list)

    # Inspection
    inspection = res.inspect()
    assert inspection["row_count"] == 2
    assert inspection["provider"] == "cmems"


def test_tide_query_execution():
    """Verify executing urn:cscm:query:tide through HicTideBroker and Composite broker."""
    mock_hic = MagicMock()
    mock_hic.client.get_station.return_value = MagicMock(
        code="OST",
        name="Oostende MVB",
        latitude=51.234,
        longitude=2.926,
        ts_observed_5min="123",
    )
    mock_df = pd.DataFrame({
        "timestamp": [
            pd.Timestamp("2026-10-24 10:00:00+00:00"),
            pd.Timestamp("2026-10-24 11:00:00+00:00"),
        ],
        "station": ["OST", "OST"],
        "water_level_m_taw": [4.10, 3.85],
        "source": ["forecast", "forecast"],
    })
    mock_hic.get_water_levels.return_value = mock_df

    tide_broker = HicTideBroker(manager=mock_hic)
    composite_broker = CompositeDataBroker(tide_broker=tide_broker)

    t0 = datetime(2026, 10, 24, 10, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc)

    # Test via query builder
    qry = composite_broker.named_query(URI_QUERY_TIDE)
    qry.set_params(
        station="OST",
        start_time=t0,
        end_time=t1,
        source="forecast",
        time_offset_minutes=7.0,
    )
    result = qry.execute()

    assert isinstance(result, QueryResult)
    df = result.data()
    assert len(df) == 2
    assert "water_level_m_taw" in df.columns
    # Check 7 minute offset shift
    assert df["timestamp"].iloc[0] == pd.Timestamp("2026-10-24 10:07:00+00:00")
    assert result.metadata["provider"] == "hic"
    assert result.metadata["time_offset_minutes"] == 7.0

    # Test convenience one-liner shortcut on broker
    res2 = composite_broker.query(
        URI_QUERY_TIDE,
        station="OST",
        start_time=t0,
        end_time=t1,
    )
    assert len(res2) == 2


def test_tide_query_coordinate_resolution():
    """Verify coordinate resolution and automatic Bredene phase lag detection."""
    mock_hic = MagicMock()
    mock_df = pd.DataFrame({
        "timestamp": [pd.Timestamp("2026-10-24 10:00:00+00:00")],
        "station": ["OST"],
        "water_level_m_taw": [4.10],
        "source": ["forecast"],
    })
    mock_hic.get_water_levels.return_value = mock_df

    tide_broker = HicTideBroker(manager=mock_hic)
    t0 = datetime.now(timezone.utc) + timedelta(days=1)
    t1 = t0 + timedelta(hours=2)

    # Coordinates near Bredene Strandpost 4 (51.2542, 2.9740)
    res = tide_broker.query(URI_QUERY_TIDE, lat=51.2542, lon=2.9740, start_time=t0, end_time=t1)
    # Automatic Bredene phase lag (+7 min) applied and predictive source routed to 'forecast'
    assert res.metadata["station"] == "OST"
    assert res.metadata["time_offset_minutes"] == 7.0
    assert res.metadata["effective_source"] == "forecast"


def test_current_query_execution_with_mock_nc(tmp_path):
    """Verify executing urn:cscm:query:current through the broker with synthetic NetCDF."""
    # Create synthetic NetCDF dataset with standard CF-compliant time coordinate
    times = pd.date_range("2026-10-24 08:00", "2026-10-24 12:00", freq="15min")
    lats = np.array([51.2, 51.3, 51.4])
    lons = np.array([2.9, 3.0, 3.1])

    # Shape: (time, lat, lon)
    shape = (len(times), len(lats), len(lons))
    uo_data = np.full(shape, 0.6)
    vo_data = np.full(shape, 0.8)

    # Set cell [0, 0] to land (NaN) so boundary classification operates
    uo_data[:, 0, 0] = np.nan
    vo_data[:, 0, 0] = np.nan

    ds = xr.Dataset(
        data_vars={
            "uo": (["time", "latitude", "longitude"], uo_data),
            "vo": (["time", "latitude", "longitude"], vo_data),
        },
        coords={
            "time": times,
            "latitude": lats,
            "longitude": lons,
        },
    )

    nc_file = tmp_path / "synthetic_cmems.nc"
    ds.to_netcdf(nc_file)

    mock_cmems = MagicMock()
    mock_cmems.data_folder = tmp_path
    mock_cmems.find_covering_files.return_value = [
        CatalogEntry(
            file_name=nc_file.name,
            start_dt=times[0].to_pydatetime().replace(tzinfo=timezone.utc),
            end_dt=times[-1].to_pydatetime().replace(tzinfo=timezone.utc),
            is_forecast=True,
        )
    ]

    current_broker = CmemsCurrentBroker(manager=mock_cmems)
    composite_broker = CompositeDataBroker(current_broker=current_broker)

    t0 = datetime(2026, 10, 24, 9, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 10, 24, 11, 0, tzinfo=timezone.utc)

    res = composite_broker.query(
        URI_QUERY_CURRENT,
        start_time=t0,
        end_time=t1,
        lat=51.35,
        lon=3.05,
        avoid_boundary_damping=True,
    )

    assert isinstance(res, QueryResult)
    df = res.data()
    assert not df.empty
    assert "current_speed_eastward_m_s" in df.columns
    assert "current_speed_northward_m_s" in df.columns
    assert "current_speed_m_s" in df.columns
    assert "current_direction_deg" in df.columns
    # With u=0.6, v=0.8, speed = sqrt(0.36 + 0.64) = 1.0 m/s
    assert df["current_speed_m_s"].iloc[0] == pytest.approx(1.0, rel=1e-3)
    assert res.metadata["provider"] == "cmems"
    assert res.metadata["avoid_boundary_damping"] is True


def test_get_broker_singleton():
    """Verify get_broker returns a singleton instance and uses @singleton."""
    assert is_singleton(CompositeDataBroker)
    b1 = get_broker()
    b2 = get_broker()
    assert b1 is b2


def test_invalid_time_window_raises_error():
    """Verify that start_time > end_time raises InvalidQueryParameterError."""
    from cscm.broker import InvalidQueryParameterError
    broker = CompositeDataBroker()
    t_start = datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc)
    t_end = datetime(2026, 10, 25, 10, 0, tzinfo=timezone.utc)  # End before start!

    with pytest.raises(InvalidQueryParameterError, match="must be before end_time"):
        broker.query(URI_QUERY_TIDE, start_time=t_start, end_time=t_end)

    with pytest.raises(InvalidQueryParameterError, match="must be before end_time"):
        broker.query(URI_QUERY_CURRENT, start_time=t_start, end_time=t_end)


def test_geographic_out_of_domain_raises_error():
    """Verify that coordinates outside the Belgian coast raise GeographicOutOfDomainError."""
    from cscm.broker import GeographicOutOfDomainError
    broker = CompositeDataBroker()

    # Paris: 48.8566 N, 2.3522 E (> 250 km from Belgian coast)
    with pytest.raises(GeographicOutOfDomainError, match="outside the Belgian Coastal Tide System operational domain"):
        broker.query(URI_QUERY_TIDE, lat=48.8566, lon=2.3522)

    # Mediterranean: 36.0 N, 14.0 E
    with pytest.raises(GeographicOutOfDomainError, match="outside the CMEMS NW European Shelf"):
        broker.query(URI_QUERY_CURRENT, lat=36.0, lon=14.0)


def test_temporal_out_of_domain_raises_error():
    """Verify requesting past-only sensors in the future raises TemporalOutOfDomainError."""
    from cscm.broker import MdkTideBroker, TemporalOutOfDomainError

    mdk_broker = MdkTideBroker(manager=MagicMock())
    future_time = datetime.now(timezone.utc) + timedelta(days=2)

    with pytest.raises(TemporalOutOfDomainError, match="MDK only provides historical sensor observations"):
        mdk_broker.query(
            URI_QUERY_TIDE,
            station="OST",
            start_time=future_time,
            end_time=future_time + timedelta(hours=2),
        )


def test_belgian_tide_composite_past_future_split():
    """
    Verify that querying a tidal window spanning past and future across 'now'
    splits seamlessly into past historical observations and future forecasts,
    concatenating them into a unified continuous dataset.
    """
    from cscm.broker import BelgianTideBroker

    now_utc = datetime.now(timezone.utc)
    t_past = now_utc - timedelta(hours=2)
    t_future = now_utc + timedelta(hours=2)

    mock_hic = MagicMock()
    mock_mdk = MagicMock()

    # Past observation dataframe
    df_past = pd.DataFrame({
        "timestamp": [t_past, now_utc],
        "lat": [51.233, 51.233],
        "lon": [2.916, 2.916],
        "station": ["OST", "OST"],
        "water_level_m_taw": [3.80, 4.10],
        "source": ["observed", "observed"],
    })
    mock_mdk.get_water_levels.return_value = df_past

    # Future forecast dataframe
    df_future = pd.DataFrame({
        "timestamp": [now_utc, t_future],
        "lat": [51.234, 51.234],
        "lon": [2.926, 2.926],
        "station": ["OST", "OST"],
        "water_level_m_taw": [4.10, 4.35],
        "source": ["forecast", "forecast"],
    })
    mock_hic.get_water_levels.return_value = df_future

    belgian_broker = BelgianTideBroker(
        hic_broker=HicTideBroker(manager=mock_hic),
        mdk_broker=MdkTideBroker(manager=mock_mdk),
    )

    res = belgian_broker.query(
        URI_QUERY_TIDE,
        station="OST",
        start_time=t_past,
        end_time=t_future,
        source="auto",
    )

    assert isinstance(res, QueryResult)
    df = res.data()
    # Continuous merged timeseries: duplicates at 'now' dropped
    assert len(df) == 3
    assert df["timestamp"].iloc[0] == t_past
    assert df["timestamp"].iloc[-1] == t_future
    assert res.metadata["composite"] is True
    assert len(res.metadata["segments"]) == 2
    assert res.metadata["segments"][0]["provider"] == "mdk"
    assert res.metadata["segments"][1]["provider"] == "hic"


def test_fluent_builder_and_format_negotiation():
    """Verify fluent broker.build().param().execute() and QueryResult format conversions."""
    broker = CompositeDataBroker()
    builder = broker.build("current").param("lat", 51.25).param("lon", 2.97)
    assert builder.params["lat"] == 51.25
    assert builder.params["lon"] == 2.97

    # Test QueryResult concrete methods and data() router
    test_df = pd.DataFrame({
        "timestamp": [datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)],
        "val": [42.0],
    })
    qr = QueryResult(_df=test_df, metadata={"provider": "test"})
    assert isinstance(qr.to_dataframe(), pd.DataFrame)
    assert isinstance(qr.to_xarray(), xr.Dataset)
    assert isinstance(qr.to_records(), list)
    assert isinstance(qr.to_dict(), dict)
    assert len(qr.to_records()) == 1
    assert qr.data("pandas").equals(test_df)
    assert qr.data("dataframe").equals(test_df)
    assert qr.data("records") == [{"timestamp": test_df["timestamp"].iloc[0], "val": 42.0}]