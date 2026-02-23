from __future__ import annotations

from pathlib import Path

import yaml

import config.config as cfg


def _patch_config_path(monkeypatch, tmp_path: Path) -> Path:
    config_path = tmp_path / "config.yaml"
    monkeypatch.setattr(cfg, "CONFIG_PATH", config_path)
    return config_path


def test_update_config_only_writes_local_when_supabase_disabled(monkeypatch, tmp_path):
    config_path = _patch_config_path(monkeypatch, tmp_path)

    monkeypatch.setattr(cfg.supabase_store, "is_enabled", lambda: False)

    def _fail(*_args, **_kwargs):  # pragma: no cover - should never run
        raise AssertionError("set_remote_value should not be called when disabled")

    monkeypatch.setattr(cfg.supabase_store, "set_remote_value", _fail)

    cfg.update_config("social_networks.twitter", "true")

    written = yaml.safe_load(config_path.read_text())
    assert written["social_networks"]["twitter"] is True


def test_update_config_calls_supabase_when_enabled(monkeypatch, tmp_path):
    config_path = _patch_config_path(monkeypatch, tmp_path)

    monkeypatch.setattr(cfg.supabase_store, "is_enabled", lambda: True)
    captured: dict[str, tuple[str, object]] = {}

    def _capture(key, value):
        captured["call"] = (key, value)

    monkeypatch.setattr(cfg.supabase_store, "set_remote_value", _capture)

    cfg.update_config("execution.interval", "6000")

    assert captured.get("call") == ("execution.interval", 6000)

    written = yaml.safe_load(config_path.read_text())
    assert written["execution"]["interval"] == 6000
