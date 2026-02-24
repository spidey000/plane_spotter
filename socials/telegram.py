from __future__ import annotations

import asyncio
import io
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

import telegram.error
from loguru import logger
from telegram import MessageEntity, Update
from telegram.constants import MessageEntityType
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

import config.config as cfg
from database import get_database_provider
from monitoring.api_usage import record_api_event
from socials import message_policy as mp
from socials.message_builder import MessageContext, build_message_context, render_flight_message


def is_admin(user_id: int) -> bool:
    return str(user_id) == os.getenv("ADMIN_USER_ID")


SUPPORTED_SOCIAL_TOGGLES = (
    "telegram",
    "bluesky",
    "twitter",
    "threads",
    "instagram",
    "linkedin",
)

CONFIG_LIST_CHUNK_SIZE = 3500
CONFIG_LIST_MAX_TEXT_CHUNKS = 5
CONFIG_LIST_DEFAULT_FILENAME = "config.yaml"


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
            "- /toggle <on|off> <platform>",
            "- /config_get <key>",
            "- /config_set <key> <value>",
            "- /config_list",
            "- /config_reset",
            "- /interesting_reg_add (REG,razon)",
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
            "Toggle rapido de redes:",
            "- /toggle off twitter",
            "- /toggle on threads",
            "",
            "Ejemplos:",
            "- /profile_set twitter short",
            "- /profile_set telegram long",
            "- /profile_get telegram",
            "- /profile_preview telegram image",
            "- /toggle off twitter",
            "- /config_set message_policy.defaults.overflow_action block",
            "- /interesting_reg_add (EC-MYT,Razon especial)",
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
        "- /toggle <on|off> <platform>",
        "- /config_get <key>",
        "- /config_set <key> <value>",
        "- /config_list",
        "- /config_reset",
        "- /interesting_reg_add (REG,razon)",
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
        "- Activar/desactivar red: /toggle off twitter",
        "- Ajustar una red: /profile_set twitter short",
        "- Validar limites: /profile_get twitter",
        "- Probar resultado: /profile_preview twitter",
        "- Preview caption Telegram: /profile_preview telegram image",
        "- Agregar registro interesante: /interesting_reg_add (EC-LMD, Primera visita)",
        "",
        "5) Keys utiles para /config_set:",
        "- message_policy.defaults.overflow_action block",
        "- message_policy.platform_limits.twitter 280",
        "- message_policy.platform_limits.telegram_caption 1024",
        "- message_policy.platforms.telegram.preferred_profile long",
        "- platform_settings.telegram.notifications_enabled false",
        "- platform_settings.telegram.registration_link_enabled false",
        "- platform_settings.bluesky.registration_link_enabled true",
        "",
        "6) Notas tecnicas:",
        "- overflow_action=block: si no cabe ni short, se bloquea esa red.",
        "- fallback_order se define en config.yaml (lista), no se recomienda editar por /config_set.",
        "- Telegram usa limite distinto para texto normal y caption con imagen.",
        "- Todos los cambios se guardan en Supabase (o config/config.yaml si Supabase esta deshabilitado).",
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


def _chunk_text(text: str, limit: int | None = None) -> list[str]:
    if limit is None:
        limit = CONFIG_LIST_CHUNK_SIZE
    if limit <= 0:
        raise ValueError("Chunk size must be positive")
    if not text:
        return []

    chunks: list[str] = []
    start = 0
    length = len(text)
    while start < length:
        end = min(start + limit, length)
        split_point = end
        if end < length:
            newline_index = text.rfind("\n", start, end)
            if newline_index > start:
                split_point = newline_index

        if split_point == start:
            split_point = end

        chunk = text[start:split_point]
        if chunk:
            chunks.append(chunk.rstrip())
        start = split_point
        while start < length and text[start] == "\n":
            start += 1

    return [chunk for chunk in chunks if chunk]


def _extract_command_payload(text: str | None) -> str:
    if not text:
        return ""

    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        return ""
    return parts[1].strip()


def _parse_registration_reason_pairs(payload: str) -> list[tuple[str, str]]:
    if not payload:
        return []

    pairs: list[tuple[str, str]] = []
    idx = 0
    length = len(payload)

    while idx < length:
        while idx < length and payload[idx].isspace():
            idx += 1
        if idx < length and payload[idx] in {",", ";"}:
            idx += 1
            continue
        if idx >= length:
            break

        if payload[idx] != "(":
            raise ValueError("Cada par debe iniciarse con '('")

        idx += 1
        closing = payload.find(")", idx)
        if closing == -1:
            raise ValueError("Falta ')' de cierre en la lista de registros")

        inside = payload[idx:closing]
        idx = closing + 1

        if "," not in inside:
            raise ValueError("Cada par debe tener una coma entre registro y razon")

        registration_part, reason_part = inside.split(",", 1)
        registration = registration_part.strip().upper()
        reason = reason_part.strip()

        if not registration or not reason:
            raise ValueError("Registro y razon no pueden estar vacios")

        pairs.append((registration, reason))

    return pairs


def _select_config_section(config: Any, key_path: str | None) -> Any:
    if not key_path:
        return config

    current: Any = config
    for segment in key_path.split('.'):
        if isinstance(current, dict):
            if segment not in current:
                raise KeyError(segment)
            current = current[segment]
        elif isinstance(current, list):
            try:
                index = int(segment)
            except ValueError as exc:
                raise KeyError(segment) from exc
            if index < 0 or index >= len(current):
                raise IndexError(segment)
            current = current[index]
        else:
            raise KeyError(segment)

    return current


def _serialize_config_section(section: Any) -> str:
    return yaml.safe_dump(section, sort_keys=False, allow_unicode=False)


def _format_config_header(key_path: str | None) -> str:
    return f"Configuracion actual ({key_path})" if key_path else "Configuracion actual"


def _build_config_filename(key_path: str | None) -> str:
    if not key_path:
        return CONFIG_LIST_DEFAULT_FILENAME
    sanitized = key_path.replace('.', '_').replace('/', '_').strip('_')
    return f"{sanitized or 'config'}.yaml"


def _should_send_document(chunks: list[str]) -> bool:
    return len(chunks) > CONFIG_LIST_MAX_TEXT_CHUNKS


def _truncate_caption(text: str, limit: int = 1024) -> str:
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


async def _reply_config_payload(message, serialized: str, key_path: str | None) -> None:
    header = _format_config_header(key_path)
    formatted = f"{header}:\n{serialized}".strip()
    chunks = _chunk_text(formatted)
    if not chunks:
        chunks = [header]

    if not _should_send_document(chunks):
        for chunk in chunks:
            await message.reply_text(chunk)
        return

    buffer = io.BytesIO(serialized.encode('utf-8'))
    buffer.name = _build_config_filename(key_path)
    buffer.seek(0)
    await message.reply_document(
        buffer,
        filename=buffer.name,
        caption=_truncate_caption(header),
    )


async def config_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.message.from_user.id):
        await update.message.reply_text("Acceso denegado")
        return

    args = getattr(context, "args", None) or []
    key_path = args[0].strip() if args else None
    if key_path == "":
        key_path = None

    try:
        config = cfg.load_config()
        section = _select_config_section(config, key_path)
        serialized = _serialize_config_section(section)
    except (IndexError, KeyError, ValueError):
        await update.message.reply_text(f"Clave invalida: {key_path}")
        return
    except Exception as exc:
        await update.message.reply_text(f"Error: {exc}")
        return

    await _reply_config_payload(update.message, serialized, key_path)


async def config_reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.message.from_user.id):
        await update.message.reply_text("Acceso denegado")
        return

    try:
        cfg.reset_config_to_defaults()
        await update.message.reply_text("Configuracion restablecida a valores por defecto")
    except Exception as exc:
        await update.message.reply_text(f"Error: {exc}")


async def interesting_reg_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    user = update.effective_user

    if message is None or user is None or not is_admin(user.id):
        if message is not None:
            await message.reply_text("Acceso denegado")
        return

    payload = _extract_command_payload(message.text)
    if not payload:
        await message.reply_text("Uso: /interesting_reg_add (REG, razon) [(REG2, razon2)...]")
        return

    try:
        pairs = _parse_registration_reason_pairs(payload)
    except ValueError as exc:
        await message.reply_text(f"Formato invalido: {exc}")
        return

    if not pairs:
        await message.reply_text("No se encontraron pares (REG, razon)")
        return

    airport_icao = (
        cfg.get_config("api.airport_icao")
        or cfg.get_config("database.airport_icao")
        or "LEMD"
    )
    airport_icao = str(airport_icao or "").strip().upper() or "LEMD"

    try:
        provider = get_database_provider()
    except Exception as exc:
        await message.reply_text(f"No se pudo inicializar el proveedor de BD: {exc}")
        return

    success_lines: list[str] = []
    error_lines: list[str] = []

    for registration, reason in pairs:
        try:
            row = await provider.upsert_interesting_registration(
                airport_icao=airport_icao,
                registration=registration,
                reason=reason,
            )
            saved_registration = registration
            if isinstance(row, dict):
                saved_registration = str(row.get("registration") or registration)
            success_lines.append(f"- {saved_registration.upper()}: {reason}")
        except Exception as exc:
            error_lines.append(f"- {registration}: {exc}")

    response_lines: list[str] = []
    if success_lines:
        response_lines.append("Registros agregados/actualizados:")
        response_lines.extend(success_lines)

    if error_lines:
        if response_lines:
            response_lines.append("")
        response_lines.append("Errores:")
        response_lines.extend(error_lines)

    await message.reply_text("\n".join(response_lines))


def _parse_toggle_args(args: list[str]) -> tuple[bool, str]:
    if len(args) < 2:
        raise ValueError("Uso: /toggle <on|off> <platform>")

    action = str(args[0]).strip().lower()
    platform = str(args[1]).strip().lower()

    if action not in {"on", "off"}:
        raise ValueError("Accion invalida. Usa on u off")

    if platform not in SUPPORTED_SOCIAL_TOGGLES:
        valid_platforms = ", ".join(SUPPORTED_SOCIAL_TOGGLES)
        raise ValueError(f"Plataforma invalida: {platform}. Validas: {valid_platforms}")

    return action == "on", platform


async def toggle_social(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.message.from_user.id):
        await update.message.reply_text("Acceso denegado")
        return

    try:
        enabled, platform = _parse_toggle_args(context.args)
        cfg.update_config(f"social_networks.{platform}", enabled)
        state = "activada" if enabled else "desactivada"
        await update.message.reply_text(f"{platform} {state}")
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
_listener_task: asyncio.Task | None = None
_listener_lock: asyncio.Lock | None = None
_COMMAND_LISTENER_RESTART_DELAY_SECONDS = 5


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
    app.add_handler(CommandHandler("toggle", toggle_social))
    app.add_handler(CommandHandler("Toggle", toggle_social))
    app.add_handler(CommandHandler("config_get", config_get))
    app.add_handler(CommandHandler("config_list", config_list))
    app.add_handler(CommandHandler("config_reset", config_reset))
    app.add_handler(CommandHandler("interesting_reg_add", interesting_reg_add))
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


def _log_listener_task_result(task: asyncio.Task) -> None:
    if task.cancelled():
        return
    exc = task.exception()
    if exc:
        logger.error(f"Telegram command listener stopped with error: {exc}")
    else:
        logger.warning("Telegram command listener stopped unexpectedly")


async def _run_command_listener(application):
    if not application.updater:
        logger.warning("Telegram Application has no Updater; command listener disabled")
        return

    logger.info("Starting Telegram command listener")
    while True:
        try:
            await application.initialize()
            await application.start()
            await application.updater.start_polling(drop_pending_updates=True)
            logger.info("Telegram command listener running")
            stop_future = asyncio.get_running_loop().create_future()
            await stop_future
        except asyncio.CancelledError:
            logger.info("Telegram command listener cancellation requested")
            raise
        except telegram.error.TelegramError as exc:
            logger.error(f"Telegram command listener failed with TelegramError: {exc}")
        except Exception as exc:
            logger.exception(f"Telegram command listener failed unexpectedly: {exc}")
        finally:
            try:
                if application.updater and application.updater.running:
                    await application.updater.stop()
            except Exception as exc:
                logger.warning(f"Unable to stop Telegram updater cleanly: {exc}")
            try:
                if application.running:
                    await application.stop()
            except Exception as exc:
                logger.warning(f"Unable to stop Telegram application cleanly: {exc}")
            try:
                await application.shutdown()
            except Exception as exc:
                logger.warning(f"Unable to shutdown Telegram application cleanly: {exc}")

        logger.warning(
            "Telegram command listener stopped unexpectedly; restarting in "
            f"{_COMMAND_LISTENER_RESTART_DELAY_SECONDS} seconds"
        )
        await asyncio.sleep(_COMMAND_LISTENER_RESTART_DELAY_SECONDS)


async def ensure_command_listener() -> asyncio.Task | None:
    global _listener_task, _listener_lock
    application = get_application()
    if application is None:
        logger.debug("Telegram command listener not started because TELEGRAM_BOT_TOKEN is missing")
        return None

    if not application.updater:
        logger.warning("Telegram Application has no Updater; command listener disabled")
        return None

    if _listener_lock is None:
        _listener_lock = asyncio.Lock()

    async with _listener_lock:
        if _listener_task and not _listener_task.done():
            return _listener_task

        loop = asyncio.get_running_loop()
        _listener_task = loop.create_task(
            _run_command_listener(application),
            name="telegram-command-listener",
        )
        _listener_task.add_done_callback(_log_listener_task_result)
        return _listener_task


async def shutdown_command_listener() -> None:
    global _listener_task
    task = _listener_task
    if task is None:
        return

    _listener_task = None
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    except Exception as exc:
        logger.error(f"Telegram command listener shutdown failed: {exc}")


def generate_flight_message(flight_data: dict[str, Any], interesting: dict[str, bool] | None = None) -> str:
    return render_flight_message(flight_data, interesting=interesting)


def _flight_url(flight_data: dict[str, Any], fallback_url: str | None = None) -> str:
    if fallback_url:
        return fallback_url
    flight_slug = flight_data.get("flight_name_iata") or flight_data.get("flight_name") or "unknown-flight"
    flight_slug = str(flight_slug).replace(" ", "").lower()
    return f"https://www.flightradar24.com/data/flights/{flight_slug}"


_NULLISH_REG_VALUES = {"", "null", "none"}


def _get_telegram_settings() -> dict[str, Any]:
    settings = cfg.get_config("platform_settings.telegram")
    if isinstance(settings, dict):
        return settings
    return {}


def _bool_setting(settings: dict[str, Any], key: str, default: bool) -> bool:
    value = settings.get(key)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "on"}:
            return True
        if lowered in {"false", "0", "no", "off"}:
            return False
    return default


def _build_registration_entities(
    message: str,
    registration_value: Any,
    registration_url: str | None,
) -> list[MessageEntity] | None:
    if not (registration_url and message):
        return None

    normalized = str(registration_value or "").strip()
    if not normalized or normalized.lower() in _NULLISH_REG_VALUES:
        return None

    offset = message.find(normalized)
    if offset == -1:
        return None

    return [
        MessageEntity(
            type=MessageEntityType.TEXT_LINK,
            offset=offset,
            length=len(normalized),
            url=registration_url,
        )
    ]


async def send_flight_update(
    chat_id: str,
    flight_data: dict[str, Any],
    image_path: str | None = None,
    image_bytes: bytes | None = None,
    message_text: str | None = None,
    flight_url: str | None = None,
    registration_url: str | None = None,
) -> None:
    application = get_application()
    if application is None:
        return

    message = message_text or generate_flight_message(flight_data)
    url = _flight_url(flight_data, fallback_url=flight_url)
    settings = _get_telegram_settings()
    notifications_enabled = _bool_setting(settings, "notifications_enabled", True)
    registration_links_enabled = _bool_setting(settings, "registration_link_enabled", True)
    if registration_links_enabled:
        entities = _build_registration_entities(
            message,
            flight_data.get("registration"),
            registration_url,
        )
    else:
        entities = None
    retries = 3
    flight_name = flight_data.get("flight_name_iata") or flight_data.get("flight_name") or "unknown-flight"

    for attempt in range(retries):
        try:
            started = time.perf_counter()
            send_photo = flight_data.get("registration") not in (None, "null") and (
                image_bytes is not None or (image_path and Path(image_path).exists())
            )
            if send_photo:
                if image_bytes is not None:
                    photo = telegram.InputFile(
                        io.BytesIO(image_bytes),
                        filename=Path(image_path).name if image_path else "flight.jpg",
                    )
                    photo_kwargs = {
                        "chat_id": chat_id,
                        "photo": photo,
                        "caption": message,
                        "reply_markup": {
                            "inline_keyboard": [[{"text": "Flightradar", "url": url}]],
                        },
                        "disable_notification": not notifications_enabled,
                    }
                    if entities is not None:
                        photo_kwargs["caption_entities"] = entities
                    await application.bot.send_photo(**photo_kwargs)
                else:
                    with open(image_path, "rb") as photo_file:
                        photo_kwargs = {
                            "chat_id": chat_id,
                            "photo": photo_file,
                            "caption": message,
                            "reply_markup": {
                                "inline_keyboard": [[{"text": "Flightradar", "url": url}]],
                            },
                            "disable_notification": not notifications_enabled,
                        }
                        if entities is not None:
                            photo_kwargs["caption_entities"] = entities
                        await application.bot.send_photo(**photo_kwargs)
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
                message_kwargs = {
                    "chat_id": chat_id,
                    "text": message,
                    "disable_web_page_preview": True,
                    "reply_markup": {
                        "inline_keyboard": [[{"text": "Flightradar", "url": url}]],
                    },
                    "disable_notification": not notifications_enabled,
                }
                if entities is not None:
                    message_kwargs["entities"] = entities
                await application.bot.send_message(**message_kwargs)
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


async def send_message(context: MessageContext, image_path: str | None = None) -> None:
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "-1002116996158")
    await send_flight_update(
        chat_id=chat_id,
        flight_data=context.flight_data,
        image_path=image_path,
        image_bytes=None,
        message_text=context.text,
        flight_url=context.flight_url,
        registration_url=context.registration_url,
    )
