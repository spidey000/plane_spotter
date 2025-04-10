import asyncio
import json
from loguru import logger
import utils.data_processing as dp
from api import api_handler_aeroapi, api_handler_aerodatabox
import database.baserow_manager as bm
import socials.socials_processing as sp
from datetime import datetime, timedelta
import sys
from pathlib import Path
import config.config as cfg

# Add project root to Python path
sys.path.append(str(Path(__file__).parent.parent))

# Load configuration
config = cfg.load_config()

# initialize the logger and log into a file in /logs folder with the current date and time in the format of "YYYY-MM-DD_HH-MM-SS" 
logger.remove()
logger.add(f"logs/lemd_spotter.log", level="DEBUG", enqueue=True, rotation="10 MB")
logger.add(f"logs/lemd_spotter_warning.log", level="WARNING", enqueue=True, rotation="10 MB")
logger.add(sys.stdout,level="INFO")


all_flights = {}
models = {}

#handles the logic and shedule

def add_flight_to_db(flight):
    # use baserow manager to add flights to the database
    bm.create()



# loads the flight information from the api
async def main(all_flights):
    from datetime import datetime, timedelta
    now = datetime.now()  # Use local time instead of UTC
    start_time = (now + timedelta(hours=0)).strftime('%Y-%m-%dT%H:%M')
    end_time = (now + timedelta(hours=2)).strftime('%Y-%m-%dT%H:%M')

    for movement in ['arrivals', 'departures']:
        aeroapi_movement = 'scheduled_arrivals' if movement == 'arrivals' else 'scheduled_departures'
        # fetch the data from the api

        prealoaded_data = True
        # comment for production
        # Check if aeroapi data file exists

        if prealoaded_data:
            logger.info("Loading data from preloaded files")
            aeroapi_file = f'api/data/aeroapi_data_scheduled_{movement}.json'
            try:
                with open(aeroapi_file, 'r') as f:
                    temp_aeroapi_data = json.load(f)
                    logger.info(f"Loaded aeroapi data from {aeroapi_file}")
            except :
                logger.info("Preloaded files not found")
                break
            # Check if aerodatabox data file exists
            adb_file = f'api/data/adb_data_{movement}.json'
            try:
                with open(adb_file, 'r') as f:
                    temp_adb_data = json.load(f)
                    logger.info(f"Loaded aerodatabox data from {adb_file}")
            except :
                logger.info("Preloaded files not found")
                break
        else:
            logger.info(f"Fetching data from API between {start_time} and {end_time}")
            temp_aeroapi_data = await api_handler_aeroapi.fetch_aeroapi_scheduled(movement, start_time, end_time)
            temp_adb_data = await api_handler_aerodatabox.fetch_adb_data(movement, start_time, end_time)
            
        # uncomment for production
        # temp_aeroapi_data = api_handler_aeroapi.fetch_aeroapi_scheduled(movement, start_time, end_time)
        # temp_adb_data = api_handler_aerodatabox.fetch_adb_data(movement, start_time, end_time)

        #iterate over every flight to get it into the database
        logger.info(f"Processing ADB data for {movement}")
        logger.info(f"Vuelos {len(temp_adb_data.get(movement, []))}")
        iata_call = set()
        call = set()

        for flight in temp_adb_data.get(movement, []):           
            # process the data
            try:
                processed_data = dp.process_flight_data_adb(flight, movement)
                flight_name = processed_data.get('flight_name_iata', processed_data.get('flight_name', None))
                #log the flight name
                logger.debug(f"Parsed {movement} flight {flight_name}")
            except Exception as e:
                logger.error(f"Error procesando vuelo {e}")
                continue          
            dp.check_existing(all_flights, processed_data)
            iata_call.add(processed_data['flight_name_iata'] if processed_data['flight_name_iata'] else 'null')

        logger.info(f"Total vuelos {len(all_flights)}")

        logger.info(f"Processing AeroAPI data for {movement}")
        logger.info(f"Vuelos {len(temp_aeroapi_data[f"scheduled_{movement}"])}")
        for flight in temp_aeroapi_data[f"scheduled_{movement}"]:
            # process the data
            try:
                processed_data = dp.process_flight_data_aeroapi(flight)
                flight_name = processed_data.get('flight_name_iata', processed_data.get('flight_name', None))
                #log the flight name
                logger.debug(f"Parsed {movement} flight {flight_name}", color="yellow")
            except Exception as e:
                logger.error(f"Error procesando vuelo {e}")
                continue
            
            #check and update none/null values
            dp.check_existing(all_flights, processed_data)

        logger.info(f"Total vuelos {len(all_flights)}")
            
            # compare the flight to the registration, airline and aircraft airtables
    
    # generate a dictionary for all the database flights
    # all registrations table '441094'
    # to check interesting models '441097'


    reg_db_copy = await bm.get_all_rows_as_dict(441094)
    model_db_copy = await bm.get_all_rows_as_dict(441097, key = "model")

    # for each flight in all_flights call baserow manager to add it to the database
    for flight in all_flights:
        if all_flights[flight]["registration"] != None:
            logger.debug(f"Processing flight {all_flights[flight]['flight_name']} in Baserow")
            flight_data, interesting_registration, interesting_model, first_seen = await dp.check_flight(all_flights[flight], reg_db_copy, model_db_copy)

        else:
            #check flight model 
            flight_data, interesting_registration, interesting_model, first_seen = await dp.check_flight(all_flights[flight], reg_db_copy, model_db_copy)
        
        INTERESTING_REASONS = {
                "MODEL": interesting_model,
                "REGISTRATION": interesting_registration,
                "FIRST_SEEN": first_seen,
                "DIVERTED": False if all_flights[flight]["diverted"] == 'null' else all_flights[flight]["diverted"],
            }
        interesting = INTERESTING_REASONS.copy()  # Create a fresh copy
                
        if any(interesting.values()):  # Check if any reason is True
            logger.level("INFO", color="<red>")
            logger.info(f"Flight {flight_data['flight_name'] if flight_data['flight_name'] not in [None, 'null'] else flight_data['flight_name_iata']} is interesting - generating socials message because of {interesting}")
            logger.level("INFO", color="<white>")
            logger.debug(flight_data)
            await sp.call_socials(all_flights[flight], interesting)

    # reinitialize the flights dict to store the new data
    # aircraft_set = set()
    # for flight in all_flights.values():
    #     if flight['aircraft'] != 'null':
    #         aircraft_set.add(flight['aircraft'])
    # # print(aircraft_set)

    all_flights = {}

async def run_periodically():


    await main(all_flights)
    logger.info("Next round at " + (datetime.now() + timedelta(hours=2)).strftime("%Y-%m-%d %H:%M"))
    await asyncio.sleep((2 * 60 * 60)-600)  # Sleep for 2 hours minus 10 minutes


if __name__ == "__main__":
    try:
        asyncio.run(run_periodically())
    except KeyboardInterrupt:
        logger.info("Program stopped by user")
