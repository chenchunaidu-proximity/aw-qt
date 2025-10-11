import logging
import json
import os
from pathlib import Path
from typing import List, Any, Optional

from aw_core.config import load_config_toml
from aw_datastore.storages.token_manager import TokenManager

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
        
        # Initialize TokenManager for authentication storage
        self.token_manager = TokenManager(testing=testing)
        
        # Authentication settings
        self.auth_token: Optional[str] = None
        self.api_url: Optional[str] = None
        self.is_authenticated: bool = False
        
        # Load authentication data if it exists
        self._load_auth_data()
    
    
    def _load_auth_data(self) -> None:
        """Load authentication data from JSON storage."""
        try:
            token_data = self.token_manager.get_token_data()
            if token_data:
                token, url = token_data
                self.auth_token = token
                self.api_url = url
                self.is_authenticated = True
                logger.info(f"🔐 Loaded authentication data from JSON storage")
            else:
                logger.info("ℹ️ No authentication data found - user not authenticated")
        except Exception as e:
            logger.error(f"❌ Failed to load authentication data: {e}")
            logger.info("ℹ️ No authentication data found - user not authenticated")
    
    def save_auth_data(self, token: str, api_url: str) -> bool:
        """Save authentication data to JSON storage."""
        try:
            logger.info(f"💾 Saving authentication data")
            
            success = self.token_manager.store_token_data(token, api_url)
            if success:
                logger.info(f"✅ Authentication data saved to JSON storage")
                
                # Update instance variables
                self.auth_token = token
                self.api_url = api_url
                self.is_authenticated = True
                return True
            else:
                logger.error(f"❌ Failed to save authentication data")
                return False
            
        except Exception as e:
            logger.error(f"❌ Failed to save authentication data: {e}")
            return False
    
    def clear_auth_data(self) -> bool:
        """Clear authentication data from JSON storage."""
        try:
            logger.info("🗑️ Clearing authentication data")
            
            success = self.token_manager.delete_token_data()
            if success:
                logger.info(f"✅ Authentication data cleared from JSON storage")
                
                # Update instance variables
                self.auth_token = None
                self.api_url = None
                self.is_authenticated = False
                return True
            else:
                logger.error(f"❌ Failed to clear authentication data")
                return False
            
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
