# src/cscm/current/cmems/__main__.py

# Note: intentionally this does not import anything before the main function
# mainly because the copernicusmarinse package initialises by reading env vars
# in our case these are set in .env and need to be loaded first
def retrieve():
    from dotenv import load_dotenv
    load_dotenv()

    from cscm.current.cmems.retrieve import CMEMSDataManager

    cmems_data_manager = CMEMSDataManager()
    cmems_data_manager.update_cmems_date()


if __name__ == "__main__":
    retrieve()
