from types import SimpleNamespace

import asyncio

import pytest

from socials import telegram as tg


def test_parse_toggle_args_accepts_on_off_case_insensitive():
    enabled, platform = tg._parse_toggle_args(["On", "Twitter"])

    assert enabled is True
    assert platform == "twitter"


def test_parse_toggle_args_rejects_invalid_action():
    with pytest.raises(ValueError, match="Accion invalida"):
        tg._parse_toggle_args(["enable", "twitter"])


def test_parse_toggle_args_rejects_invalid_platform():
    with pytest.raises(ValueError, match="Plataforma invalida"):
        tg._parse_toggle_args(["off", "tiktok"])


def test_toggle_social_updates_config_for_admin(monkeypatch):
    captured = {}

    def fake_update_config(key, value):
        captured["key"] = key
        captured["value"] = value

    monkeypatch.setattr(tg.cfg, "update_config", fake_update_config)
    monkeypatch.setattr(tg, "is_admin", lambda user_id: True)

    replies = []

    async def fake_reply_text(text):
        replies.append(text)

    message = SimpleNamespace(
        from_user=SimpleNamespace(id=1),
        reply_text=fake_reply_text,
    )
    update = SimpleNamespace(message=message)
    context = SimpleNamespace(args=["off", "threads"])

    asyncio.run(tg.toggle_social(update, context))

    assert captured == {"key": "social_networks.threads", "value": False}
    assert replies == ["threads desactivada"]


def test_toggle_social_denies_non_admin():
    replies = []

    async def fake_reply_text(text):
        replies.append(text)

    message = SimpleNamespace(
        from_user=SimpleNamespace(id=10),
        reply_text=fake_reply_text,
    )
    update = SimpleNamespace(message=message)
    context = SimpleNamespace(args=["on", "twitter"])

    asyncio.run(tg.toggle_social(update, context))

    assert replies == ["Acceso denegado"]


def test_toggle_social_legacy_alias_updates_config_for_admin(monkeypatch):
    captured = {}

    def fake_update_config(key, value):
        captured["key"] = key
        captured["value"] = value

    monkeypatch.setattr(tg.cfg, "update_config", fake_update_config)
    monkeypatch.setattr(tg, "is_admin", lambda user_id: True)

    replies = []

    async def fake_reply_text(text):
        replies.append(text)

    message = SimpleNamespace(
        text="/toggle.command off twitter",
        reply_text=fake_reply_text,
    )
    update = SimpleNamespace(
        effective_message=message,
        effective_user=SimpleNamespace(id=1),
    )
    context = SimpleNamespace(args=[])

    asyncio.run(tg.toggle_social_legacy_alias(update, context))

    assert captured == {"key": "social_networks.twitter", "value": False}
    assert replies == ["twitter desactivada"]
