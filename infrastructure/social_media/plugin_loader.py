import os
import importlib.util
import inspect
from typing import List
from loguru import logger
from core.interfaces import SocialProvider

class PluginLoader:
    def __init__(self, plugin_dir: str):
        self.plugin_dir = plugin_dir

    def load_plugins(self) -> List[SocialProvider]:
        plugins = []
        if not os.path.exists(self.plugin_dir):
            logger.warning(f"Plugin directory {self.plugin_dir} does not exist.")
            return plugins

        logger.info(f"Scanning for plugins in {self.plugin_dir}")
        
        for filename in os.listdir(self.plugin_dir):
            if filename.endswith(".py") and not filename.startswith("__"):
                plugin_path = os.path.join(self.plugin_dir, filename)
                module_name = filename[:-3]
                
                try:
                    spec = importlib.util.spec_from_file_location(module_name, plugin_path)
                    if spec and spec.loader:
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)
                        
                        # Find classes that implement SocialProvider
                        for name, obj in inspect.getmembers(module):
                            if (inspect.isclass(obj) and 
                                issubclass(obj, SocialProvider) and 
                                obj is not SocialProvider):
                                
                                try:
                                    instance = obj()
                                    plugins.append(instance)
                                    logger.info(f"Loaded social plugin: {name} from {filename}")
                                except Exception as e:
                                    logger.error(f"Failed to instantiate plugin {name}: {e}")
                except Exception as e:
                    logger.error(f"Failed to load plugin from {filename}: {e}")
        
        return plugins
