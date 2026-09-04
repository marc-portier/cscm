# src/cscm/simulation/__main__.py

import os
import sys
import argparse
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

import pandas as pd
import xarray as xr
import yaml
from jinja2 import Template

from cscm.model import Position
from cscm.wellknown import POSITIONS as wkPositions
from cscm.current.cmems.analyse import classify_grid_cells

from cscm.simulation.jobs import parse_job_file, JobConfig
from cscm.simulation.predict import (
    CmemsForecastCurrentsModel,
    find_daily_tide_peaks,
    simulate_test_swim,
    write_gpx_track,
    plot_daily_simulations
)
from cscm.simulation.mailer import send_simulation_email

# Set up logging to stdout
log = logging.getLogger("cscm.simulation")


def configure_logging():
    log.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    log.addHandler(handler)


def get_latest_forecast_nc(storage_dir: Path) -> Optional[Path]:
    """Finds the most recent CMEMS NetCDF file in the storage directory."""
    nc_files = list(storage_dir.glob("*.nc"))
    if not nc_files:
        return None
    # Return file with latest modified time
    return max(nc_files, key=lambda f: f.stat().st_mtime)


def parse_date_range_expr(expr: str, anchor_date: datetime) -> list[datetime]:
    """
    Parses range expressions like '1d,+5d' or '+0d,+4d' relative to anchor_date.
    Returns a list of datetime days to run simulations for.
    """
    try:
        parts = expr.split(",")
        days = []
        for p in parts:
            p = p.strip().lower()
            if p.endswith("d"):
                val = int(p[:-1].replace("+", ""))
                days.append(anchor_date + timedelta(days=val))
        # Ensure distinct and sorted dates
        return sorted(list(set(days)))
    except Exception as e:
        log.warning(f"Could not parse date range expression '{expr}', using today as default: {e}")
        return [anchor_date]


def load_random_qotd(qotd_path: Path) -> tuple[str, str]:
    """Loads a random Quote of the Day from qotd.yml."""
    default_quote = ("The most effective way to do it, is to do it.", "Amelia Earhart")
    if not qotd_path or not qotd_path.exists():
        return default_quote

    try:
        with open(qotd_path, "r") as f:
            quotes = yaml.safe_load(f)
        if quotes and isinstance(quotes, list):
            import random
            q = random.choice(quotes)
            return q.get("txt", default_quote[0]), q.get("by", default_quote[1])
    except Exception as e:
        log.warning(f"Failed to load QOTD from {qotd_path.name}: {e}")

    return default_quote


def local_time_to_utc(dt: datetime, tz_offset_hours: int = 2) -> datetime:
    """Converts a local time datetime to UTC assuming offset hours."""
    return dt - timedelta(hours=tz_offset_hours)


def is_time_in_local_range(dt: datetime, range_local: tuple[str, str], tz_offset_hours: int = 2) -> bool:
    """Checks if a UTC datetime falls within a local time window (e.g. 05:00 to 17:00 CEST)."""
    # Convert UTC datetime to local representation
    local_dt = dt + timedelta(hours=tz_offset_hours)
    local_time_str = local_dt.strftime("%H:%M")

    start_str, end_str = range_local
    return start_str <= local_time_str <= end_str


def run_job(cfg: JobConfig, nc_file: Path, base_date: datetime) -> None:
    """Runs a single simulation JobConfig, generates GPX tracks, daily maps, and emails the results."""
    log.info(f"Executing active Job: {cfg.title}")

    # Open NetCDF dataset
    log.info(f"Opening CMEMS forecast file: {nc_file.name}")
    ds = xr.open_dataset(nc_file)

    # 1. Classify grid cell coastline background (Land/Boundary/Water)
    status_mask, _ = classify_grid_cells(ds)
    lat_coord = 'latitude' if 'latitude' in ds.coords else 'lat'
    lon_coord = 'longitude' if 'longitude' in ds.coords else 'lon'
    lats = ds[lat_coord].values
    lons = ds[lon_coord].values

    # 2. Resolve calculation calendar windows
    eval_dates = parse_date_range_expr(cfg.date_range_expr, base_date)
    log.info(f"Resolved simulation calendar window: {', '.join([d.strftime('%Y-%m-%d') for d in eval_dates])}")

    for day in eval_dates:
        log.info(f"--- Processing simulations for: {day.strftime('%Y-%m-%d')} ---")
        day_start = day.replace(hour=0, minute=0, second=0, microsecond=0).replace(tzinfo=timezone.utc)
        day_end = day_start + timedelta(hours=23, minutes=59, seconds=59)

        # Build list of calculations with trajectories for this day
        daily_runs = []
        model = CmemsForecastCurrentsModel(ds)

        for calc in cfg.calculations:
            # If dynamic peak detection is enabled
            if calc.start_time_detect:
                # Find tidal current peaks near start position
                peaks = find_daily_tide_peaks(ds, calc.from_pos, day_start, day_end)
                log.info(f"Detected {len(peaks)} physical tide peaks in 24h window (UTC).")

                # Process matching peaks
                for p in peaks:
                    p_type = p["type"]
                    # Match peaks allowed by YAML types (e.g. 'pfc' or 'pec')
                    if p_type.lower() in calc.start_time_detect:
                        p_time_utc = p["time"]

                        # Apply user's local day-swim constraint (e.g., CEST 05:00-17:00)
                        if calc.detect_in_range_local:
                            if not is_time_in_local_range(p_time_utc, calc.detect_in_range_local):
                                continue

                        log.info(
                            f"Matched Peak: {p_type} at {p_time_utc.strftime('%H:%M')} UTC. "
                            f"Simulating heading {calc.bearing_deg}° N for {calc.duration_hours}h..."
                        )

                        # Run trajectory simulation
                        df_traj = simulate_test_swim(
                            model=model,
                            start_pos=calc.from_pos,
                            start_time=p_time_utc,
                            heading_deg=calc.bearing_deg,
                            duration_hours=calc.duration_hours
                        )

                        daily_runs.append((df_traj, p_type, p_time_utc, calc))

            elif calc.start_time_exact:
                # Run with exact specified start-time (if inside this day's window)
                p_time_utc = calc.start_time_exact
                if day_start <= p_time_utc <= day_end:
                    log.info(f"Simulating exact start: {p_time_utc.isoformat()} | {calc.bearing_deg}° N...")
                    df_traj = simulate_test_swim(
                        model=model,
                        start_pos=calc.from_pos,
                        start_time=p_time_utc,
                        heading_deg=calc.bearing_deg,
                        duration_hours=calc.duration_hours
                    )
                    daily_runs.append((df_traj, "CUSTOM", p_time_utc, calc))

        if not daily_runs:
            log.info(f"No simulations scheduled or resolved for {day.strftime('%Y-%m-%d')}.")
            continue

        # 3. Create results folder & Export outputs
        results_dir = Path("./data_store/predictions")
        if cfg.results and cfg.results.output_folder_template:
            # Replace placeholder variables
            now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            folder_path = cfg.results.output_folder_template.replace("{now}", now_str)
            results_dir = Path(folder_path)

        results_dir.mkdir(parents=True, exist_ok=True)

        # Overview Map Plotting
        overview_filename = f"{day.strftime('%Y-%m-%d')}-overview.png"
        if cfg.results and cfg.results.overview_file_template:
            overview_filename = cfg.results.overview_file_template.replace("{date}", day.strftime("%Y-%m-%d"))

        overview_path = results_dir / overview_filename

        plot_data_list = []
        gpx_attachments = []
        calc_summaries = []

        for df_traj, run_type, start_dt, calc_cfg in daily_runs:
            # Local CEST representations for placeholders
            local_dt = start_dt + timedelta(hours=2)
            local_time_str = local_dt.strftime("%H%M")
            local_time_formatted = local_dt.strftime("%H:%M")

            # Fully resolve dynamic placeholders in calc_id
            resolved_calc_id = calc_cfg.calc_id \
                .replace("{date}", day.strftime("%Y-%m-%d")) \
                .replace("{time}", local_time_str)

            # GPX export
            gpx_name = f"{day.strftime('%Y-%m-%d')}-{resolved_calc_id}.gpx"
            if cfg.results and cfg.results.gpx_file_template:
                gpx_name = cfg.results.gpx_file_template \
                    .replace("{date}", day.strftime("%Y-%m-%d")) \
                    .replace("{calc.id}", resolved_calc_id)

            gpx_path = results_dir / gpx_name
            track_label = f"{run_type} Run - {local_time_formatted} CEST"
            write_gpx_track(df_traj, track_label, gpx_path)
            gpx_attachments.append(gpx_path)

            calc_summaries.append({
                "start_time_local": local_time_formatted,
                "type": "PVS (Vloed)" if run_type == "PFC" else "PES (Eb)" if run_type == "PEC" else "Custom",
                "bearing": calc_cfg.bearing_deg,
                "duration": f"{calc_cfg.duration_hours}h",
                "gpx_filename": gpx_name
            })

            plot_data_list.append((df_traj, run_type, start_dt))

        # Render and save daily map plot
        plot_daily_simulations(
            df_list=plot_data_list,
            day_label=day.strftime('%d %B %Y'),
            output_path=overview_path,
            status_mask=status_mask,
            lats=lats,
            lons=lons,
            coastline_wkt_path=cfg.extra.coastline_path,
            obstructions_wkt_path=cfg.extra.obstructions_path
        )

        # 4. SMTP HTML Email Dispatch
        if cfg.results and cfg.results.mail:
            mail_cfg = cfg.results.mail
            template_path = mail_cfg.template_path or Path("./data/simulation/email-template.html")

            if not template_path.exists():
                log.warning(f"Email template not found: {template_path}. Using fallback text.")
                html_body = f"Simulation results for {day.strftime('%Y-%m-%d')}. Visuals and GPX files attached."
            else:
                qotd_txt, qotd_by = load_random_qotd(cfg.extra.qotd_path)
                with open(template_path, "r") as tf:
                    jinja_template = Template(tf.read())
                    html_body = jinja_template.render(
                        job_title=cfg.title,
                        date=day.strftime("%d-%m-%Y"),
                        now=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
                        qotd_text=qotd_txt,
                        qotd_author=qotd_by,
                        calculations=calc_summaries
                    )

            subject = mail_cfg.subject_template \
                .replace("{date}", day.strftime("%Y-%m-%d")) \
                .replace("{now}", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

            attachments = []
            if mail_cfg.attach_mode in ("all", "gpx"):
                attachments.extend(gpx_attachments)

            overview_map_embed = overview_path if mail_cfg.attach_mode in ("all", "overview") else None

            try:
                send_simulation_email(
                    to_list=mail_cfg.to_list,
                    subject=subject,
                    html_body=html_body,
                    overview_map_path=overview_map_embed,
                    attachment_paths=attachments
                )
            except Exception as e:
                log.error(f"Email delivery skipped or failed during SMTP send: {e}")


def main() -> None:
    """Main CLI controller for retrieving and executing the tidal simulation jobs."""
    load_dotenv()

    configure_logging()
    log.info("Starting automated test-swim simulation pipeline...")

    parser = argparse.ArgumentParser(description="CSCM Autonomous Swim Trajectory Simulator")
    parser.add_argument("--jobs-dir", type=str, default="./data/simulation/jobs",
                        help="Path to folder containing YAML simulation jobs")
    parser.add_argument("--storage-dir", type=str, default="./data/cmems",
                        help="CMEMS local forecast NetCDF files folder")
    parser.add_argument("--force", action="store_true", help="Force recalculate and bypass cache rules")
    parser.add_argument("--date", type=str, default=None, help="Evaluation anchor date (YYYY-MM-DD)")
    args = parser.parse_args()

    # Load target directories
    jobs_dir = Path(args.jobs_dir)
    storage_dir = Path(args.storage_dir)

    # 1. Resolve active forecast file
    nc_file = get_latest_forecast_nc(storage_dir)
    if not nc_file:
        log.error(f"Cannot run simulation engine: No Copernicus Marine forecast (*.nc) files found on disk. Please check the storage directory: {storage_dir}")
        sys.exit(1)

    log.info(f"Using CMEMS NetCDF forecast database: {nc_file}")

    # 2. Resolve anchor evaluation datetime
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    if args.date:
        try:
            today = pd.to_datetime(args.date).replace(tzinfo=timezone.utc)
        except Exception as e:
            log.error(f"Invalid evaluation date format '{args.date}': {e}")
            sys.exit(1)

    log.info(f"Running in-range job checks for evaluation date: {today.strftime('%Y-%m-%d')}")

    # 3. Read and execute active YAML jobs
    if not jobs_dir.exists():
        log.error(f"Jobs folder does not exist: {jobs_dir}")
        sys.exit(1)

    job_files = list(jobs_dir.glob("*.yaml")) + list(jobs_dir.glob("*.yml"))
    if not job_files:
        log.warning(f"No simulation YAML jobs found in: {jobs_dir}")
        sys.exit(0)

    for job_path in job_files:
        try:
            cfg = parse_job_file(job_path)

            # Skip inactive jobs
            if not cfg.active.on:
                log.info(f"Skipping job: {cfg.title} (Reason: if-on=false)")
                continue

            # Check inside valid calendar range
            if cfg.active.begin_date and today < cfg.active.begin_date:
                log.info(f"Skipping job: {cfg.title} (Reason: before begin-date {cfg.active.begin_date.strftime('%Y-%m-%d')})")
                continue
            if cfg.active.end_date and today > cfg.active.end_date:
                log.info(f"Skipping job: {cfg.title} (Reason: after end-date {cfg.active.end_date.strftime('%Y-%m-%d')})")
                continue

            # Run simulations
            run_job(cfg, nc_file, today)

        except Exception as e:
            log.error(f"Failed to execute job {job_path.name}: {e}", exc_info=True)

    log.info("Simulation pipeline finished successfully!")


if __name__ == "__main__":
    main()
