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
        config = load_config_toml("aw-qt", default_config)
        config_section: Any = config["aw-qt" if not testing else "aw-qt-testing"]

        self.autostart_modules: List[str] = config_section["autostart_modules"]
        
        # Authentication settings
        self.auth_token: Optional[str] = None
        self.api_url: Optional[str] = None
        self.is_authenticated: bool = False
        
        # Load authentication data if it exists
        self._load_auth_data()
    
    def _get_auth_file_path(self) -> Path:
        """Get the path to the authentication data file."""
        config_dir = Path.home() / ".config" / "aw-qt"
        config_dir.mkdir(parents=True, exist_ok=True)
        return config_dir / "auth.json"
    
    def _load_auth_data(self) -> None:
        """Load authentication data from file."""
        auth_file = self._get_auth_file_path()
        
        if auth_file.exists():
            try:
                logger.info(f"🔍 Loading authentication data from: {auth_file}")
                with open(auth_file, 'r') as f:
                    data = json.load(f)
                
                self.auth_token = data.get('token')
                self.api_url = data.get('api_url') or data.get('url') or data.get('target_url')
                self.is_authenticated = bool(self.auth_token and self.api_url)
                
                if self.is_authenticated:
                    logger.info(f"✅ Loaded authentication data:")
                    logger.info(f"   🔑 Token: {self.auth_token[:20]}...{self.auth_token[-10:] if len(self.auth_token) > 30 else ''}")
                    logger.info(f"   🌐 API URL: {self.api_url}")
                    logger.info(f"   📊 Token length: {len(self.auth_token)} characters")
                else:
                    logger.warning("⚠️ Authentication data incomplete - missing token or API URL")
                    
            except Exception as e:
                logger.error(f"❌ Failed to load authentication data: {e}")
                self.auth_token = None
                self.api_url = None
                self.is_authenticated = False
        else:
            logger.info("ℹ️ No authentication data file found - user not authenticated")
    
    def save_auth_data(self, token: str, api_url: str) -> bool:
        """Save authentication data to file."""
        try:
            logger.info(f"💾 Saving authentication data:")
            logger.info(f"   🔑 Token: {token[:20]}...{token[-10:] if len(token) > 30 else ''}")
            logger.info(f"   🌐 API URL: {api_url}")
            logger.info(f"   📊 Token length: {len(token)} characters")
            
            auth_file = self._get_auth_file_path()
            data = {
                'token': token,
                'api_url': api_url,
                'timestamp': str(Path().cwd())  # Simple timestamp placeholder
            }
            
            with open(auth_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            # Update instance variables
            self.auth_token = token
            self.api_url = api_url
            self.is_authenticated = True
            
            logger.info(f"✅ Authentication data saved successfully to: {auth_file}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to save authentication data: {e}")
            return False
    
    def clear_auth_data(self) -> bool:
        """Clear authentication data."""
        try:
            logger.info("🗑️ Clearing authentication data")
            
            auth_file = self._get_auth_file_path()
            if auth_file.exists():
                auth_file.unlink()
                logger.info(f"✅ Authentication data file deleted: {auth_file}")
            
            # Update instance variables
            self.auth_token = None
            self.api_url = None
            self.is_authenticated = False
            
            logger.info("✅ Authentication data cleared successfully")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to clear authentication data: {e}")
            return False
    
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
