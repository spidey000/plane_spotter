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
from socials import message_policy as mp
from socials.message_builder import MessageContext, build_message_context, render_flight_message


def is_admin(user_id: int) -> bool:
    return str(user_id) == os.getenv("ADMIN_USER_ID")


def _build_help_text(admin_user: bool) -> str:
    lines = [
        "Plane Spotter Bot - HELP",
        "",
        "Comandos generales:",
        "- /help -> muestra esta ayuda",
        "- /help_tech -> ayuda tecnica detallada",
    ]

    if not admin_user:
        lines.extend(
            [
                "",
                "Comandos de configuracion disponibles solo para ADMIN.",
                "Si necesitas cambios, contacta al administrador del bot.",
            ]
        )
        return "\n".join(lines)

    lines.extend(
        [
            "",
            "Comandos de configuracion (ADMIN):",
            "- /config_get <key>",
            "- /config_set <key> <value>",
            "- /config_list",
            "- /config_reset",
            "",
            "Comandos de perfiles de mensaje (ADMIN):",
            "- /profile_list",
            "- /profile_get <platform>",
            "- /profile_set <platform> <short|medium|long>",
            "- /profile_preview <platform> [image]",
            "",
            "Plataformas validas:",
            "- telegram, bluesky, twitter, threads, instagram, linkedin",
            "",
            "Ejemplos:",
            "- /profile_set twitter short",
            "- /profile_set telegram long",
            "- /profile_get telegram",
            "- /profile_preview telegram image",
            "- /config_set message_policy.defaults.overflow_action block",
        ]
    )
    return "\n".join(lines)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    admin_user = bool(user and is_admin(user.id))
    message = update.effective_message
    if message is None:
        return
    await message.reply_text(_build_help_text(admin_user))


def _build_help_tech_text(admin_user: bool) -> str:
    if not admin_user:
        return (
            "Ayuda tecnica disponible solo para ADMIN.\n"
            "Usa /help para ayuda general."
        )

    lines = [
        "Plane Spotter Bot - HELP TECH",
        "",
        "1) Comandos de configuracion base:",
        "- /config_get <key>",
        "- /config_set <key> <value>",
        "- /config_list",
        "- /config_reset",
        "",
        "2) Comandos de perfiles por red social:",
        "- /profile_list",
        "- /profile_get <platform>",
        "- /profile_set <platform> <short|medium|long>",
        "- /profile_preview <platform> [image]",
        "",
        "3) Plataformas soportadas:",
        "- telegram, bluesky, twitter, threads, instagram, linkedin",
        "",
        "4) Flujos recomendados:",
        "- Ver estado actual: /profile_list",
        "- Ajustar una red: /profile_set twitter short",
        "- Validar limites: /profile_get twitter",
        "- Probar resultado: /profile_preview twitter",
        "- Preview caption Telegram: /profile_preview telegram image",
        "",
        "5) Keys utiles para /config_set:",
        "- message_policy.defaults.overflow_action block",
        "- message_policy.platform_limits.twitter 280",
        "- message_policy.platform_limits.telegram_caption 1024",
        "- message_policy.platforms.telegram.preferred_profile long",
        "",
        "6) Notas tecnicas:",
        "- overflow_action=block: si no cabe ni short, se bloquea esa red.",
        "- fallback_order se define en config.yaml (lista), no se recomienda editar por /config_set.",
        "- Telegram usa limite distinto para texto normal y caption con imagen.",
        "- Todos los cambios son on-the-go y persisten en config/config.yaml.",
    ]
    return "\n".join(lines)


async def help_tech_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    admin_user = bool(user and is_admin(user.id))
    message = update.effective_message
    if message is None:
        return
    await message.reply_text(_build_help_tech_text(admin_user))


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


async def profile_set(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.message.from_user.id):
        await update.message.reply_text("Acceso denegado")
        return

    if len(context.args) < 2:
        await update.message.reply_text("Uso: /profile_set <platform> <short|medium|long>")
        return

    try:
        platform = mp.validate_platform(context.args[0])
        profile = mp.validate_profile(context.args[1])
        cfg.update_config(f"message_policy.platforms.{platform}.preferred_profile", profile)
        await update.message.reply_text(
            f"Perfil actualizado: {platform} -> {profile}"
        )
    except Exception as exc:
        await update.message.reply_text(f"Error: {exc}")


async def profile_get(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.message.from_user.id):
        await update.message.reply_text("Acceso denegado")
        return

    if len(context.args) < 1:
        await update.message.reply_text("Uso: /profile_get <platform>")
        return

    try:
        platform = mp.validate_platform(context.args[0])
        policy = mp.load_message_policy()
        preferred = mp.get_platform_profile_map(policy).get(platform)
        limits = policy.get("platform_limits", {})
        if platform == "telegram":
            limit_info = (
                f"telegram_text={limits.get('telegram_text')}, "
                f"telegram_caption={limits.get('telegram_caption')}"
            )
        else:
            limit_info = f"limit={limits.get(platform)}"
        await update.message.reply_text(
            f"{platform}: profile={preferred}, {limit_info}"
        )
    except Exception as exc:
        await update.message.reply_text(f"Error: {exc}")


async def profile_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.message.from_user.id):
        await update.message.reply_text("Acceso denegado")
        return

    try:
        profile_map = mp.get_platform_profile_map()
        lines = ["Perfiles por plataforma:"]
        for platform in mp.SUPPORTED_PLATFORMS:
            lines.append(f"- {platform}: {profile_map.get(platform)}")
        await update.message.reply_text("\n".join(lines))
    except Exception as exc:
        await update.message.reply_text(f"Error: {exc}")


async def profile_preview(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.message.from_user.id):
        await update.message.reply_text("Acceso denegado")
        return

    if len(context.args) < 1:
        await update.message.reply_text("Uso: /profile_preview <platform> [image]")
        return

    try:
        platform = mp.validate_platform(context.args[0])
        has_image = len(context.args) > 1 and context.args[1].strip().lower() in {
            "image",
            "caption",
            "true",
            "1",
            "yes",
        }

        sample_flight = {
            "flight_name": "PREVIEW9001",
            "flight_name_iata": "PV9001",
            "registration": "EC-PVW",
            "aircraft_name": "Airbus A320",
            "aircraft_icao": "A320",
            "airline": "IBE",
            "airline_name": "Iberia",
            "origin_icao": "LEBL",
            "origin_name": "Barcelona",
            "destination_icao": "LEMD",
            "destination_name": "Madrid",
            "terminal": "T4",
            "scheduled_time": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "last_update": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "diverted": False,
        }
        context_preview = build_message_context(sample_flight, interesting={"FIRST_SEEN": True})
        decision = mp.resolve_message_for_platform(
            platform,
            context_preview,
            has_image=platform == "telegram" and has_image,
        )

        preview_text = decision.text or "<blocked>"
        if len(preview_text) > 900:
            preview_text = preview_text[:900] + "..."

        lines = [
            f"platform={platform}",
            f"preferred={decision.preferred_profile}",
            f"selected={decision.selected_profile}",
            f"blocked={decision.blocked}",
            f"limit={decision.limit}",
            f"lengths={decision.lengths_by_profile}",
            "",
            "Preview:",
            preview_text,
        ]
        await update.message.reply_text("\n".join(lines))
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
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("start", help_command))
    app.add_handler(CommandHandler("help_tech", help_tech_command))
    app.add_handler(CommandHandler("help_tecnico", help_tech_command))
    app.add_handler(CommandHandler("config_set", config_set))
    app.add_handler(CommandHandler("config_get", config_get))
    app.add_handler(CommandHandler("config_list", config_list))
    app.add_handler(CommandHandler("config_reset", config_reset))
    app.add_handler(CommandHandler("profile_set", profile_set))
    app.add_handler(CommandHandler("profile_get", profile_get))
    app.add_handler(CommandHandler("profile_list", profile_list))
    app.add_handler(CommandHandler("profile_preview", profile_preview))
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
