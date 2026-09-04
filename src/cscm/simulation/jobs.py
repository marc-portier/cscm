# src/cscm/simulation/jobs.py

import os
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Union
import yaml
import pandas as pd

from cscm.model import Position
from cscm.wellknown import POSITIONS as wkPositions


@dataclass
class JobActiveConfig:
    on: bool = True
    begin_date: Optional[datetime] = None
    end_date: Optional[datetime] = None


@dataclass
class JobCalcConfig:
    calc_id: str
    from_pos: Position
    bearing_deg: float
    duration_hours: float
    start_time_detect: Optional[list[str]] = None  # "pec", "pfc", etc.
    start_time_exact: Optional[datetime] = None
    detect_in_range_local: Optional[tuple[str, str]] = None  # ("05:00", "17:00")


@dataclass
class JobExtraConfig:
    qotd_path: Optional[Path] = None
    obstructions_path: Optional[Path] = None
    coastline_path: Optional[Path] = None


@dataclass
class JobMailConfig:
    to_list: list[str] = field(default_factory=list)
    subject_template: str = ""
    template_path: Optional[Path] = None
    attach_mode: str = "all"  # "all", "overview", "gpx", "none"


@dataclass
class JobResultsConfig:
    output_folder_template: str = ""
    overview_file_template: str = ""
    gpx_file_template: str = ""
    mail: Optional[JobMailConfig] = None


@dataclass
class JobConfig:
    title: str
    active: JobActiveConfig
    date_range_expr: str  # e.g., "1d,+5d"
    calculations: list[JobCalcConfig] = field(default_factory=list)
    extra: JobExtraConfig = field(default_factory=JobExtraConfig)
    results: Optional[JobResultsConfig] = None


def parse_time_range(range_str: str) -> tuple[str, str]:
    """Parses a time range string like '05:00-17:00' into a tuple of start and end hours."""
    parts = range_str.split("-")
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return "00:00", "23:59"


def parse_job_file(job_yaml_path: Path) -> JobConfig:
    """Parses a YAML simulation job file and builds a validated JobConfig structure."""
    with open(job_yaml_path, "r") as f:
        data = yaml.safe_load(f)

    # 1. Active Config
    active_raw = data.get("active", {})
    on = active_raw.get("if-on", True)
    range_raw = active_raw.get("if-now-in-range", {})
    begin_dt = None
    end_dt = None
    if range_raw.get("begin"):
        begin_dt = pd.to_datetime(range_raw["begin"]).replace(tzinfo=timezone.utc)
    if range_raw.get("end"):
        end_dt = pd.to_datetime(range_raw["end"]).replace(tzinfo=timezone.utc)

    active_cfg = JobActiveConfig(on=on, begin_date=begin_dt, end_date=end_dt)

    # 2. Calculations
    calcs_list = []
    calc_raw_list = data.get("calc", [])
    for c in calc_raw_list:
        c_id = c.get("id", "sim-run")
        from_label = c.get("from", "KOKSIJDE")
        from_pos = wkPositions.get(from_label.upper())
        if not from_pos:
            raise ValueError(f"Focal position label '{from_label}' not defined in wellknown.py")

        bearing = float(c.get("bearing", 316.0))
        duration_str = str(c.get("duration", "6h"))
        duration_hours = float(duration_str.replace("h", "").strip())

        # Start time parsing
        start_time_raw = c.get("start-time", {}) or c.get("time", {})
        detect_type = None
        exact_time = None
        in_range_local = None

        if isinstance(start_time_raw, dict):
            detect_raw = start_time_raw.get("detect")
            if isinstance(detect_raw, dict):
                types_raw = detect_raw.get("types", detect_raw.get("type", "pfc"))
                if "," in types_raw:
                    detect_type = [t.strip().lower() for t in types_raw.split(",")]
                else:
                    detect_type = [types_raw.strip().lower()]
                range_str = detect_raw.get("in-range", "00:00-23:59")
                in_range_local = parse_time_range(range_str)
            elif isinstance(detect_raw, str):
                detect_type = [detect_raw.strip().lower()]
                earliest = start_time_raw.get("earliest", "00:00")
                latest = start_time_raw.get("latest", "23:59")
                in_range_local = (earliest, latest)
        elif isinstance(start_time_raw, str):
            exact_time = pd.to_datetime(start_time_raw).replace(tzinfo=timezone.utc)

        # For single detect string setup
        if "detect" in c and isinstance(c["detect"], str):
            detect_type = [c["detect"].strip().lower()]

        calcs_list.append(
            JobCalcConfig(
                calc_id=c_id,
                from_pos=from_pos,
                bearing_deg=bearing,
                duration_hours=duration_hours,
                start_time_detect=detect_type,
                start_time_exact=exact_time,
                detect_in_range_local=in_range_local
            )
        )

    # 3. Extra stuff
    extra_raw = data.get("extra", {})
    extra_cfg = JobExtraConfig(
        qotd_path=Path(extra_raw["qotd"]) if "qotd" in extra_raw else None,
        obstructions_path=Path(extra_raw["obstructions"]) if "obstructions" in extra_raw else None,
        coastline_path=Path(extra_raw["coastline"]) if "coastline" in extra_raw else None
    )

    # 4. Results & Mail Config
    results_raw = data.get("results", {})
    results_cfg = None
    if results_raw:
        mail_raw = results_raw.get("mail", {})
        mail_cfg = None
        if mail_raw:
            to_raw = mail_raw.get("to", "")
            to_list = [t.strip() for t in to_raw.split(",")] if "," in to_raw else [to_raw.strip()]
            mail_cfg = JobMailConfig(
                to_list=to_list,
                subject_template=mail_raw.get("subject", ""),
                template_path=Path(mail_raw["template"]) if "template" in mail_raw else None,
                attach_mode=mail_raw.get("attach", "all")
            )

        results_cfg = JobResultsConfig(
            output_folder_template=results_raw.get("folder", ""),
            overview_file_template=results_raw.get("files", {}).get("overview", ""),
            gpx_file_template=results_raw.get("files", {}).get("gpx", ""),
            mail=mail_cfg
        )

    date_expr = data.get("date", {}).get("range", "1d,+5d")

    return JobConfig(
        title=data.get("title", "CSCM Simulation Job"),
        active=active_cfg,
        date_range_expr=date_expr,
        calculations=calcs_list,
        extra=extra_cfg,
        results=results_cfg
    )
