import os
from pathlib import Path
from dotenv import load_dotenv
from telegram import Update, Bot
from telegram.ext import Application, ApplicationBuilder, CommandHandler, ContextTypes
from telegram.request import HTTPXRequest

# Load .env file dynamically
def load_env():
    # Get the absolute path of the current script
    script_dir = Path(__file__).resolve().parent
    # Navigate to the config directory and load the .env file
    env_path = script_dir.parent / 'config' / '.env'
    print(f"Loading .env file from: {env_path}")  # Debugging line
    if env_path.exists():
        load_dotenv(env_path)
    else:
        print(f".env file not found at {env_path}")

# Define a command handler for the /start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('Hello! I am your test bot.')

# Main function to start the bot
def main():
    # Load environment variables FIRST
    load_env()

    # Get the bot token from the environment variables or use a hardcoded one
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not bot_token:
        print("TELEGRAM_BOT_TOKEN not found in .env, using hardcoded token for testing.")
        bot_token = "6572961963:AAGTLDcCHAIf6Agbbo9Tskm5VTI8u0C_g_8" # Your hardcoded token

    print(f"Using Bot Token: {bot_token[:15]}...")

    if not bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN not found in .env file or hardcoded.")

    # Build the bot application with custom HTTPX configuration
    application = ApplicationBuilder().token(bot_token).build()

    # Register the /start command handler
    start_handler = CommandHandler('start', start)
    application.add_handler(start_handler)

    # Start the bot
    print("Starting bot polling...")
    application.run_polling()

if __name__ == '__main__':
    main()
