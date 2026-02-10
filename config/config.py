import yaml
from pathlib import Path
from typing import Any

CONFIG_PATH = Path(__file__).parent / 'config.yaml'

# Default configuration
DEFAULT_CONFIG = {
    'logging': {
        'log_file': 'logs/lemd_spotter.log',
        'warning_log_file': 'logs/lemd_spotter_warning.log',
        'log_level': 'DEBUG',
        'log_rotation': '10 MB'
    },
    'api': {
        'airport_icao': 'LEMD',
        'time_range_hours': 2,
        'preloaded_data': True,
        'aeroapi': {
            'monthly_budget_per_key_usd': 5.0,
            'usage_cache_ttl_seconds': 600,
        },
    },
    'database': {
        'provider': 'supabase',
        'airport_icao': 'LEMD'
    },
    'social_networks': {
        'telegram': True,
        'bluesky': False,
        'twitter': False,
        'instagram': False,
        'linkedin': False,
        'threads': False
    },
    'execution': {
        'interval': (2 * 60 * 60) - 600  # 2 hours minus 10 minutes
    },
    'usage_monitoring': {
        'enabled': True,
        'db_path': 'database/usage_metrics.db',
        'x': {
            'enforce_budget': True,
            'monthly_budget_usd': 10.0,
            'default_cost_per_call_usd': 0.01,
            'endpoint_costs_usd': {
                'POST /2/tweets': 0.01,
                'POST /1.1/media/upload.json': 0.01,
                'GET /2/usage/tweets': 0.01,
            },
        },
    }
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if (
            key in merged
            and isinstance(merged[key], dict)
            and isinstance(value, dict)
        ):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _coerce_value(value: Any) -> Any:
    if not isinstance(value, str):
        return value

    lowered = value.strip().lower()
    if lowered == 'true':
        return True
    if lowered == 'false':
        return False

    try:
        return int(value)
    except ValueError:
        pass

    try:
        return float(value)
    except ValueError:
        return value

def load_config():
    """Load configuration from YAML file"""
    if not CONFIG_PATH.exists():
        save_config(DEFAULT_CONFIG)
        return dict(DEFAULT_CONFIG)

    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        loaded = yaml.safe_load(f)

    if not isinstance(loaded, dict):
        save_config(DEFAULT_CONFIG)
        return dict(DEFAULT_CONFIG)

    return _deep_merge(DEFAULT_CONFIG, loaded)

def save_config(config):
    """Save configuration to YAML file"""
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        yaml.safe_dump(config, f, sort_keys=False)

def update_config(key, value):
    """Update a specific configuration value"""
    config = load_config()
    keys = key.split('.')
    current = config
    
    for k in keys[:-1]:
        if k not in current:
            current[k] = {}
        current = current[k]

    current[keys[-1]] = _coerce_value(value)
    save_config(config)

def get_config(key):
    """Get a specific configuration value"""
    config = load_config()
    keys = key.split('.')
    current = config
    
    for k in keys:
        if k not in current:
            return None
        current = current[k]
    
    return current

# Load initial configuration
config = load_config()
