# src/cscm/current/cmems/__main__.py
import os
import sys
import argparse
from dotenv import load_dotenv
from cscm.model import Position

# Note: intentionally this does not import anything from cscm.*.cmems before the main function is called
# mainly because the copernicusmarine package initialises by reading env vars
# in our case these are set in .env and need to be loaded first


def main():
    load_dotenv()

    from cscm.current.cmems.retrieve import CMEMSDataManager
    from cscm.current.cmems.analyse import process_catalog
    from cscm.wellknown import POSITIONS as wkPositions

    # Standard argparse setup for professional command-line flag handling
    parser = argparse.ArgumentParser(description="Copernicus CMEMS Data Retrieval & Analysis Suite")
    parser.add_argument("--clean", action="store_true", help="Delete all downloaded files and companion metadata in the store before running")
    parser.add_argument("--force", action="store_true", help="Force overwrite downloads and force recalculate analysis JSONs")
    parser.add_argument("--limit", type=int, default=None, help="Process only the N most recent moon cycles")
    parser.add_argument("--skip-update", action="store_true", help="Skip the Copernicus downloads and only run analysis on existing files")

    # Use parse_known_args to ignore any unrecognized arguments and avoid crashes
    args, unknown = parser.parse_known_args()

    cmems_data_manager = CMEMSDataManager()

    # 1. Clean storage folder if requested
    if args.clean:
        print(f"Cleaning data store folder: {cmems_data_manager.storage_folder}")
        for file_path in cmems_data_manager.storage_folder.glob("*"):
            if file_path.is_file():
                try:
                    file_path.unlink()
                except Exception as e:
                    print(f"Could not delete file {file_path}: {e}")
        # Re-initialize the empty catalog after cleaning
        cmems_data_manager.init_catalog()

    # 2. Update/retrieve CMEMS data unless skipped
    if args.skip_update:
        print("Skipping CMEMS data update as requested. Running analysis only.")
    else:
        print("Doing CMEMS data update...")
        cmems_data_manager.update_cmems_data(force=args.force, limit=args.limit)

    # 3. Resolve focal points for plot generation
    focal_position_labels: list[str] = os.environ.get("CMEMS_FOCAL_POSITIONS", "KOKSIJDE,BREDENE_POST4").split(",")
    focal_positions: list[Position] = [wkPositions[label] for label in focal_position_labels if label in wkPositions]
    print(f"Processing CMEMS data for focal positions: {', '.join([focal_positions])}")

    # 4. Limit catalog processing if limit is specified
    catalog_to_process = cmems_data_manager.catalog
    if args.limit is not None and args.limit > 0:
        # Sort catalog descending (newest first) and take top N entries
        catalog_to_process = catalog_to_process.sort_values(by="nwmn_start_dt", ascending=False).head(args.limit)
        print(f"Limiting batch analysis to the {args.limit} most recent moon cycles in the catalog.")

    # 5. Process catalog (processes newest moon cycles first)
    process_catalog(
        catalog_to_process,
        force_recalculate=args.force,
        focal_positions=focal_positions
    )


if __name__ == "__main__":
    main()
