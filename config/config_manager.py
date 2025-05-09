import json
import os
from loguru import logger

# Define a mapping for environment variables to config keys if they differ
# Or define a list of keys that should be preferentially loaded from environment.
# For simplicity, this example will assume environment variables match the top-level keys in config.json
# or nested keys using a double underscore (__) as a separator, e.g., BASEROW__DB_ID for config['baserow']['db_id']

def _get_env_var(key, default=None):
    """Helper to get environment variable."""
    return os.environ.get(key, default)

def _override_with_env_vars(config_dict, parent_key=""):
    """
    Recursively overrides dictionary values with environment variables.
    Environment variables are expected to be named like PARENTKEY__CHILDKEY__GRANDCHILDKEY.
    """
    for key, value in config_dict.items():
        # Construct the environment variable name
        env_var_name_parts = [part for part in [parent_key, key] if part] # Filter out empty parent_key for top level
        env_var_name = "__".join(env_var_name_parts).upper()

        if isinstance(value, dict):
            _override_with_env_vars(value, env_var_name) # Pass the constructed prefix
        else:
            env_value = _get_env_var(env_var_name)
            if env_value is not None:
                # Attempt to cast env_value to the type of the original value
                original_type = type(value)
                if original_type == bool:
                    config_dict[key] = env_value.lower() in ['true', '1', 't', 'y', 'yes']
                elif original_type == int:
                    try:
                        config_dict[key] = int(env_value)
                    except ValueError:
                        logger.warning(f"Could not cast env var {env_var_name}='{env_value}' to int. Using original value.")
                elif original_type == float:
                    try:
                        config_dict[key] = float(env_value)
                    except ValueError:
                        logger.warning(f"Could not cast env var {env_var_name}='{env_value}' to float. Using original value.")
                else: # str or other types
                    config_dict[key] = env_value
                logger.info(f"Config key '{'.'.join(env_var_name_parts).lower()}' overridden by environment variable '{env_var_name}'.")


def load_config(config_path='config/config.json'):
    """
    Load configuration from a JSON file, then override with environment variables.
    
    Args:
        config_path (str): Path to the configuration JSON file. Defaults to 'config/config.json'.
    
    Returns:
        dict: The configuration dictionary.
    """
    config = {}
    try:
        with open(config_path, 'r') as file:
            config = json.load(file)
        logger.info(f"Configuration loaded successfully from JSON file: '{config_path}'.")
    except FileNotFoundError:
        logger.warning(f"The configuration file '{config_path}' was not found. Proceeding with environment variables and defaults if any.")
    except json.JSONDecodeError:
        logger.error(f"The configuration file '{config_path}' contains invalid JSON. Cannot load base configuration.")
        # Depending on requirements, you might want to return {} or raise an error.
        # For now, we'll proceed, allowing env vars to populate the config.
    except Exception as e:
        logger.error(f"An unexpected error occurred while loading the configuration file '{config_path}': {e}")
        # As above, decide error handling strategy.

    # Override with environment variables
    # This simple example overrides top-level keys.
    # For nested keys, a more sophisticated approach is needed (e.g. BASEROW_API_URL for config['baserow']['api_url'])
    # The _override_with_env_vars function handles nested keys.
    _override_with_env_vars(config)
    
    if not config:
        logger.warning("Configuration is empty after attempting to load from JSON and environment variables.")
        
    return config
    

def modify_config(key_path, new_value, config_path='config/config.json'):
    """
    Modify a configuration value in the JSON file.
    
    Args:
        key_path (str or list): The path to the key in the configuration dictionary. 
                               Can be a dot-separated string or a list of keys.
        new_value: The new value to set.
        config_path (str): Path to the configuration JSON file. Defaults to 'config/config.json'.
    
    Returns:
        bool: True if the modification was successful, False otherwise.
    """
    try:
        # Load the configuration
        config = load_config(config_path)
        
        # Convert key_path to a list if it's a string
        if isinstance(key_path, str):
            key_path = key_path.split('.')
        
        # Traverse the dictionary to find the key to modify
        current_level = config
        for key in key_path[:-1]:
            if key not in current_level:
                logger.error(f"Key '{key}' not found in the configuration.")
                return False
            current_level = current_level[key]
        
        # Modify the value
        current_level[key_path[-1]] = new_value
        
        # Dump the modified dictionary back to the JSON file
        with open(config_path, 'w') as file:
            json.dump(config, file, indent=4)
        
        logger.info("Configuration modified successfully.")
        return True
    except Exception as e:
        logger.error(f"An error occurred while modifying the configuration: {e}")
        return False


# Example usage:
if __name__ == "__main__":
    config = load_config()
    logger.info(config)
