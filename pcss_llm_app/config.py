import os
import keyring
import json
from pathlib import Path

# Constants for Keyring
SERVICE_NAME = "pcss_llm_app"
USERNAME = "api_key"

class ConfigManager:
    """
    Manages application configuration and secure secrets.
    """
    def __init__(self):
        self.config_path = Path("settings.json")
        self._config = self._load_config()

    def _load_config(self):
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r') as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def save_config(self):
        with open(self.config_path, 'w') as f:
            json.dump(self._config, f, indent=4)

    def get_api_key(self):
        """
        Retrieves API key from (priority order):
        1. Environment Variable (PCSS_API_KEY)
        2. System Keyring
        """
        # 1. Environment Variable
        env_key = os.environ.get("PCSS_API_KEY")
        if env_key:
            return env_key

        # 2. Keyring
        try:
            return keyring.get_password(SERVICE_NAME, USERNAME)
        except Exception as e:
            # print(f"Keyring error: {e}")
            return None

    def set_api_key(self, api_key):
        """
        Saves API key to system keyring.
        """
        try:
            keyring.set_password(SERVICE_NAME, USERNAME, api_key)
            return True
        except Exception as e:
            # print(f"Error saving to keyring: {e}")
            return False

    def get(self, key, default=None):
        return self._config.get(key, default)

    def set(self, key, value):
        self._config[key] = value
        self.save_config()

    def get_workspace_path(self):
        """
        Returns workspace path, default to ~/Documents/Bielik_Workspace
        """
        default_path = str(Path.home() / "Documents" / "Bielik_Workspace")
        path = self._config.get("workspace_path", default_path)
        
        try:
            # Ensure directory exists
            Path(path).mkdir(parents=True, exist_ok=True)
        except Exception as e:
            # Fallback gracefully if settings.json contains a path from another OS
            print(f"Warning: Could not access workspace path '{path}' ({e}). Falling back to default.")
            path = default_path
            # If even the default fails (e.g., Documents doesn't exist), just use home dir
            try:
                Path(path).mkdir(parents=True, exist_ok=True)
            except Exception:
                path = str(Path.home() / "Bielik_Workspace")
                Path(path).mkdir(parents=True, exist_ok=True)
                
        return path

    def set_workspace_path(self, path):
        self._config["workspace_path"] = str(path)
        self.save_config()

    def get_base_url(self):
        """
        Returns the LLM API base URL from settings.
        Default: https://llm.hpc.pcss.pl/v1
        """
        return self._config.get("base_url", "https://llm.hpc.pcss.pl/v1")

    def set_base_url(self, url):
        self._config["base_url"] = str(url)
        self.save_config()
