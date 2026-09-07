# src/cscm/simulation/__main__.py

import os
import sys
import argparse
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional
import random
import zoneinfo
from dotenv import load_dotenv

import pandas as pd
import numpy as np
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
    # Return sorted last name order for reliable forecast timestamp matches
    return sorted(nc_files)[-1]


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


def is_time_in_local_range(time_utc: datetime, range_local: tuple[str, str], tz_str: str) -> bool:
    """Checks if a UTC time is within a specified local day time window (e.g. 05:00-17:00 in job timezone)"""
    local_tz = zoneinfo.ZoneInfo(tz_str)
    local_time = time_utc.astimezone(local_tz)
    local_time_str = local_time.strftime('%H:%M')
    start_str, end_str = range_local
    return start_str <= local_time_str <= end_str


def load_random_qotd(qotd_path: Optional[Path]) -> tuple[Optional[str], Optional[str]]:
    """Loads a random Quote Of The Day from the qotd.yml file, or returns (None, None) if not present."""
    if not qotd_path or not qotd_path.exists():
        return None, None

    try:
        with open(qotd_path, "r", encoding="utf-8") as f:
            quotes = yaml.safe_load(f)
            if quotes and isinstance(quotes, list):
                q = random.choice(quotes)
                return q.get("txt", q.get("text", "")), q.get("by", q.get("author", ""))
    except Exception as e:
        log.warning(f"Could not load quote from {qotd_path}: {e}")

    return None, None


def run_job(cfg: JobConfig, nc_file: Path, base_date: datetime) -> None:
    """Runs a single simulation JobConfig, generates GPX tracks, daily maps, and emails the results."""
    log.info(f"Executing active Job: {cfg.title}")

    # Set up timezone objects
    local_tz = zoneinfo.ZoneInfo(cfg.tz_str)

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
                status_mask, is_boundary_mask = classify_grid_cells(ds)

                # Filter open-water cellen (status 2 = Water, status 1 = Boundary, status 0 = Land)
                valid_coords = []
                for y in range(len(lats)):
                    for x in range(len(lons)):
                        if status_mask[y, x] == 2:  # Alleen zuiver open water
                            valid_coords.append((lats[y], lons[x]))

                if not valid_coords:
                    # Fallback naar alle watercellen als er geen open water is
                    valid_coords = [
                        (lats[y], lons[x])
                        for y in range(len(lats))
                        for x in range(len(lons))
                        if status_mask[y, x] in (1, 2)
                    ]

                valid_coords = np.array(valid_coords).reshape(-1, 2)

                # Snap de startpositie naar het dichtstbijzijnde open water
                dists = (valid_coords[:, 0] - calc.from_pos.lat)**2 + (valid_coords[:, 1] - calc.from_pos.lon)**2
                best_idx = np.argmin(dists)
                snapped_pos = Position(valid_coords[best_idx, 0], valid_coords[best_idx, 1])

                log.info(
                    f"Snapping startpositie '{calc.from_pos}' naar open water cel: "
                    f"[{snapped_pos.lat:.5f}N, {snapped_pos.lon:.5f}E]"
                )

                # Gebruik nu snapped_pos voor piekdetectie en simulatie!
                peaks = find_daily_tide_peaks(ds, snapped_pos, day_start, day_end)
                log.info(f"Detected {len(peaks)} physical tide peaks in 24h window (UTC).")

                # Process matching peaks
                for p in peaks:
                    p_type = p["type"]
                    # Match peaks allowed by YAML types (e.g. 'pfc' or 'pec')
                    if p_type.lower() in calc.start_time_detect:
                        p_time_utc = p["time"]

                        # Apply user's local day-swim constraint (e.g., CEST 05:00-17:00)
                        if calc.detect_in_range_local:
                            if not is_time_in_local_range(p_time_utc, calc.detect_in_range_local, cfg.tz_str):
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
            # Local representations for placeholders
            local_dt = start_dt.astimezone(local_tz)
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
            track_label = f"{run_type} Run - {local_time_formatted} {local_tz.tzname(local_dt)}"
            write_gpx_track(df_traj, track_label, gpx_path)
            gpx_attachments.append(gpx_path)

            calc_summaries.append({
                "start_time_local": local_time_formatted,
                "type": "PFC (Flood)" if run_type == "PFC" else "PEC (Ebb)" if run_type == "PEC" else "Custom",
                "bearing": calc_cfg.bearing_deg,
                "duration": f"{calc_cfg.duration_hours}h",
                "gpx_filename": gpx_name
            })

            plot_data_list.append((df_traj, run_type, start_dt, calc_cfg))

        # Render and save daily map plot
        plot_daily_simulations(
            df_list=plot_data_list,
            day_label=day.strftime('%d %B %Y'),
            output_path=overview_path,
            status_mask=status_mask,
            lats=lats,
            lons=lons,
            model=model,  # Pass the currents model!
            coastline_wkt_path=cfg.extra.coastline_path,
            obstructions_wkt_path=cfg.extra.obstructions_path,
            colors_cfg=cfg.results.colors if cfg.results else None,
            labels_cfg=cfg.results.labels if cfg.results else None
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
                now_local = datetime.now(timezone.utc).astimezone(local_tz)
                now_local_str = now_local.strftime("%Y-%m-%d %H:%M")

                with open(template_path, "r", encoding="utf-8") as tf:
                    jinja_template = Template(tf.read())
                    html_body = jinja_template.render(
                        job_title=cfg.title,
                        date=day.strftime("%d-%m-%Y"),
                        now=now_local_str,
                        tz_name=local_tz.tzname(now_local),
                        qotd_text=qotd_txt,
                        qotd_author=qotd_by,
                        calculations=calc_summaries
                    )

            # Format email subject with local time offsets
            now_local = datetime.now(timezone.utc).astimezone(local_tz)
            now_local_str = now_local.strftime("%Y-%m-%d %H:%M:%S")
            subject = mail_cfg.subject_template \
                .replace("{date}", day.strftime("%Y-%m-%d")) \
                .replace("{now}", now_local_str)

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
    """Main entry point for CSCM automated trajectory simulation."""
    configure_logging()
    load_dotenv()

    parser = argparse.ArgumentParser(description="CSCM Automated Test Swim Trajectory Simulator.")
    parser.add_argument("--job-dir", default="./data/simulation/jobs", help="Path to jobs folder.")
    parser.add_argument("--data-dir", default="./data/cmems", help="Path to CMEMS forecast storage.")
    parser.add_argument("--output-dir", default="./data_store/predictions", help="Path to save outputs.")
    parser.add_argument("--skip-update", action="store_true", help="Skip checking Copernicus CMEMS database download update.")
    parser.add_argument("--cron-install", action="store_true", help="Generate a secure cron execution template in /tmp")

    args = parser.parse_args()

    # Handle cron-install templates instantly
    if args.cron_install:
        project_root = Path(os.getcwd()).resolve()
        cron_script_path = Path("/tmp/cscm_daily_prediction")
        cron_content = f"""#!/bin/bash
# CSCM Daily Automated Prediction Cron Executable
# Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

# Move to absolute project root directory
cd {project_root}

# Pull Copernicus live forecast updates and execute simulation jobs
poetry run python -m cscm.simulation
"""
        with open(cron_script_path, "w", encoding="utf-8") as cf:
            cf.write(cron_content)

        try:
            os.chmod(cron_script_path, 0o755)
        except Exception:
            pass

        print("\n" + "="*80)
        print(" CSCM CRON-INSTALL GENERATOR ")
        print("="*80)
        print(f"Daily cron executable template written successfully to: {cron_script_path}")
        print("\nTo install this as an automated daily job on your Ubuntu server:")
        print(f"  sudo mv {cron_script_path} /etc/cron.daily/cscm-prediction")
        print("  sudo chown root:root /etc/cron.daily/cscm-prediction")
        print("  sudo chmod +x /etc/cron.daily/cscm-prediction")
        print("\nThis will run predictions autonomously at 03:00 every night (default daily trigger).")
        print("="*80 + "\n")
        sys.exit(0)

    job_dir = Path(args.job_dir)
    data_dir = Path(args.data_dir)

    # Clean fallback for directories
    if not job_dir.exists():
        log.warning(f"Job directory {job_dir} not found. Defaulting to scratch test.")
        job_dir = Path("/workspace/scratch/data/simulation/jobs")
    if not data_dir.exists():
        data_dir = Path("/workspace/scratch")

    # Delay heavy imports so dotenv is loaded and logger is configured first
    from cscm.current.cmems.retrieve import CMEMSDataManager

    cmems_data_manager = CMEMSDataManager()

    # Automatically fetch latest updates unless update is skipped
    if args.skip_update:
        log.info("Skipping Copernicus CMEMS database update checks as requested (--skip-update).")
    else:
        log.info("Checking Copernicus CMEMS data store for live forecast updates...")
        try:
            cmems_data_manager.update_cmems_data()
        except Exception as e:
            log.error(f"Failed to retrieve live forecast update: {e}")

    nc_file = get_latest_forecast_nc(data_dir)
    if not nc_file:
        log.error("Cannot run simulation engine: No Copernicus Marine forecast (*.nc) files found on disk.")
        sys.exit(1)

    log.info(f"Using CMEMS NetCDF forecast database: {nc_file}")

    job_files = list(job_dir.glob("*.yaml")) + list(job_dir.glob("*.yml"))
    if not job_files:
        log.warning("No YAML simulation job files found in job directory.")
        return

    today = datetime.now()

    for j_file in job_files:
        try:
            cfg = parse_job_file(j_file)
            if not cfg.active.on:
                log.info(f"Skipping job {j_file.name}: disabled in config.")
                continue

            # Check if active window matches today
            if cfg.active.begin_date and cfg.active.end_date:
                begin_utc = cfg.active.begin_date.replace(tzinfo=timezone.utc)
                end_utc = cfg.active.end_date.replace(tzinfo=timezone.utc)
                today_utc = today.replace(tzinfo=timezone.utc)
                if not (begin_utc <= today_utc <= end_utc):
                    log.info(f"Skipping job {j_file.name}: today is outside active range.")
                    continue

            run_job(cfg, nc_file, today)
        except Exception as e:
            log.error(f"Failed to execute job {j_file.name}: {e}", exc_info=True)

    log.info("Simulation pipeline finished successfully!")


if __name__ == "__main__":
    main()
