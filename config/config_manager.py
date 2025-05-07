import json
from loguru import logger


def load_config(config_path='config/config.json'):
    """
    Load the configuration from a JSON file and return it as a dictionary.
    
    Args:
        config_path (str): Path to the configuration JSON file. Defaults to 'config/config.json'.
    
    Returns:
        dict: The configuration dictionary.
    """
    try:
        with open(config_path, 'r') as file:
            config = json.load(file)
        logger.info("Configuration loaded successfully.")
        return config
    except FileNotFoundError:
        logger.error(f"The configuration file '{config_path}' was not found.")
        return {}
    except json.JSONDecodeError:
        logger.error(f"The configuration file '{config_path}' contains invalid JSON.")
        return {}
    except Exception as e:
        logger.error(f"An unexpected error occurred while loading the configuration file: {e}")
        return {}
    

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