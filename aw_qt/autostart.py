#!/usr/bin/env python3
"""
Autostart functionality for Samay
Handles automatic startup on system restart for different platforms
"""

import os
import sys
import subprocess
import platform
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class AutostartManager:
    """Manages autostart functionality across different platforms."""
    
    def __init__(self):
        self.platform = platform.system()
        self.bundle_id = "net.samay.Samay"
        
    def is_autostart_enabled(self) -> bool:
        """Check if autostart is currently enabled."""
        if self.platform == "Darwin":
            return self._is_macos_autostart_enabled()
        elif self.platform == "Linux":
            return self._is_linux_autostart_enabled()
        elif self.platform == "Windows":
            return self._is_windows_autostart_enabled()
        else:
            logger.warning(f"Autostart not supported on platform: {self.platform}")
            return False
    
    def enable_autostart(self) -> bool:
        """Enable autostart for the current platform."""
        if self.platform == "Darwin":
            return self._enable_macos_autostart()
        elif self.platform == "Linux":
            return self._enable_linux_autostart()
        elif self.platform == "Windows":
            return self._enable_windows_autostart()
        else:
            logger.warning(f"Autostart not supported on platform: {self.platform}")
            return False
    
    def disable_autostart(self) -> bool:
        """Disable autostart for the current platform."""
        if self.platform == "Darwin":
            return self._disable_macos_autostart()
        elif self.platform == "Linux":
            return self._disable_linux_autostart()
        elif self.platform == "Windows":
            return self._disable_windows_autostart()
        else:
            logger.warning(f"Autostart not supported on platform: {self.platform}")
            return False
    
    def _is_macos_autostart_enabled(self) -> bool:
        """Check if macOS LaunchAgent is enabled."""
        try:
            plist_path = os.path.expanduser("~/Library/LaunchAgents/net.samay.Samay.plist")
            if not os.path.exists(plist_path):
                return False
            
            # Check if LaunchAgent is loaded
            result = subprocess.run(
                ["launchctl", "list", "net.samay.Samay"],
                capture_output=True,
                text=True
            )
            return result.returncode == 0
        except Exception as e:
            logger.error(f"Error checking macOS autostart: {e}")
            return False
    
    def _enable_macos_autostart(self) -> bool:
        """Enable macOS LaunchAgent autostart."""
        try:
            # Find Samay.app bundle
            samay_app_path = self._find_samay_app()
            if not samay_app_path:
                logger.error("Samay.app not found")
                return False
            
            # Create LaunchAgents directory
            launch_agents_dir = os.path.expanduser("~/Library/LaunchAgents")
            os.makedirs(launch_agents_dir, exist_ok=True)
            
            # Create plist file
            plist_path = os.path.join(launch_agents_dir, "net.samay.Samay.plist")
            plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>net.samay.Samay</string>
    <key>ProgramArguments</key>
    <array>
        <string>{samay_app_path}/Contents/MacOS/aw-qt</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
    <key>ProcessType</key>
    <string>Background</string>
    <key>StandardOutPath</key>
    <string>/tmp/samay.out.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/samay.err.log</string>
</dict>
</plist>"""
            
            with open(plist_path, 'w') as f:
                f.write(plist_content)
            
            # Load the LaunchAgent
            subprocess.run(["launchctl", "load", plist_path], check=True)
            
            return True
            
        except Exception as e:
            logger.error(f"Error enabling macOS autostart: {e}")
            return False
    
    def _disable_macos_autostart(self) -> bool:
        """Disable macOS LaunchAgent autostart."""
        try:
            plist_path = os.path.expanduser("~/Library/LaunchAgents/net.samay.Samay.plist")
            
            # Unload the LaunchAgent if it exists
            if os.path.exists(plist_path):
                subprocess.run(["launchctl", "unload", plist_path], check=True)
                os.remove(plist_path)
            
            return True
            
        except Exception as e:
            logger.error(f"Error disabling macOS autostart: {e}")
            return False
    
    def _is_linux_autostart_enabled(self) -> bool:
        """Check if Linux desktop autostart is enabled."""
        try:
            autostart_path = os.path.expanduser("~/.config/autostart/aw-qt.desktop")
            return os.path.exists(autostart_path)
        except Exception as e:
            logger.error(f"Error checking Linux autostart: {e}")
            return False
    
    def _enable_linux_autostart(self) -> bool:
        """Enable Linux desktop autostart."""
        try:
            # Use existing Linux autostart script
            script_path = Path(__file__).parent.parent / "scripts" / "config-autostart.sh"
            if script_path.exists():
                subprocess.run([str(script_path)], check=True)
                return True
            else:
                logger.error("Linux autostart script not found")
                return False
        except Exception as e:
            logger.error(f"Error enabling Linux autostart: {e}")
            return False
    
    def _disable_linux_autostart(self) -> bool:
        """Disable Linux desktop autostart."""
        try:
            autostart_path = os.path.expanduser("~/.config/autostart/aw-qt.desktop")
            if os.path.exists(autostart_path):
                os.remove(autostart_path)
            
            return True
            
        except Exception as e:
            logger.error(f"Error disabling Linux autostart: {e}")
            return False
    
    def _is_windows_autostart_enabled(self) -> bool:
        """Check if Windows autostart is enabled."""
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run")
            try:
                winreg.QueryValueEx(key, "Samay")
                return True
            except FileNotFoundError:
                return False
            finally:
                winreg.CloseKey(key)
        except Exception as e:
            logger.error(f"Error checking Windows autostart: {e}")
            return False
    
    def _enable_windows_autostart(self) -> bool:
        """Enable Windows autostart."""
        try:
            import winreg
            # Find Samay executable
            samay_exe = self._find_samay_executable()
            if not samay_exe:
                logger.error("Samay executable not found")
                return False
            
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
            winreg.SetValueEx(key, "Samay", 0, winreg.REG_SZ, samay_exe)
            winreg.CloseKey(key)
            
            return True
            
        except Exception as e:
            logger.error(f"Error enabling Windows autostart: {e}")
            return False
    
    def _disable_windows_autostart(self) -> bool:
        """Disable Windows autostart."""
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
            winreg.DeleteValue(key, "Samay")
            winreg.CloseKey(key)
            
            return True
            
        except Exception as e:
            logger.error(f"Error disabling Windows autostart: {e}")
            return False
    
    def _find_samay_app(self) -> Optional[str]:
        """Find the Samay.app bundle path."""
        possible_paths = [
            "/Applications/Samay.app",
            os.path.expanduser("~/Applications/Samay.app"),
        ]
        
        # Also check relative to current script
        script_dir = Path(__file__).parent.parent.parent
        possible_paths.extend([
            str(script_dir / "dist" / "Samay.app"),
            str(script_dir / "dist" / "app" / "Samay.app"),
        ])
        
        for path in possible_paths:
            if os.path.exists(path) and os.path.exists(os.path.join(path, "Contents", "MacOS", "aw-qt")):
                return path
        
        return None
    
    def _find_samay_executable(self) -> Optional[str]:
        """Find the Samay executable path."""
        if self.platform == "Darwin":
            app_path = self._find_samay_app()
            if app_path:
                return os.path.join(app_path, "Contents", "MacOS", "aw-qt")
        elif self.platform == "Windows":
            # Look for aw-qt.exe in common locations
            possible_paths = [
                os.path.join(os.path.dirname(sys.executable), "aw-qt.exe"),
                os.path.join(os.path.dirname(sys.executable), "Scripts", "aw-qt.exe"),
            ]
            for path in possible_paths:
                if os.path.exists(path):
                    return path
        
        return None


def main():
    """Command line interface for autostart management."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Manage Samay autostart")
    parser.add_argument("action", choices=["enable", "disable", "status"], help="Action to perform")
    
    args = parser.parse_args()
    
    manager = AutostartManager()
    
    if args.action == "enable":
        success = manager.enable_autostart()
        if success:
            print("✅ Autostart enabled successfully")
        else:
            print("❌ Failed to enable autostart")
            sys.exit(1)
    elif args.action == "disable":
        success = manager.disable_autostart()
        if success:
            print("✅ Autostart disabled successfully")
        else:
            print("❌ Failed to disable autostart")
            sys.exit(1)
    elif args.action == "status":
        enabled = manager.is_autostart_enabled()
        if enabled:
            print("✅ Autostart is enabled")
        else:
            print("❌ Autostart is disabled")


if __name__ == "__main__":
    main()
