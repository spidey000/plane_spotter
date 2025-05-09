# this loads the fligth data from the apis and stores it in the database
# compare flights by flight_name in both api calls and merge the most information in the database
import json
from pathlib import Path
from datetime import datetime
import database.baserow_manager as bm
from loguru import logger
from log.logger_config import logger

from config import config_manager

config = config_manager.load_config()

def process_flight_data_adb(flight, movement):
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
    country = airlines_db.get(airline, {}).get('Country', 'null')
    callsign = airlines_db.get(airline, {}).get('Callsign', 'null')

    if movement == 'departures':
        destination_icao = flight.get('arrival', {}).get('airport', {}).get('icao', 'null')
        destination_name = flight.get('arrival', {}).get('airport', {}).get('name', 'null')
        origin_icao = "LEMD"
        origin_name = "Madrid"
    else:
        origin_icao = flight.get('departure', {}).get('airport', {}).get('icao', 'null')
        origin_name = flight.get('departure', {}).get('airport', {}).get('name', 'null')
        destination_icao = "LEMD"
        destination_name = "Madrid"

    terminal = flight[movement.removesuffix('s')].get('terminal', 'null')
    diverted = 'null'
    
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
        'callsign': callsign,
        'flight_name': "".join(flight_name.split()),
        'flight_name_iata': flight_name_iata,
        'registration': registration,
        'aircraft_name': aircraft_name.strip(),
        'aircraft_icao': None,
        'airline': airline,
        'airline_name': airline_name,
        'country': country,
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

def process_flight_data_aeroapi(flight):
    try:
        registration = flight["registration"]
    except Exception as e:
        logger.warning(f"Failed to get registration: {e}")
        return None
    
    is_departure = flight.get("origin", {}).get("code_icao") == "LEMD"
    
    if is_departure:
        scheduled_time = get_valid_value(flight, ["actual_off", "estimated_off", "scheduled_off"])
        terminal = flight.get("terminal_origin", 'null')
        origin_icao, origin_name = 'LEMD', 'Madrid'
        destination_icao = flight.get("destination", {}).get("code_icao", 'null')
        destination_name = flight.get("destination", {}).get("name", 'null')
    else:
        scheduled_time = get_valid_value(flight, [ "estimated_on", "scheduled_on", "scheduled_in, estimated_in"])
        terminal = flight.get("terminal_destination", 'null')
        origin_icao = flight.get("origin", {}).get("code_icao", 'null')
        origin_name = flight.get("origin", {}).get("name", 'null')
        destination_icao, destination_name = 'LEMD', 'Madrid'
    
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
    country = airlines_db.get(airline, {}).get('Country', 'null')
    callsign = airlines_db.get(airline, {}).get('Callsign', 'null')
    diverted = flight.get("diverted", 'null')

    # Get last update time
    last_update = datetime.now().strftime("%Y-%m-%d %H:%M")

    single_flight_data = {
        'callsign': callsign,
        'flight_name': "".join(flight_name.split()),
        'flight_name_iata': flight_name_iata,
        'registration': registration,
        'aircraft_name': None,
        'aircraft_icao': aircraft.strip(),
        'airline': airline,
        'airline_name': airline_name,
        'country': country,
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

async def check_flight(flight, reg_db, interesting_reg_db, model_db, interesting_model_db_copy):
    interesting_registration = False
    interesting_model = False
    first_seen = False        

    # Convert scheduled_time to string if needed
    if not isinstance(flight['scheduled_time'], str):
        flight['scheduled_time'] = flight['scheduled_time'].strftime("%Y-%m-%d %H:%M")
        logger.debug(f"Converted scheduled_time to string format")

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
            reason = interesting_reg_db['registration']['reason']
            logger.info(f"Flight {flight['registration']} is in interesting registrations table: {reason}")

        if flight['registration'] in reg_db: # if the registration is in the general reg db then its not new
            db_reg = reg_db[flight['registration']]
            logger.debug(f"Flight {flight['registration']} has been seen before")
            
            if (db_reg['reason'] not in ['null', None]) or flight['registration'] in interesting_reg_db: # if the reg has a reason field or is in the interesting reg table
                logger.info(f"Flight {flight['registration']} is in interesting registrations table")
                reason = db_reg.get('reason', None)
                interesting_registration = True # set the interesting reason as true for registration
                
            # Update last seen value
            times_seen = db_reg['times_seen']
            payload = {
                'last_seen': flight['scheduled_time'], 
                'times_seen': int(times_seen) + 1
            }
            
            try:
                await bm.update_record(config['baserow']['tables']['registrations'], payload, flight)
                logger.debug(f"Updated record for {flight['registration']} in table {config['baserow']['tables']['registrations']}")
            except Exception as e:
                logger.error(f"Failed to update record for {flight['registration']}: {e}")

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
                await bm.create_record(f'{config['baserow']['tables']['registrations']}', payload)
                logger.success(f"Created new record for {flight['registration']} in table {config['baserow']['tables']['registrations']}")
                first_seen = True
            except Exception as e:
                logger.error(f"Failed to create record for {flight['registration']}: {e}")
    

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

    return flight, interesting_registration, interesting_model, first_seen, reason

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