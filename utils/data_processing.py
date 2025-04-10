# this loads the fligth data from the apis and stores it in the database
# compare flights by flight_name in both api calls and merge the most information in the database

from datetime import datetime
import database.baserow_manager as bm
from loguru import logger

def process_flight_data_adb(flight, movement):
    # Extract flight information
    try:
        registration = flight['aircraft']['reg']
    except Exception as e:
        logger.debug(f"Failed to get registration: {e}")
        registration = 'null'


    flight_name = flight.get('callSign', 'null')
    flight_name_iata = flight.get('number', 'null')


    aircraft_name = flight['aircraft'].get('model', 'null')
    airline = flight['airline'].get('icao', 'null')
    airline_name = flight['airline'].get('name', 'null')

    if movement == 'departures':
        destination_icao = flight['arrival']['airport']['icao']
        destination_name = flight['arrival']['airport']['name']
        origin_icao = "LEMD"
        origin_name = "Madrid"
    else:
        origin_icao = flight['departure']['airport']['icao']
        origin_name = flight['departure']['airport']['name']
        destination_icao = "LEMD"
        destination_name = "Madrid"

    terminal = flight[movement.removesuffix('s')].get('terminal', 'null')
    diverted = 'null'
    
    # Get scheduled time and convert to datetime object
    try:
        scheduled_time_str = flight[movement.removesuffix('s')]['revisedTime']['local'][:-6]
        scheduled_time = datetime.strptime(scheduled_time_str, "%Y-%m-%d %H:%M")
    except Exception as e:
        logger.error(f"Failed to parse scheduled time: {e}")
        scheduled_time = datetime.now()
    
    # Get last update time (use revised time if available, otherwise scheduled time)
    last_update = datetime.now().strftime("%Y-%m-%d %H:%M")

    single_flight_data = {
        'flight_name': "".join(flight_name.split()),
        'flight_name_iata': flight_name_iata,
        'registration': registration,
        'aircraft_name': aircraft_name.strip(),
        'aircraft_icao': None,
        'airline': airline,
        'airline_name': airline_name,
        'origin_icao': origin_icao,
        'origin_name': origin_name,
        'destination_icao': destination_icao,
        'destination_name': destination_name,
        'terminal': terminal,
        'scheduled_time': scheduled_time,
        'last_update': last_update,
        'diverted': diverted
    }

    logger.debug(f"Processed ADB flight data: {single_flight_data}")
    return single_flight_data

def get_valid_value(flight, keys, default='null'):
    """Returns the first non-null and non-'null' value from the flight dictionary."""
    return next((flight.get(k) for k in keys if flight.get(k) not in [None, 'null']), default)

def process_flight_data_aeroapi(flight):
    try:
        registration = flight["registration"]
    except Exception as e:
        logger.warning(f"Failed to get registration: {e}")
        return None
    
    is_departure = flight.get("origin", {}).get("code_icao") == "LEMD"
    
    if is_departure:
        scheduled_time = get_valid_value(flight, ["actual_out", "estimated_out", "scheduled_out"])
        terminal = flight.get("terminal_origin", 'null')
        origin_icao, origin_name = 'LEMD', 'Madrid'
        destination_icao = flight.get("destination", {}).get("code_icao", 'null')
        destination_name = flight.get("destination", {}).get("name", 'null')
    else:
        scheduled_time = get_valid_value(flight, ["actual_out", "estimated_off", "scheduled_off"])
        terminal = flight.get("terminal_destination", 'null')
        origin_icao = flight.get("origin", {}).get("code_icao", 'null')
        origin_name = flight.get("origin", {}).get("name", 'null')
        destination_icao, destination_name = 'LEMD', 'Madrid'
    
    flight_name = get_valid_value(flight, ['atc_ident', 'ident_icao'])
    flight_name_iata = get_valid_value(flight, ['ident_iata', 'null'])
    aircraft = flight.get("aircraft_type", 'null')
    airline = flight.get("operator_icao", 'null')
    airline_name = flight.get("operator", 'null')
    diverted = flight.get("diverted", 'null')

    # Get last update time
    last_update = datetime.now().strftime("%Y-%m-%d %H:%M")

    single_flight_data = {
        'flight_name': "".join(flight_name.split()),
        'flight_name_iata': flight_name_iata,
        'registration': registration,
        'aircraft_name': None,
        'aircraft_icao': aircraft.strip(),
        'airline': airline,
        'airline_name': airline_name,
        'origin_icao': origin_icao,
        'origin_name': origin_name,
        'destination_icao': destination_icao,
        'destination_name': destination_name,
        'terminal': terminal,
        'scheduled_time': datetime.strptime(scheduled_time[:-4], "%Y-%m-%dT%H:%M"),
        'last_update': last_update,
        'diverted': diverted
    }

    logger.debug(f"Processed AeroAPI flight data: {single_flight_data}")
    return single_flight_data

async def check_flight(flight, reg_db, model_db):
    interesting_registration = False
    interesting_model = False
    first_seen = False        

    # Convert scheduled_time to string if needed
    if not isinstance(flight['scheduled_time'], str):
        flight['scheduled_time'] = flight['scheduled_time'].strftime("%Y-%m-%d %H:%M")
        logger.debug(f"Converted scheduled_time to string format")
    
    if flight['registration'] not in ['null', None]:
        if flight['registration'] in reg_db:
            db_reg = reg_db[flight['registration']]
            logger.debug(f"Flight {flight['registration']} has been seen before")
            
            if db_reg['reason'] not in ['null', None]:
                logger.info(f"Flight {flight['registration']} is in interesting registrations table")
                interesting_registration = True
                
            for model_entry in model_db.values():
                try:
                    interesting_model = True if model_entry['model'].lower() == flight['aircraft_icao'].lower() else False
                except Exception as e:
                    logger.debug(f"Model comparison error: {e}")
                    interesting_model = True if model_entry['name'].lower() in flight['aircraft_name'].lower() else False
                if interesting_model:
                    logger.info(f"Flight {flight['registration']} matches interesting model {model_entry['model']}")
                    break
            # Update last seen value
            times_seen = db_reg['times_seen']
            payload = {
                'last_seen': flight['scheduled_time'], 
                'times_seen': int(times_seen) + 1
            }
            try:
                # await bm.update_record('441094', payload, flight)
                logger.debug(f"Updated record for {flight['registration']} in table 441094")
            except Exception as e:
                logger.error(f"Failed to update record for {flight['registration']}: {e}")

        else:
            # New registration
            payload = {
                "registration": flight['registration'],
                "first_seen": flight['scheduled_time'],
                "last_seen": flight['scheduled_time'],
                "times_seen": 1,
                "reason": None
            }
            try:
                await bm.create_record('441094', payload)
                logger.success(f"Created new record for {flight['registration']} in table 441094")
                first_seen = True
            except Exception as e:
                logger.error(f"Failed to create record for {flight['registration']}: {e}")
    else:
        for model_entry in model_db.values():
            try:
                interesting_model = True if model_entry['model'].lower() == flight['aircraft_icao'].lower() else False
            except Exception as e:
                logger.debug(f"Model comparison error: {e}")
                interesting_model = True if model_entry['name'].lower() in flight['aircraft_name'].lower() else False
            if interesting_model:
                logger.info(f"Flight {flight['registration']} matches interesting model {model_entry['model']}")
                break

    return flight, interesting_registration, interesting_model, first_seen

# If flight already exists, merge data
def check_existing(all_flights, processed_data):
    nameish = ['flight_name_iata', 'flight_name']

    for name in nameish:
        if processed_data.get(name, None) in [None, 'null']:
            continue
        else:
            if name == 'flight_name_iata' and processed_data.get('flight_name', None) in all_flights:
                for key, value in processed_data.items():
                    if all_flights[name].get(key) in [None, 'null'] and value not in [None, 'null']:
                        all_flights[name][key] = value
                        logger.debug(f"Updated {key} for {name}")

            else:
                # Add new flight data
                all_flights[processed_data.get('flight_name_iata')] = processed_data
