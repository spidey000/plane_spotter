# this loads the fligth data from the apis and stores it in the database
# compare flights by flight_name in both api calls and merge the most information in the database
import json
from pathlib import Path
from datetime import datetime
import database.baserow_manager as bm
from loguru import logger
from log.logger_config import logger
from pytz import timezone

from config import config_manager # Keep import for type hinting or if other functions need it

def normalize_diverted_value(diverted_val):
    """Normalize diverted value to a consistent boolean or None"""
    if diverted_val in [True, False]:
        return diverted_val
    elif diverted_val == 'null' or diverted_val is None:
        return None
    elif isinstance(diverted_val, str):
        return diverted_val.lower() in ['true', 'yes', '1']
    return None

# Load callsigns database (this is static data, not part of dynamic config)
try:
    with open('database/callsigns.json', 'r', encoding='utf-8') as f:
        callsigns_data = json.load(f)
        # Convert list of dicts to a dictionary with 3-Letter ID as key
        callsigns_dict = {item['3-Letter ID']: item for item in callsigns_data}
    logger.info("Successfully loaded and converted callsigns database")
except FileNotFoundError:
    logger.warning("Callsigns database not found, using empty dict")
    callsigns_dict = {}
except json.JSONDecodeError as e:
    logger.error(f"Error decoding callsigns database: {e}")
    callsigns_dict = {}
except Exception as e:
    logger.error(f"Unexpected error loading callsigns database: {e}")
    callsigns_dict = {}


def process_flight_data_adb(flight, movement, config):
    # Extract flight information
    registration = flight['aircraft'].get('reg', 'null')


    flight_name = flight.get('callSign', 'null')
    flight_name_iata = flight.get('number', 'null')


    aircraft_name = flight['aircraft'].get('model', 'null')
    airline = flight['airline'].get('icao', 'null')
    airline_name = flight['airline'].get('name', 'null')

    # Load airlines database
    import json
    with open('database/airlines.json', 'r', encoding='utf-8') as f:
        airlines_db = json.load(f)
    
    # Get airline name from ICAO if available, otherwise use existing name
    airline_name = airlines_db.get(airline, {}).get('Name', airline_name)
    country = callsigns_dict.get(airline, airlines_db.get(airline, {})).get('Country', 'null')
    callsign = callsigns_dict.get(airline, airlines_db.get(airline, {})).get('Callsign', 'null')

    if movement == 'departures':
        destination_icao = flight.get('arrival', {}).get('airport', {}).get('icao', 'null')
        destination_name = flight.get('arrival', {}).get('airport', {}).get('name', 'null')
        origin_icao = config['settings']['airport']
        origin_name = config['settings']['airport_name']
    else:
        origin_icao = flight.get('departure', {}).get('airport', {}).get('icao', 'null')
        origin_name = flight.get('departure', {}).get('airport', {}).get('name', 'null')
        destination_icao = config['settings']['airport']
        destination_name = config['settings']['airport_name']

    terminal = flight[movement.removesuffix('s')].get('terminal', 'null')
    diverted = flight.get('diverted', 'null')
    diverted = normalize_diverted_value(diverted)
    
    # Get scheduled time and convert to datetime object
    try:
        scheduled_time_str = flight[movement.removesuffix('s')].get('revisedTime', {}).get('local', flight[movement.removesuffix('s')].get('scheduledTime', {}).get('local', ''))[:-6]
        scheduled_time = datetime.strptime(scheduled_time_str, "%Y-%m-%d %H:%M")
    except Exception as e:
        logger.error(f"Failed to parse scheduled time: {e}")
        scheduled_time = datetime.now()
    
    # Get last update time (use revised time if available, otherwise scheduled time)
    last_update = datetime.now().strftime("%Y-%m-%d %H:%M")

    single_flight_data = {
        'callsign': callsign.capitalize(),
        'flight_name': "".join(flight_name.split()) if flight_name else 'null',
        'flight_name_iata': "".join(flight_name_iata.split()) if flight_name_iata else 'null',
        'registration': registration,
        'aircraft_name': aircraft_name.strip(),
        'aircraft_icao': None,
        'airline': airline,
        'airline_name': airline_name,
        'country': country.capitalize(),
        'origin_icao': origin_icao,
        'origin_name': origin_name,
        'destination_icao': destination_icao,
        'destination_name': destination_name,
        'terminal': terminal,
        'scheduled_time': scheduled_time,
        'last_update': last_update,
        'diverted': diverted
    }

    #logger.debug(f"Processed ADB flight data: {single_flight_data}")
    return single_flight_data

def get_valid_value(flight, keys, default='null'):
    """Returns the first non-null and non-'null' value from the flight dictionary."""
    return next((flight.get(k) for k in keys if flight.get(k) not in [None, 'null']), default)

def process_flight_data_aeroapi(flight, config):
    try:
        registration = flight["registration"]
    except Exception as e:
        logger.warning(f"Failed to get registration: {e}")
        return None
    
    is_departure = flight.get("origin", {}).get("code_icao").lower() == config['settings']['airport'].lower()
    
    if is_departure:
        scheduled_time = get_valid_value(flight, ["actual_off", "estimated_off", "scheduled_off"])
        terminal = flight.get("terminal_origin", 'null')
        origin_icao, origin_name = config['settings']['airport'], config['settings']['airport_name']
        destination_icao = flight.get("destination", {}).get("code_icao", 'null')
        destination_name = flight.get("destination", {}).get("name", 'null')
    else:
        scheduled_time = get_valid_value(flight, [ "estimated_on", "estimated_in", "scheduled_on",  "scheduled_in"])
        terminal = flight.get("terminal_destination", 'null')
        origin_icao = flight.get("origin", {}).get("code_icao", 'null')
        origin_name = flight.get("origin", {}).get("name", 'null')
        destination_icao, destination_name = config['settings']['airport'], config['settings']['airport_name']
    
    # Convert UTC to Madrid time (CET/CEST)
    if scheduled_time != 'null':
        utc_time = datetime.strptime(scheduled_time[:-4], "%Y-%m-%dT%H:%M")
        utc_time = utc_time.replace(tzinfo=timezone('UTC'))
        madrid_time = utc_time.astimezone(timezone('Europe/Madrid'))
        scheduled_time = madrid_time.strftime("%Y-%m-%d %H:%M")

    flight_name = get_valid_value(flight, ['atc_ident', 'ident_icao'])
    flight_name_iata = get_valid_value(flight, ['ident_iata', 'null'])
    aircraft = flight.get("aircraft_type", 'null')
    airline = flight.get("operator_icao", 'null')
    airline_name = flight.get("operator", 'null')
    
    # Load airlines database
    import json
    with open('database/airlines.json', 'r', encoding='utf-8') as f:
        airlines_db = json.load(f)
    
    # Get airline name from ICAO if available, otherwise use existing name
    airline_name = airlines_db.get(airline, {}).get('Name', airline_name)
    country = callsigns_dict.get(airline, airlines_db.get(airline, {})).get('Country', 'null')
    callsign = callsigns_dict.get(airline, airlines_db.get(airline, {})).get('Callsign', 'null')
    diverted = flight.get("diverted", 'null')
    diverted = normalize_diverted_value(diverted)

    # Get last update time
    last_update = datetime.now().strftime("%Y-%m-%d %H:%M")

    single_flight_data = {
        'callsign': callsign.capitalize(),
        'flight_name': "".join(flight_name.split()),
        'flight_name_iata': flight_name_iata,
        'registration': registration,
        'aircraft_name': None,
        'aircraft_icao': aircraft.strip() if aircraft != None else 'null',
        'airline': airline,
        'airline_name': airline_name,
        'country': country.capitalize(),
        'origin_icao': origin_icao,
        'origin_name': origin_name,
        'destination_icao': destination_icao,
        'destination_name': destination_name,
        'terminal': terminal,
        'scheduled_time': scheduled_time,
        'last_update': last_update,
        'diverted': diverted
    }

    logger.debug(f"Processed AeroAPI flight data: {single_flight_data}")
    return single_flight_data

async def check_flight(flight, reg_db, interesting_reg_db, model_db, interesting_model_db_copy, config):
    interesting_registration = False
    interesting_model = False
    first_seen = False
    seen_recently = False

    # Convert scheduled_time to string if needed
    if not isinstance(flight['scheduled_time'], str):
        flight['scheduled_time'] = flight['scheduled_time'].strftime("%Y-%m-%d %H:%M")
        logger.debug(f"Converted scheduled_time to string format")

    # Get posting cooldown from config (default 6 months in hours)
    posting_cooldown_hours = config.get('flight', {}).get('posting_cooldown_hours', 6 * 30 * 24)  # 6 months

    # if we have a registration proceed with the evaluation
    # if the registration is in the general reg db then its not new
    #  - update the last_seen field
    # if its not then its new
    #  - cretae a new record in the db
    #  - flag as first seen
    #  - update the times_seen field
    # evaluate the model
    # - if its NOT in the model db then its interesting
    reason = None

    if flight['registration'] not in ['null', None]: # if we have a registration proceed with the evaluation

        if flight['registration'] in interesting_reg_db: #its a interesting plane
            
            interesting_registration = True # set the interesting reason as true for registration
            reason = interesting_reg_db[flight['registration']].get('reason', None)
            logger.info(f"Flight {flight['registration']} is in interesting registrations table: {reason}")

        if flight['registration'] in reg_db: # if the registration is in the general reg db then its not new
            db_reg = reg_db[flight['registration']]
            logger.debug(f"Flight {flight['registration']} has been seen before")
            
            # Check if aircraft was seen recently (within cooldown period)
            # If it was last seen more than 6 months ago, treat it as interesting to post again
            last_seen_db = db_reg.get('last_seen', None)
            if last_seen_db and last_seen_db not in [None, 'null', '']:
                try:
                    from datetime import datetime, timedelta
                    last_seen_dt = datetime.strptime(last_seen_db, "%Y-%m-%d %H:%M")
                    current_dt = datetime.strptime(flight['scheduled_time'], "%Y-%m-%d %H:%M")
                    time_diff = current_dt - last_seen_dt
                    
                    if time_diff.total_seconds() < (posting_cooldown_hours * 3600):
                        seen_recently = True
                        logger.debug(f"Aircraft {flight['registration']} was last seen {time_diff} ago, within cooldown period")
                    else:
                        # Aircraft hasn't been seen in 6+ months, treat as interesting again
                        seen_recently = False
                        logger.info(f"Aircraft {flight['registration']} last seen {time_diff} ago (>{posting_cooldown_hours/24:.0f} days), treating as interesting")
                except Exception as e:
                    logger.warning(f"Error parsing last_seen time for {flight['registration']}: {e}")
            
            if (db_reg.get('reason') not in ['null', None]) or flight['registration'] in interesting_reg_db: # if the reg has a reason field or is in the interesting reg table
                logger.info(f"Flight {flight['registration']} is in interesting registrations table")
                if flight['registration'] in interesting_reg_db:
                    reason = interesting_reg_db[flight['registration']].get('reason', None)
                else:
                    reason = db_reg.get('reason', None)
                interesting_registration = True # set the interesting reason as true for registration
                
            # Update last seen value
            times_seen = db_reg['times_seen']
            payload = {
                'last_seen': flight['scheduled_time'], 
                'times_seen': int(times_seen) + 1
            }
            
            try:
                result = await bm.update_record(config['baserow']['tables']['registrations'], payload, flight)
                if result:
                    logger.debug(f"Updated record for {flight['registration']} in table {config['baserow']['tables']['registrations']}")
                else:
                    logger.warning(f"Failed to update record for {flight['registration']} - no error raised but result was None")
            except Exception as e:
                logger.error(f"Failed to update record for {flight['registration']}: {e}")
                # Log the payload for debugging
                logger.debug(f"Payload for update: {payload}")

        else:
            # New registration so we create the record in the db
            payload = {
                "registration": flight['registration'],
                "first_seen": flight['scheduled_time'],
                "last_seen": flight['scheduled_time'],
                "times_seen": 1,
                "reason": None
            }
            try: # its new, lets add it to the db
                table_name = config['baserow']['tables']['registrations']
                result = await bm.create_record(f'{table_name}', payload)
                if result:
                    logger.success(f"Created new record for {flight['registration']} in table {table_name}")
                    first_seen = True
                else:
                    logger.warning(f"Failed to create record for {flight['registration']} - no error raised but result was None")
            except Exception as e:
                logger.error(f"Failed to create record for {flight['registration']}: {e}")
                # Log the payload for debugging
                logger.debug(f"Payload for creation: {payload}")
    

    # model_db is a dictionary where values are model entries
    # Each model entry contains 'model' and 'name' fields
    # We check if the flight's aircraft matches any model in either:
    # 1. The main model database (model_db)
    # 2. The interesting models database (interesting_model_db_copy)
    # A match is found if the flight's aircraft_icao or aircraft_name matches
    # either the model or name field from any database entry

    # Create sets for faster lookups
    model_set = {model_entry.get('model', '').lower().replace('/', '').replace('-', '') for model_entry in model_db.values()}
    interesting_model_set = {model_entry.get('model', '').lower().replace('/', '').replace('-', '') for model_entry in interesting_model_db_copy.values()}
    model_name_set = {model_entry.get('name', '').lower().replace('/', '').replace('-', '') for model_entry in model_db.values()}
    interesting_model_name_set = {model_entry.get('name', '').lower().replace('/', '').replace('-', '') for model_entry in interesting_model_db_copy.values()}

    # Check if aircraft is interesting based on model or name
    aircraft_icao = flight.get('aircraft_icao', '').lower().replace('/', '').replace('-', '') if flight.get('aircraft_icao') else None
    aircraft_name = flight.get('aircraft_name', '').lower().replace('/', '').replace('-', '') if flight.get('aircraft_name') else None

    interesting_model = (
        aircraft_icao in interesting_model_set if aircraft_icao != None else False or
        aircraft_name in interesting_model_name_set if aircraft_name != None else False or
        aircraft_icao not in model_set if aircraft_icao != None else False or
        aircraft_name not in model_name_set if aircraft_name != None else False
    )



    if interesting_model:
        logger.info(f"Flight {flight['registration'] if flight.get('registration') != 'null' else flight.get('flight_name') if flight.get('flight_name') != 'null' else flight.get('flight_name_iata', 'N/A')} is interesting based on model {aircraft_name} {aircraft_icao}")
    if interesting_registration:
        logger.info(f"Flight {flight['registration'] if flight.get('registration') != 'null' else flight.get('flight_name') if flight.get('flight_name') != 'null' else flight.get('flight_name_iata', 'N/A')} is interesting based on registration")
    if first_seen: 
        logger.info(f"Flight {flight['registration'] if flight.get('registration') != 'null' else flight.get('flight_name') if flight.get('flight_name') != 'null' else flight.get('flight_name_iata', 'N/A')} is first seen")

    return flight, interesting_registration, interesting_model, first_seen, reason, seen_recently

# If flight already exists, merge data
def check_existing(all_flights, processed_data):
    # Lista de claves que se utilizarán para identificar el vuelo
    nameish = ['flight_name_iata', 'flight_name']

    # Itera sobre las claves de identificación
    for name in nameish:
        # Si la clave no está presente en los datos procesados o es 'null', continúa con la siguiente clave
        if processed_data.get(name, None) in [None, 'null']:
            continue
        else:
            # Si la clave es 'flight_name_iata' y el 'flight_name' ya existe en all_flights
            if name == 'flight_name_iata' and processed_data.get('flight_name', None) in all_flights:
                # Itera sobre todos los pares clave-valor en los datos procesados
                for key, value in processed_data.items():
                    # Si la clave en el vuelo existente es 'null' y el valor en los datos procesados no es 'null', actualiza el valor
                    if all_flights[name].get(key) in [None, 'null'] and value not in [None, 'null']:
                        all_flights[name][key] = value
                        logger.debug(f"Updated {key} for {name}")
            else:
                # Si el vuelo no existe, agrega los datos procesados al diccionario usando 'flight_name_iata' como clave
                all_flights[processed_data.get('flight_name_iata')] = processed_data
