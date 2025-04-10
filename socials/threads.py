# uses threads api https://developers.facebook.com/docs/threads

def generate_flight_message(flight_data):
    """Generate a formatted message from flight data"""
    message = f"✈️ Flight Information:\n\n"
    message += f"Flight: {flight_data['flight_name']}\n"
    message += f"Registration: {flight_data['registration']}\n"
    message += f"Aircraft: {flight_data['aircraft']}\n"
    message += f"Airline: {flight_data['airline_name']} ({flight_data['airline']})\n"
    message += f"Route: {flight_data['origin_name']} ({flight_data['origin_icao']}) → "
    message += f"{flight_data['destination_name']} ({flight_data['destination_icao']})\n"
    message += f"Scheduled Time: {flight_data['scheduled_time']}\n"
    message += f"Terminal: {flight_data['terminal']}\n"
    if flight_data['diverted'] not in [None, False, 'null']:
        message += "\n⚠️ This flight has been diverted"
    message += "\n\n"
    message += "Check all our socials in linktr.ee/ctrl_plataforma"
    return message

