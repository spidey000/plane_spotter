from __future__ import annotations

from config import supabase_store as store


def test_flatten_config_creates_dot_notation_keys():
    config = {
        "social_networks": {"telegram": True, "twitter": False},
        "platform_settings": {"telegram": {"notifications_enabled": True}},
        "image_finder": {
            "providers": ["planespotters"],
            "enabled": True,
        },
    }

    flattened = store.flatten_config(config)

    assert flattened["social_networks.telegram"] is True
    assert flattened["social_networks.twitter"] is False
    assert flattened["platform_settings.telegram.notifications_enabled"] is True
    assert flattened["image_finder.providers"] == ["planespotters"]
    assert flattened["image_finder.enabled"] is True


def test_expand_rows_reconstructs_nested_dict():
    rows = [
        {"key_path": "social_networks.telegram", "value": True},
        {"key_path": "platform_settings.telegram.notifications_enabled", "value": False},
        {"key_path": "image_finder.providers", "value": ["planespotters", "jetphotos"]},
    ]

    reconstructed = store.expand_rows(rows)

    assert reconstructed["social_networks"]["telegram"] is True
    assert (
        reconstructed["platform_settings"]["telegram"]["notifications_enabled"]
        is False
    )
    assert reconstructed["image_finder"]["providers"] == ["planespotters", "jetphotos"]
