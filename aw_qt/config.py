import logging
import json
import os
from pathlib import Path
from typing import List, Any, Optional

from aw_core.config import load_config_toml

logger = logging.getLogger(__name__)


default_config = """
[aw-qt]
autostart_modules = ["aw-server", "aw-watcher-window"]

[aw-qt-testing]
autostart_modules = ["aw-server", "aw-watcher-window"]
""".strip()


class AwQtSettings:
    def __init__(self, testing: bool):
        """
        An instance of loaded settings, containing a list of modules to autostart.
        Constructor takes a `testing` boolean as an argument
        """
        self.testing = testing  # Store testing flag as instance variable
        
        config = load_config_toml("aw-qt", default_config)
        config_section: Any = config["aw-qt" if not testing else "aw-qt-testing"]

        self.autostart_modules: List[str] = config_section["autostart_modules"]
        
        # Authentication settings
        self.auth_token: Optional[str] = None
        self.api_url: Optional[str] = None
        self.is_authenticated: bool = False
        
        # Load authentication data if it exists
        self._load_auth_data()
    
    
    def _load_auth_data(self) -> None:
        """Load authentication data from aw-server SQLite storage."""
        try:
            import requests
            server_url = f"http://localhost:{5666 if self.testing else 5600}"
            response = requests.get(f"{server_url}/api/0/token", timeout=2)
            if response.status_code == 200:
                data = response.json()
                token = data.get('token')
                url = data.get('url')
                if token and url:
                    self.auth_token = token
                    self.api_url = url
                    self.is_authenticated = True
                    logger.info(f"🔐 Loaded authentication data from aw-server")
                    return
            
            logger.info("ℹ️ No authentication data found - user not authenticated")

        except Exception as e:
            logger.debug(f"Could not load from aw-server: {e}")
            # Try to load from local fallback storage
            self._load_auth_data_fallback()
    
    def _load_auth_data_fallback(self) -> None:
        """Load authentication data from local fallback storage when aw-server is unavailable."""
        try:
            import json
            import os
            
            # Try to load from local JSON file as fallback
            fallback_path = os.path.expanduser("~/Library/Application Support/activitywatch/aw-qt/auth.json")
            if os.path.exists(fallback_path):
                with open(fallback_path, 'r') as f:
                    data = json.load(f)
                    token = data.get('token')
                    url = data.get('url')
                    if token and url:
                        self.auth_token = token
                        self.api_url = url
                        self.is_authenticated = True
                        logger.info(f"🔐 Loaded authentication data from fallback storage")
                        return
            
            logger.info("ℹ️ No authentication data found in fallback storage - user not authenticated")
            
        except Exception as e:
            logger.debug(f"Could not load from fallback storage: {e}")
            logger.info("ℹ️ No authentication data found - user not authenticated")
    
    def save_auth_data(self, token: str, api_url: str) -> bool:
        """Save authentication data to aw-server SQLite storage."""
        try:
            logger.info(f"💾 Saving authentication data")
            
            import requests
            server_url = f"http://localhost:{5666 if self.testing else 5600}"
            data = {"token": token, "url": api_url}
            response = requests.post(f"{server_url}/api/0/token", json=data, timeout=5)
            if response.status_code == 200:
                logger.info(f"✅ Authentication data saved to aw-server")
                
                # Also save to fallback storage
                self._save_auth_data_fallback(token, api_url)
                
                # Update instance variables
                self.auth_token = token
                self.api_url = api_url
                self.is_authenticated = True
                return True
            else:
                logger.error(f"❌ Failed to save to aw-server: {response.status_code}")
                # Try fallback storage anyway
                self._save_auth_data_fallback(token, api_url)
                return False
            
        except Exception as e:
            logger.error(f"❌ Failed to save authentication data: {e}")
            # Try fallback storage as last resort
            self._save_auth_data_fallback(token, api_url)
            return False
    
    def _save_auth_data_fallback(self, token: str, api_url: str) -> None:
        """Save authentication data to local fallback storage."""
        try:
            import json
            import os
            
            # Ensure directory exists
            fallback_dir = os.path.expanduser("~/Library/Application Support/activitywatch/aw-qt")
            os.makedirs(fallback_dir, exist_ok=True)
            
            # Save to local JSON file
            fallback_path = os.path.join(fallback_dir, "auth.json")
            data = {"token": token, "url": api_url}
            with open(fallback_path, 'w') as f:
                json.dump(data, f)
            
            logger.info(f"💾 Authentication data saved to fallback storage")
            
        except Exception as e:
            logger.error(f"❌ Failed to save to fallback storage: {e}")
    
    def clear_auth_data(self) -> bool:
        """Clear authentication data from aw-server SQLite storage."""
        try:
            logger.info("🗑️ Clearing authentication data")
            
            import requests
            server_url = f"http://localhost:{5666 if self.testing else 5600}"
            response = requests.delete(f"{server_url}/api/0/token", timeout=5)
            if response.status_code == 200:
                logger.info(f"✅ Authentication data cleared from aw-server")
                
                # Also clear from fallback storage
                self._clear_auth_data_fallback()
                
                # Update instance variables
                self.auth_token = None
                self.api_url = None
                self.is_authenticated = False
                return True
            else:
                logger.error(f"❌ Failed to clear from aw-server: {response.status_code}")
                # Try fallback storage anyway
                self._clear_auth_data_fallback()
                return False
            
        except Exception as e:
            logger.error(f"❌ Failed to clear authentication data: {e}")
            # Try fallback storage as last resort
            self._clear_auth_data_fallback()
            return False
    
    def _clear_auth_data_fallback(self) -> None:
        """Clear authentication data from local fallback storage."""
        try:
            import os
            
            fallback_path = os.path.expanduser("~/Library/Application Support/activitywatch/aw-qt/auth.json")
            if os.path.exists(fallback_path):
                os.remove(fallback_path)
                logger.info(f"🗑️ Authentication data cleared from fallback storage")
            else:
                logger.info("ℹ️ No fallback storage file to clear")
                
        except Exception as e:
            logger.error(f"❌ Failed to clear fallback storage: {e}")
    
    def get_auth_token(self) -> Optional[str]:
        """Get the stored authentication token."""
        if self.is_authenticated and self.auth_token:
            logger.debug(f"🔑 Returning stored token: {self.auth_token[:20]}...")
            return self.auth_token
        else:
            logger.debug("🔑 No authentication token available")
            return None
    
    def get_api_url(self) -> Optional[str]:
        """Get the stored API URL."""
        if self.is_authenticated and self.api_url:
            logger.debug(f"🌐 Returning stored API URL: {self.api_url}")
            return self.api_url
        else:
            logger.debug("🌐 No API URL available")
            return None
