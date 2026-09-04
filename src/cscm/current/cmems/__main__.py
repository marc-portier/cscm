# src/cscm/current/cmems/__main__.py

import argparse
import logging
import os
import sys
from pathlib import Path
from dotenv import load_dotenv


def cleanup_storage(storage_folder: Path, clean_mode: str) -> None:
    """
    Cleans up files in the CMEMS data storage folder based on the clean_mode.
    """
    if clean_mode == "none":
        return

    storage_path = Path(storage_folder)
    if not storage_path.exists():
        return

    logging.info(f"Performing cleanup of storage folder {storage_folder} with mode: {clean_mode}")

    if clean_mode == "all":
        # Delete all files and subdirectories
        for item in storage_path.iterdir():
            if item.is_file():
                item.unlink()
            elif item.is_dir():
                import shutil
                shutil.rmtree(item)
    elif clean_mode == "analysis":
        # Delete only analytical and verification files
        for item in storage_path.iterdir():
            if item.is_file():
                if (
                    item.name.endswith("_analysis.json")
                    or item.name.endswith(".png")
                    or item.name.endswith(".gpx")
                    or item.name.endswith(".geojson")
                ):
                    item.unlink()


def main() -> None:
    """
    Main entry point for retrieving and analyzing CMEMS tidal current data.
    """
    load_dotenv()

    # Create command line parser with PEP8 compliance
    parser = argparse.ArgumentParser(
        description="CSCM CMEMS Data Retriever and Tide Analyzer Module."
    )
    parser.add_argument(
        "--skip-update",
        action="store_true",
        help="Skip CMEMS database download update."
    )
    parser.add_argument(
        "--skip-analysis",
        action="store_true",
        help="Skip CMEMS data analysis workflow."
    )
    parser.add_argument(
        "--clean",
        choices=["all", "analysis", "none"],
        default="none",
        help="Cleanup storage level before running processing."
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force full tide analysis, ignoring cached JSON analysis files."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit retrieval and analysis to the N most recent lunar cycles."
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Set the logging level (default: INFO)."
    )

    args = parser.parse_args()

    # Configure logging level and targets
    log_level = getattr(logging, args.log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        handlers=[
            logging.FileHandler("cscm.log", mode="a", encoding="utf-8"),
            logging.StreamHandler(sys.stdout)
        ]
    )

    # Delay heavy imports so dotenv is loaded and logger is configured first
    from cscm.current.cmems.retrieve import CMEMSDataManager
    from cscm.current.cmems.analyse import process_catalog
    from cscm.wellknown import POSITIONS as wk_positions

    cmems_data_manager = CMEMSDataManager()

    # Handle cleaning logic if requested
    if args.clean != "none":
        cleanup_storage(cmems_data_manager.storage_folder, args.clean)
        # Re-initialize catalog since files were deleted
        cmems_data_manager.init_catalog()

    # Check for update downloads unless requested to skip
    if args.skip_update:
        logging.info("Skipping Copernicus CMEMS database download update.")
    else:
        logging.info("Checking Copernicus CMEMS data store for updates.")
        # If limit is set, we pass it to restrict how many future cycles we check
        cmems_data_manager.update_cmems_data()

    if args.skip_analysis:
        logging.info("Skipping CMEMS data analysis workflow.")
        return
    # else:

    # Resolve focal positions for verification diagnostic plots
    focal_env = os.environ.get("CMEMS_FOCAL_POSITIONS", "*")
    if focal_env in ("*", "all", "ALL"):
        logging.info("Wildcard CMEMS_FOCAL_POSITIONS resolved. Selecting all known positions.")
        focal_positions = list(wk_positions.values())
    else:
        focal_position_labels = [label.strip() for label in focal_env.split(",") if label.strip()]
        focal_positions = [
            wk_positions[label]
            for label in focal_position_labels
            if label in wk_positions
        ]

    pos_names = [getattr(p, "label", str(p)) for p in focal_positions]
    logging.info(f"Processing tide analysis for focal positions: {', '.join(pos_names)}")

    # Sort catalog to run newest/forecast data first
    catalog_df = cmems_data_manager.catalog
    if args.limit is not None and not catalog_df.empty:
        # Sort descending to get newest files first
        catalog_df = catalog_df.sort_values(by="nwmn_start_dt", ascending=False)
        catalog_df = catalog_df.head(args.limit)

    process_catalog(
        catalog_df,
        force_recalculate=args.force,
        focal_positions=focal_positions
    )


if __name__ == "__main__":
    main()
