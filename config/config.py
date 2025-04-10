import os
import yaml
from pathlib import Path

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
        'time_range_hours': 2,
        'preloaded_data': True
    },
    'database': {
        'registration_table_id': 441094,
        'model_table_id': 441097,
        'model_table_key': 'model'
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
    }
}

def load_config():
    """Load configuration from YAML file"""
    if not CONFIG_PATH.exists():
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG
    
    with open(CONFIG_PATH, 'r') as f:
        return yaml.safe_load(f) or DEFAULT_CONFIG

def save_config(config):
    """Save configuration to YAML file"""
    with open(CONFIG_PATH, 'w') as f:
        yaml.safe_dump(config, f)

def update_config(key, value):
    """Update a specific configuration value"""
    config = load_config()
    keys = key.split('.')
    current = config
    
    for k in keys[:-1]:
        if k not in current:
            current[k] = {}
        current = current[k]
    
    current[keys[-1]] = value
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
