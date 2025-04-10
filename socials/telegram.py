from loguru import logger
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters, CommandHandler
import telegram.error
import asyncio
from datetime import datetime, timedelta
from utils.image_finder import get_first_image_url_jp, get_first_image_url_pp
import os
import config.config as cfg

def is_admin(user_id):
    """Check if user is admin"""
    return str(user_id) == os.getenv('ADMIN_USER_ID')

async def config_set(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /config_set command"""
    if not is_admin(update.message.from_user.id):
        await update.message.reply_text("Acceso denegado")
        return
    
    try:
        key = context.args[0]
        value = context.args[1]
        cfg.update_config(key, value)
        await update.message.reply_text(f"Configuración actualizada: {key} = {value}")
    except Exception as e:
        await update.message.reply_text(f"Error: {str(e)}")

async def config_get(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /config_get command"""
    if not is_admin(update.message.from_user.id):
        await update.message.reply_text("Acceso denegado")
        return
    
    try:
        key = context.args[0]
        value = cfg.get_config(key)
        await update.message.reply_text(f"{key} = {value}")
    except Exception as e:
        await update.message.reply_text(f"Error: {str(e)}")

async def config_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /config_list command"""
    if not is_admin(update.message.from_user.id):
        await update.message.reply_text("Acceso denegado")
        return
    
    try:
        config = cfg.load_config()
        await update.message.reply_text(f"Configuración actual:\n{config}")
    except Exception as e:
        await update.message.reply_text(f"Error: {str(e)}")

async def config_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /config_reset command"""
    if not is_admin(update.message.from_user.id):
        await update.message.reply_text("Acceso denegado")
        return
    
    try:
        cfg.save_config(cfg.DEFAULT_CONFIG)
        await update.message.reply_text("Configuración restablecida a valores por defecto")
    except Exception as e:
        await update.message.reply_text(f"Error: {str(e)}")

# Initialize Telegram application with longer timeout
application = ApplicationBuilder().token('6572961963:AAE29B4HnmR17HTllBAmKK02ecIwav6WQmk')\
    .read_timeout(30)\
    .write_timeout(30)\
    .build()

# Register configuration commands
application.add_handler(CommandHandler("config_set", config_set))
application.add_handler(CommandHandler("config_get", config_get))
application.add_handler(CommandHandler("config_list", config_list))
application.add_handler(CommandHandler("config_reset", config_reset))

def generate_flight_message(flight_data):
    """Generate a formatted message from flight data"""
    message = f"✈️ Flight Information:\n\n"
    message += f"Flight: {flight_data['flight_name_iata']}{"/" + flight_data['flight_name'] if flight_data['flight_name'] not in [None, 'null'] else ''}\n"
    message += f"Registration: {flight_data['registration'] if flight_data['registration'] not in [None, 'null'] else 'Unkown'}\n"
    message += f"Aircraft: {flight_data['aircraft_name'] if flight_data['aircraft_name'] else flight_data['aircraft_icao']}\n"
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

async def send_flight_update(chat_id, flight_data, image_path=None):
    """Send flight update to specified chat with retry logic"""
    message = generate_flight_message(flight_data)
    retries = 3
    flight_name = flight_data['flight_name_iata'] if flight_data['flight_name_iata'] not in [None, 'null'] else flight_data['flight_name']
    for attempt in range(retries):
        try:
            # image path is a local image path
            if image_path and flight_data['registration']:
                # Send message with photo
                with open(image_path, 'rb') as photo_file:
                    await application.bot.send_photo(
                        chat_id=chat_id,
                        photo=photo_file,
                        caption=message,
                        reply_markup={
                            'inline_keyboard': [[{
                                'text': 'Flightradar',
                                'url': f"https://www.flightradar24.com/data/flights/{flight_name}"
                            }]]
                        }
                    )
            else:
                # Send message without photo if no image found
                logger.warning(f"No valid image file found at {image_path}, sending text only")
                await application.bot.send_message(
                    chat_id=chat_id,
                    text=message,
                    disable_web_page_preview=True,
                    reply_markup={
                        'inline_keyboard': [[{
                            'text': 'Flightradar',
                            'url': f"https://www.flightradar24.com/data/flights/{flight_name}"
                        }]]
                    }
                )
            logger.success(f"Successfully sent Telegram message for flight {flight_name}")
            return
        except telegram.error.TimedOut:
            if attempt < retries - 1:  # Don't wait on the last attempt
                wait_time = 2 ** attempt  # Exponential backoff
                logger.warning(f"Timeout occurred. Retrying in {wait_time} seconds... (Attempt {attempt + 1}/{retries})")
                await asyncio.sleep(wait_time)
                continue
            raise  # Re-raise the exception if all retries fail
        except telegram.error.RetryAfter as e:
            logger.warning(f"Rate limit hit. Retrying in {e.retry_after} seconds...")
            await asyncio.sleep(e.retry_after)
            continue
        except Exception as e:
            logger.error(f"Failed to send Telegram message for flight {flight_data['flight_name']}: {e}")
            raise

async def schedule_telegram(flight_data, image_path=None):
    """Send a Telegram message with flight data to the channel"""
    chat_id = '-1002116996158'  # Telegram channel ID
    flight_name = flight_data['flight_name_iata'] if flight_data['flight_name_iata'] not in [None, 'null'] else flight_data['flight_name']
    logger.info(f"Scheduling Telegram message for flight {flight_name}")
    
    async def send_message_task():
        try:
            # Parse scheduled time and calculate send time (2 hours before)
            scheduled_time = datetime.strptime(flight_data['scheduled_time'], "%Y-%m-%d %H:%M")
            send_time = scheduled_time - timedelta(hours=2)
            
            # Calculate delay in seconds
            now = datetime.now()
            delay = (send_time - now).total_seconds()
            
            # If the time has already passed, send immediately
            if delay < 0:
                logger.warning(f"Scheduled time for flight {flight_name} is in the past, sending immediately")
                delay = 0
            else:
                logger.debug(f"Message for flight {flight_name} will be sent in {delay} seconds")
                try:
                    await asyncio.sleep(delay)
                except asyncio.CancelledError:
                    logger.warning(f"Task for flight {flight_name} was cancelled, sending immediately")
            
            
            await send_flight_update(chat_id, flight_data, image_path)
        except Exception as e:
            logger.error(f"Failed to send Telegram message for flight {flight_name}: {e}")
            logger.exception(f"Exception details:{e}")
    
    # Create a background task that won't block the main execution
    task = asyncio.create_task(send_message_task())
    return task  # Return the task so it can be awaited if needed
