import json
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from log.logger_config import logger


# Use the modern ApplicationBuilder and related components
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters # Import filters
)
from loguru import logger # Using loguru since config_manager likely uses it

# Add project root directory to Python path
# Ensure this path logic works correctly relative to where you run the script
try:
    project_root = Path(__file__).resolve().parent.parent
    sys.path.append(str(project_root))
    logger.info(f"Added project root to sys.path: {project_root}")
    # Import config manager after adding to path
    from config.config_manager import load_config, modify_config
except ImportError as e:
    logger.error(f"Error importing config_manager. Check PYTHONPATH and file location. Error: {e}")
    sys.exit(1)
except FileNotFoundError:
    logger.error("Could not determine project root directory. Ensure script is in the expected location.")
    sys.exit(1)


# Load initial configuration
try:
    config = load_config()
    if not config:
        logger.error("Failed to load configuration. Exiting.")
        sys.exit(1)
except Exception as e:
    logger.error(f"Exception during initial config load: {e}")
    sys.exit(1)

# --- Command Handlers ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command and show configuration edit buttons."""
    # Reload config each time start is called to show current values
    current_config = load_config()
    if not current_config:
        await update.message.reply_text("Error loading configuration.")
        return

    keyboard = []
    build_keyboard(current_config, keyboard) # Pass the freshly loaded config

    if not keyboard:
        await update.message.reply_text("Configuration is empty or could not be parsed.")
        return

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text('Select a parameter to edit:', reply_markup=reply_markup)

# --- Keyboard Builder ---

def build_keyboard(data, keyboard, prefix=""):
    """Build keyboard with configuration parameters (recursive)."""
    for key, value in data.items():
        current_prefix = f"{prefix}{key}"
        if isinstance(value, dict):
            # Option 1: Add a button for the dictionary itself (less user-friendly for editing)
            # keyboard.append([InlineKeyboardButton(f"Section: {current_prefix}", callback_data="noop")]) # noop = no operation
            # Option 2: Recursively add keys within the dictionary (better for editing leaves)
            build_keyboard(value, keyboard, f"{current_prefix}.")
        else:
            # Format value nicely for the button
            display_value = str(value)
            if len(display_value) > 20: # Shorten long values for display
                display_value = display_value[:17] + "..."
            button_text = f"{current_prefix}: {display_value}"
            callback_data = f"edit_{current_prefix}"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])

# --- Callback Query Handler ---

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle button selection and request new value."""
    query = update.callback_query
    await query.answer() # Acknowledge callback

    callback_data = query.data
    if callback_data == "noop": # Handle dummy buttons if you added them
        return
    elif callback_data.startswith("edit_"):
        # Extract full key path from callback_data
        key_path = callback_data[len("edit_"):] # Remove "edit_" prefix

        # Save key path in context for next interaction
        context.user_data['edit_key_path'] = key_path

        # Request new value
        try:
            await query.edit_message_text(f"Enter new value for `{key_path}`:", parse_mode='MarkdownV2')
        except Exception as e:
            logger.error(f"Error editing message: {e}")
            # Fallback if editing fails (e.g., message too old)
            if query.message:
                await query.message.reply_text(f"Enter new value for {key_path}:")
            else:
                 logger.warning("Could not send reply for entering new value - query.message is None")

# --- Message Handler ---

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle new value entered by user."""
    key_path = context.user_data.get('edit_key_path')

    if not key_path:
        # User sent a message, but we weren't expecting an edit value
        # Optionally, provide guidance or ignore.
        # await update.message.reply_text("Use /start to manage configuration.")
        logger.info("Received unexpected message, ignoring.")
        return

    new_value_str = update.message.text
    logger.info(f"Attempting to update '{key_path}' with value '{new_value_str}'")

    # We need the *current* config to check the type
    current_config = load_config()
    if not current_config:
        await update.message.reply_text("Error loading configuration. Cannot validate or update.")
        del context.user_data['edit_key_path'] # Clean up state
        return

    current_value = get_nested_value(current_config, key_path.split('.'))

    if current_value is None:
        # This shouldn't happen if the button was generated correctly, but check anyway
        await update.message.reply_text(f"Error: Could not find parameter '{key_path}' in current configuration.")
        del context.user_data['edit_key_path'] # Clean up state
        return

    try:
        # Try to convert value to the *original* type
        original_type = type(current_value)
        if original_type == bool:
            if new_value_str.strip().lower() == 'true':
                new_value = True
            elif new_value_str.strip().lower() == 'false':
                new_value = False
            else:
                raise ValueError("Boolean value must be 'true' or 'false'")
        elif original_type == int:
            new_value = int(new_value_str)
        elif original_type == float:
            new_value = float(new_value_str)
        elif original_type == str:
            new_value = new_value_str # No conversion needed for strings
        else:
            # Handle other potential types like lists or if None was somehow the original type
            # For simplicity, try direct eval or JSON loading for complex types,
            # but this can be risky. Sticking to basic types is safer.
            # Let's assume we only handle bool, int, float, str for now.
            await update.message.reply_text(f"Error: Unsupported data type ({original_type.__name__}) for parameter '{key_path}'. Only Bool, Int, Float, Str supported.")
            del context.user_data['edit_key_path'] # Clean up state
            return

        # Modify configuration using the imported function
        if modify_config(key_path, new_value):
            logger.info(f"Successfully updated '{key_path}' to '{new_value}'")
            await update.message.reply_text(f"✅ Value updated: `{key_path}` = `{new_value}`\nUse /start to see updated menu.", parse_mode='MarkdownV2')
        else:
            logger.error(f"modify_config function failed for '{key_path}' = '{new_value}'")
            await update.message.reply_text("❌ Error updating value in configuration file.")

    except ValueError as e:
        logger.warning(f"Value conversion error for '{key_path}': {e}")
        await update.message.reply_text(f"❌ Invalid value format. Expected type: {original_type.__name__}. Error: {e}")
    except Exception as e:
        logger.error(f"Unexpected error during value update for '{key_path}': {e}")
        await update.message.reply_text(f"❌ An unexpected error occurred: {e}")
    finally:
        # !!! IMPORTANT: Clean up the state variable regardless of success or failure !!!
        if 'edit_key_path' in context.user_data:
            del context.user_data['edit_key_path']


# --- Helper Function ---

def get_nested_value(data, keys):
    """Get nested value in dictionary using a list of keys."""
    for key in keys:
        if isinstance(data, dict) and key in data:
            data = data[key]
        else:
            return None # Key not found or structure mismatch
    return data

# --- Main Function ---

def main() -> None:
    """Start Telegram bot."""
    logger.info("Starting bot setup...")

    # Define env_path relative to this script's location
    env_path = project_root / 'config' / '.env' # Use the determined project_root
    if env_path.exists():
        load_dotenv(env_path)
        logger.info(f"Loaded environment variables from: {env_path}")
    else:
        logger.warning(f".env file not found at: {env_path}. Relying on system environment variables.")

    # Get Telegram token from environment variables
    telegram_token = os.getenv('TELEGRAM_BOT_TOKEN')
    print(f"Using Telegram Token: {telegram_token}...")
    if not telegram_token:
        logger.error("TELEGRAM_BOT_TOKEN not configured in environment variables or .env file.")
        raise ValueError("TELEGRAM_BOT_TOKEN not configured")

    # Use ApplicationBuilder for v20+
    application = ApplicationBuilder().token(telegram_token).build()
    logger.info("Telegram Application built.")

    # Add command and message handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_callback))
    # !!! Add the MessageHandler for text input, excluding commands !!!
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Handlers added.")
    logger.info("Bot starting polling...")
    # Start the bot using run_polling
    application.run_polling()
    # No idle() needed with run_polling, it blocks until stopped

if __name__ == '__main__':
    # Basic logger setup if not already configured elsewhere
    logger.add(sys.stderr, level="INFO")
    logger.info("Running __main__ block.")
    main()