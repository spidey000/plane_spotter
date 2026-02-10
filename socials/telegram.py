from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import telegram.error
from loguru import logger
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

import config.config as cfg
from monitoring.api_usage import record_api_event
from socials.message_builder import MessageContext, render_flight_message


def is_admin(user_id: int) -> bool:
    return str(user_id) == os.getenv("ADMIN_USER_ID")


async def config_set(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.message.from_user.id):
        await update.message.reply_text("Acceso denegado")
        return

    try:
        key = context.args[0]
        value = context.args[1]
        cfg.update_config(key, value)
        await update.message.reply_text(f"Configuracion actualizada: {key} = {value}")
    except Exception as exc:
        await update.message.reply_text(f"Error: {exc}")


async def config_get(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.message.from_user.id):
        await update.message.reply_text("Acceso denegado")
        return

    try:
        key = context.args[0]
        value = cfg.get_config(key)
        await update.message.reply_text(f"{key} = {value}")
    except Exception as exc:
        await update.message.reply_text(f"Error: {exc}")


async def config_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.message.from_user.id):
        await update.message.reply_text("Acceso denegado")
        return

    try:
        config = cfg.load_config()
        await update.message.reply_text(f"Configuracion actual:\n{config}")
    except Exception as exc:
        await update.message.reply_text(f"Error: {exc}")


async def config_reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.message.from_user.id):
        await update.message.reply_text("Acceso denegado")
        return

    try:
        cfg.save_config(cfg.DEFAULT_CONFIG)
        await update.message.reply_text("Configuracion restablecida a valores por defecto")
    except Exception as exc:
        await update.message.reply_text(f"Error: {exc}")


_application = None


def _create_application():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.warning("TELEGRAM_BOT_TOKEN is not configured; Telegram sender is disabled")
        return None

    app = (
        ApplicationBuilder()
        .token(token)
        .read_timeout(30)
        .write_timeout(30)
        .build()
    )
    app.add_handler(CommandHandler("config_set", config_set))
    app.add_handler(CommandHandler("config_get", config_get))
    app.add_handler(CommandHandler("config_list", config_list))
    app.add_handler(CommandHandler("config_reset", config_reset))
    return app


def get_application():
    global _application
    if _application is None:
        _application = _create_application()
    return _application


def generate_flight_message(flight_data: dict[str, Any], interesting: dict[str, bool] | None = None) -> str:
    return render_flight_message(flight_data, interesting=interesting)


def _flight_url(flight_data: dict[str, Any], fallback_url: str | None = None) -> str:
    if fallback_url:
        return fallback_url
    flight_slug = flight_data.get("flight_name_iata") or flight_data.get("flight_name") or "unknown-flight"
    flight_slug = str(flight_slug).replace(" ", "").lower()
    return f"https://www.flightradar24.com/data/flights/{flight_slug}"


async def send_flight_update(
    chat_id: str,
    flight_data: dict[str, Any],
    image_path: str | None = None,
    message_text: str | None = None,
    flight_url: str | None = None,
) -> None:
    application = get_application()
    if application is None:
        return

    message = message_text or generate_flight_message(flight_data)
    url = _flight_url(flight_data, fallback_url=flight_url)
    retries = 3
    flight_name = flight_data.get("flight_name_iata") or flight_data.get("flight_name") or "unknown-flight"

    for attempt in range(retries):
        try:
            started = time.perf_counter()
            if image_path and Path(image_path).exists() and flight_data.get("registration") not in (None, "null"):
                with open(image_path, "rb") as photo_file:
                    await application.bot.send_photo(
                        chat_id=chat_id,
                        photo=photo_file,
                        caption=message,
                        reply_markup={
                            "inline_keyboard": [[{"text": "Flightradar", "url": url}]],
                        },
                    )
                record_api_event(
                    provider="telegram",
                    endpoint="POST /bot/sendPhoto",
                    method="POST",
                    status_code=200,
                    success=True,
                    duration_ms=(time.perf_counter() - started) * 1000.0,
                    estimated_cost_usd=0.0,
                )
            else:
                await application.bot.send_message(
                    chat_id=chat_id,
                    text=message,
                    disable_web_page_preview=True,
                    reply_markup={
                        "inline_keyboard": [[{"text": "Flightradar", "url": url}]],
                    },
                )
                record_api_event(
                    provider="telegram",
                    endpoint="POST /bot/sendMessage",
                    method="POST",
                    status_code=200,
                    success=True,
                    duration_ms=(time.perf_counter() - started) * 1000.0,
                    estimated_cost_usd=0.0,
                )

            logger.success(f"Successfully sent Telegram message for flight {flight_name}")
            return
        except telegram.error.TimedOut:
            if attempt < retries - 1:
                wait_time = 2 ** attempt
                logger.warning(
                    f"Telegram timeout. Retrying in {wait_time} seconds "
                    f"(attempt {attempt + 1}/{retries})"
                )
                await asyncio.sleep(wait_time)
                continue
            raise
        except telegram.error.RetryAfter as exc:
            logger.warning(f"Telegram rate limit hit. Retrying in {exc.retry_after} seconds")
            await asyncio.sleep(exc.retry_after)
            continue
        except Exception as exc:
            record_api_event(
                provider="telegram",
                endpoint="POST /bot/send",
                method="POST",
                status_code=None,
                success=False,
                duration_ms=0.0,
                estimated_cost_usd=0.0,
                error=str(exc),
            )
            logger.error(f"Failed to send Telegram message for flight {flight_name}: {exc}")
            raise


async def schedule_telegram(
    flight_data: dict[str, Any],
    image_path: str | None = None,
    message_text: str | None = None,
    flight_url: str | None = None,
):
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "-1002116996158")
    flight_name = flight_data.get("flight_name_iata") or flight_data.get("flight_name") or "unknown-flight"
    logger.info(f"Scheduling Telegram message for flight {flight_name}")

    async def send_message_task() -> None:
        try:
            scheduled_time = datetime.strptime(str(flight_data["scheduled_time"]), "%Y-%m-%d %H:%M")
            send_time = scheduled_time - timedelta(hours=2)
            delay_seconds = (send_time - datetime.now()).total_seconds()

            if delay_seconds < 0:
                logger.warning(f"Scheduled time for flight {flight_name} is in the past, sending immediately")
                delay_seconds = 0

            if delay_seconds > 0:
                await asyncio.sleep(delay_seconds)

            await send_flight_update(
                chat_id=chat_id,
                flight_data=flight_data,
                image_path=image_path,
                message_text=message_text,
                flight_url=flight_url,
            )
        except asyncio.CancelledError:
            logger.warning(f"Telegram task for flight {flight_name} was cancelled")
        except Exception as exc:
            logger.error(f"Failed to schedule Telegram message for flight {flight_name}: {exc}")

    return asyncio.create_task(send_message_task())


async def send_message(context: MessageContext, image_path: str | None = None) -> None:
    task = await schedule_telegram(
        context.flight_data,
        image_path=image_path,
        message_text=context.text,
        flight_url=context.flight_url,
    )
    await task
