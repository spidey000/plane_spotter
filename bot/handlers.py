import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, CallbackContext, MessageHandler, Filters
from config.config_manager import load_config, modify_config
import os

# Cargar la configuración inicial
config = load_config()

def start(update: Update, context: CallbackContext) -> None:
    """Maneja el comando /start y muestra los botones para editar la configuración."""
    keyboard = []
    build_keyboard(config, keyboard)
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text('Selecciona un parámetro para editar:', reply_markup=reply_markup)

def build_keyboard(data, keyboard, prefix=""):
    """Construye el teclado con los parámetros de configuración."""
    for key, value in data.items():
        if isinstance(value, dict):
            build_keyboard(value, keyboard, f"{prefix}{key}.")
        else:
            keyboard.append([InlineKeyboardButton(f"{prefix}{key}: {value}", callback_data=f"edit_{prefix}{key}")])

def button_callback(update: Update, context: CallbackContext) -> None:
    """Maneja la selección de un botón y solicita el nuevo valor."""
    query = update.callback_query
    query.answer()
    
    # Extraer la ruta completa de la clave del callback_data
    key_path = query.data.split('_')[1]
    
    # Guardar la ruta de la clave en el contexto para usarlo en la siguiente interacción
    context.user_data['edit_key_path'] = key_path
    
    # Solicitar el nuevo valor
    query.edit_message_text(f"Introduce el nuevo valor para {key_path}:")

def handle_message(update: Update, context: CallbackContext) -> None:
    """Maneja el nuevo valor introducido por el usuario."""
    new_value = update.message.text
    key_path = context.user_data.get('edit_key_path')
    
    if key_path:
        # Obtener el valor actual para verificar el tipo de dato
        current_value = get_nested_value(config, key_path.split('.'))
        
        if current_value is not None:
            try:
                # Intentar convertir el valor al tipo correcto
                if isinstance(current_value, bool):
                    new_value = new_value.lower() == 'true'
                elif isinstance(current_value, int):
                    new_value = int(new_value)
                elif isinstance(current_value, float):
                    new_value = float(new_value)
                # No se necesita conversión para cadenas
                
                # Modificar la configuración
                if modify_config(key_path, new_value):
                    update.message.reply_text(f"Valor actualizado: {key_path} = {new_value}")
                else:
                    update.message.reply_text("Error al actualizar el valor.")
            except ValueError:
                update.message.reply_text("El valor introducido no es válido para este parámetro.")
        else:
            update.message.reply_text("Error: No se pudo encontrar el parámetro a editar.")
    else:
        update.message.reply_text("Error: No se pudo identificar el parámetro a editar.")

def get_nested_value(data, keys):
    """Obtiene el valor anidado en el diccionario."""
    for key in keys:
        if key in data:
            data = data[key]
        else:
            return None
    return data

def main() -> None:
    """Inicia el bot de Telegram."""
    # Obtener el token de Telegram desde las variables de entorno
    telegram_token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not telegram_token:
        raise ValueError("TELEGRAM_BOT_TOKEN no está configurado en las variables de entorno")
    updater = Updater(telegram_token)
    
    dispatcher = updater.dispatcher
    
    # Manejadores de comandos y mensajes
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CallbackQueryHandler(button_callback))
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))
    
    # Iniciar el bot
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()