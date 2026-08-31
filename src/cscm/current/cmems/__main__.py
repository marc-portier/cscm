import os
import sys
from dotenv import load_dotenv
from cscm.model import Position
# Note: intentionally this does not import anything from cscm.*.cmems before the main function is called
# mainly because the copernicusmarinse package initialises by reading env vars
# in our case these are set in .env and need to be loaded first


def main():
    load_dotenv()

    from cscm.current.cmems.retrieve import CMEMSDataManager
    from cscm.current.cmems.analyse import process_catalog
    from cscm.wellknown import POSITIONS as wkPositions

    cmems_data_manager = CMEMSDataManager()
    # check arguments for --skip-update
    if "--skip-update" in sys.argv:
        print("Skipping CMEMS data update as requested.")
    else:
        print("Doing CMEMS data update first.")
        cmems_data_manager.update_cmems_data()

    focal_position_labels: list[str] = os.environ.get("CMEMS_FOCAL_POSITIONS", "KOKSIJDE,BREDENE_POST4").split(",")
    focal_positions: list[Position] = [wkPositions[label] for label in focal_position_labels if label in wkPositions]

    print(f"Processing CMEMS data for focal positions: {', '.join([p.name for p in focal_positions])}")
    process_catalog(
        cmems_data_manager.catalog,
        focal_positions=focal_positions
    )


if __name__ == "__main__":
    main()
