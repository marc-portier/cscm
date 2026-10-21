"""
Universal Data Access Layer (UDAL) - Semantic Query Catalogue & Contracts.

Defines standardized Semantic URIs, parameter constraints, and column schemas
for all domain queries (currents, tides, landmarks, moon phases).
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# --- Semantic Query URIs ---
URI_QUERY_CURRENT = "urn:cscm:query:current"
URI_QUERY_TIDE = "urn:cscm:query:tide"
URI_QUERY_LANDMARK = "urn:cscm:query:landmark"
URI_QUERY_MOONPHASE = "urn:cscm:query:moonphase"

# --- Semantic Parameter URIs ---
URI_PARAM_START_TIME = "urn:cscm:param:start_time"
URI_PARAM_END_TIME = "urn:cscm:param:end_time"
URI_PARAM_LAT = "urn:cscm:param:lat"
URI_PARAM_LON = "urn:cscm:param:lon"
URI_PARAM_STATION = "urn:cscm:param:station"
URI_PARAM_POSITIONS = "urn:cscm:param:positions"
URI_PARAM_AVOID_DAMPING = "urn:cscm:param:avoid_boundary_damping"
URI_PARAM_TIME_OFFSET_MIN = "urn:cscm:param:time_offset_minutes"
URI_PARAM_SOURCE = "urn:cscm:param:source"

# --- Semantic Column URIs ---
URI_COL_TIME_UTC = "urn:cscm:column:time:utc"
URI_COL_LAT = "urn:cscm:column:geo:lat"
URI_COL_LON = "urn:cscm:column:geo:lon"
URI_COL_CURRENT_SPEED_EASTWARD = "urn:cscm:column:current_speed:eastward"
URI_COL_CURRENT_SPEED_NORTHWARD = "urn:cscm:column:current_speed:northward"
URI_COL_CURRENT_SPEED_MAGNITUDE = "urn:cscm:column:current_speed:magnitude"
URI_COL_CURRENT_DIR_FROM_NORTH = "urn:cscm:column:current_direction:from_north"
URI_COL_STATION_CODE = "urn:cscm:column:station:code"
URI_COL_WATER_LEVEL_M_TAW = "urn:cscm:column:water_level:m_taw"
URI_COL_TIDE_SOURCE = "urn:cscm:column:tide:source"


@dataclass(frozen=True)
class ParamDefinition:
    """Defines a query parameter supported by a QueryContract."""
    name: str
    uri: str
    type_hint: str
    required: bool = False
    description: str = ""
    default: Any = None


@dataclass(frozen=True)
class ColumnDefinition:
    """Defines a column in the standardized tabular response."""
    name: str
    uri: str
    description: str = ""
    unit: str = ""
    aliases: List[str] = field(default_factory=list)


@dataclass
class QueryContract:
    """Complete specification contract for a semantic query."""
    uri: str
    title: str
    description: str
    supported_params: Dict[str, ParamDefinition]
    result_schema: Dict[str, ColumnDefinition]
    status: str = "active"  # "active" or "draft"

    def inspect(self) -> Dict[str, Any]:
        """Returns structured dictionary of contract metadata."""
        return {
            "uri": self.uri,
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "supported_params": {
                name: {
                    "uri": p.uri,
                    "type": p.type_hint,
                    "required": p.required,
                    "description": p.description,
                    "default": p.default,
                }
                for name, p in self.supported_params.items()
            },
            "result_schema": {
                name: {
                    "uri": col.uri,
                    "description": col.description,
                    "unit": col.unit,
                    "aliases": col.aliases,
                }
                for name, col in self.result_schema.items()
            },
        }


# ==============================================================================
# CANONICAL QUERY CATALOGUE
# ==============================================================================

QUERY_CATALOGUE: Dict[str, QueryContract] = {
    URI_QUERY_CURRENT: QueryContract(
        uri=URI_QUERY_CURRENT,
        title="Hydrodynamic Ocean Current Vectors",
        description="Extracts 2D horizontal ocean current speed and direction vectors along the coast.",
        supported_params={
            "start_time": ParamDefinition(
                name="start_time",
                uri=URI_PARAM_START_TIME,
                type_hint="datetime",
                required=False,
                description="UTC start datetime (defaults to start of current day).",
            ),
            "end_time": ParamDefinition(
                name="end_time",
                uri=URI_PARAM_END_TIME,
                type_hint="datetime",
                required=False,
                description="UTC end datetime (defaults to start_time + 1 day).",
            ),
            "lat": ParamDefinition(
                name="lat",
                uri=URI_PARAM_LAT,
                type_hint="float",
                required=False,
                description="Target latitude in degrees north.",
            ),
            "lon": ParamDefinition(
                name="lon",
                uri=URI_PARAM_LON,
                type_hint="float",
                required=False,
                description="Target longitude in degrees east.",
            ),
            "positions": ParamDefinition(
                name="positions",
                uri=URI_PARAM_POSITIONS,
                type_hint="List[Tuple[float, float]]",
                required=False,
                description="Optional list of (lat, lon) coordinates representing route checkpoints.",
            ),
            "avoid_boundary_damping": ParamDefinition(
                name="avoid_boundary_damping",
                uri=URI_PARAM_AVOID_DAMPING,
                type_hint="bool",
                required=False,
                default=True,
                description="If True, selects nearest full water cell (status 2), avoiding coastal boundary friction damping.",
            ),
        },
        result_schema={
            "timestamp": ColumnDefinition(
                name="timestamp",
                uri=URI_COL_TIME_UTC,
                description="UTC timestamp of the current vector",
                unit="ISO-8601 UTC",
            ),
            "lat": ColumnDefinition(
                name="lat",
                uri=URI_COL_LAT,
                description="Latitude of selected hydrodynamic grid cell",
                unit="degrees_north",
            ),
            "lon": ColumnDefinition(
                name="lon",
                uri=URI_COL_LON,
                description="Longitude of selected hydrodynamic grid cell",
                unit="degrees_east",
            ),
            "current_speed_eastward_m_s": ColumnDefinition(
                name="current_speed_eastward_m_s",
                uri=URI_COL_CURRENT_SPEED_EASTWARD,
                description="Zonal water velocity eastward",
                unit="m/s",
                aliases=["u_water"],
            ),
            "current_speed_northward_m_s": ColumnDefinition(
                name="current_speed_northward_m_s",
                uri=URI_COL_CURRENT_SPEED_NORTHWARD,
                description="Meridional water velocity northward",
                unit="m/s",
                aliases=["v_water"],
            ),
            "current_speed_m_s": ColumnDefinition(
                name="current_speed_m_s",
                uri=URI_COL_CURRENT_SPEED_MAGNITUDE,
                description="Total horizontal current speed magnitude (sqrt(u^2 + v^2))",
                unit="m/s",
                aliases=["current_speed_ms_magnitude"],
            ),
            "current_direction_deg": ColumnDefinition(
                name="current_direction_deg",
                uri=URI_COL_CURRENT_DIR_FROM_NORTH,
                description="Flow direction towards (0-360 degrees from True North)",
                unit="degrees",
                aliases=["current_direction_deg_from_north"],
            ),
        },
    ),
    URI_QUERY_TIDE: QueryContract(
        uri=URI_QUERY_TIDE,
        title="Coastal Tidal Water Levels",
        description="Fetches 5-minute coastal water level curves in meters TAW and extreme events (HW/LW).",
        supported_params={
            "station": ParamDefinition(
                name="station",
                uri=URI_PARAM_STATION,
                type_hint="str",
                required=False,
                description="Canonical coastal station code (e.g. 'OST', 'NPT', 'ZLD').",
            ),
            "lat": ParamDefinition(
                name="lat",
                uri=URI_PARAM_LAT,
                type_hint="float",
                required=False,
                description="Target latitude. If provided without station, resolves nearest gauge with alongshore phase lag.",
            ),
            "lon": ParamDefinition(
                name="lon",
                uri=URI_PARAM_LON,
                type_hint="float",
                required=False,
                description="Target longitude.",
            ),
            "start_time": ParamDefinition(
                name="start_time",
                uri=URI_PARAM_START_TIME,
                type_hint="datetime",
                required=False,
                description="UTC start datetime.",
            ),
            "end_time": ParamDefinition(
                name="end_time",
                uri=URI_PARAM_END_TIME,
                type_hint="datetime",
                required=False,
                description="UTC end datetime.",
            ),
            "source": ParamDefinition(
                name="source",
                uri=URI_PARAM_SOURCE,
                type_hint="str",
                required=False,
                default="auto",
                description="'auto' (infers forecast vs astro from time range), 'forecast' (KT-Last), or 'astro' (Astro.05).",
            ),
            "time_offset_minutes": ParamDefinition(
                name="time_offset_minutes",
                uri=URI_PARAM_TIME_OFFSET_MIN,
                type_hint="float",
                required=False,
                default=0.0,
                description="Optional temporal lag in minutes (e.g. +7.0 min for Bredene relative to Oostende).",
            ),
        },
        result_schema={
            "timestamp": ColumnDefinition(
                name="timestamp",
                uri=URI_COL_TIME_UTC,
                description="UTC timestamp of the water level measurement",
                unit="ISO-8601 UTC",
            ),
            "lat": ColumnDefinition(
                name="lat",
                uri=URI_COL_LAT,
                description="Latitude of water level measurement or reference station",
                unit="degrees_north",
            ),
            "lon": ColumnDefinition(
                name="lon",
                uri=URI_COL_LON,
                description="Longitude of water level measurement or reference station",
                unit="degrees_east",
            ),
            "station": ColumnDefinition(
                name="station",
                uri=URI_COL_STATION_CODE,
                description="Reference coastal station code",
                unit="code",
            ),
            "water_level_m_taw": ColumnDefinition(
                name="water_level_m_taw",
                uri=URI_COL_WATER_LEVEL_M_TAW,
                description="Water level in meters relative to Belgian reference datum TAW",
                unit="m TAW",
            ),
            "source": ColumnDefinition(
                name="source",
                uri=URI_COL_TIDE_SOURCE,
                description="Data origin: 'forecast' (surge+tide model), 'astro' (astronomical), or 'observed'",
                unit="string",
            ),
        },
    ),
    URI_QUERY_LANDMARK: QueryContract(
        uri=URI_QUERY_LANDMARK,
        title="Coastal Landmarks & Beach Posts (Backlog)",
        description="Retrieves geographic landmarks, municipality beach posts, groynes, and bearings.",
        supported_params={},
        result_schema={},
        status="draft",
    ),
    URI_QUERY_MOONPHASE: QueryContract(
        uri=URI_QUERY_MOONPHASE,
        title="Astronomical Lunar Cycles & Moon Phases (Backlog)",
        description="Retrieves moon phases, synodic cycle boundaries, and lunar tide periods.",
        supported_params={},
        result_schema={},
        status="draft",
    ),
}


def resolve_query_contract(query_uri: str) -> QueryContract:
    """
    Resolves a semantic query URI or convenient shorthand to its formal QueryContract.
    Supports 'urn:cscm:query:current', 'current', 'moonphase', etc.
    """
    clean = query_uri.strip().lower()
    # Direct match
    if clean in QUERY_CATALOGUE:
        return QUERY_CATALOGUE[clean]

    # Normalize shorthands: 'urn:cscm:current' -> 'urn:cscm:query:current'
    if clean.startswith("urn:cscm:") and not clean.startswith("urn:cscm:query:"):
        sub = clean[len("urn:cscm:"):]
        mapped = f"urn:cscm:query:{sub}"
        if mapped in QUERY_CATALOGUE:
            return QUERY_CATALOGUE[mapped]

    # Shorthand by simple domain: 'current' -> 'urn:cscm:query:current'
    simple_map = {
        "current": URI_QUERY_CURRENT,
        "tide": URI_QUERY_TIDE,
        "landmark": URI_QUERY_LANDMARK,
        "moon": URI_QUERY_MOONPHASE,
        "moonphase": URI_QUERY_MOONPHASE,
        "moon_phase": URI_QUERY_MOONPHASE,
    }
    if clean in simple_map:
        return QUERY_CATALOGUE[simple_map[clean]]

    known = ", ".join(QUERY_CATALOGUE.keys())
    raise ValueError(f"Unknown query URI '{query_uri}'. Known catalogue queries: {known}")