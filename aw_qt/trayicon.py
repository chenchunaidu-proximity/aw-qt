import logging
import os
import signal
import subprocess
import sys
import webbrowser
import requests
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse, parse_qs

import aw_core
from PyQt6 import QtCore
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QMenu,
    QMessageBox,
    QPushButton,
    QSystemTrayIcon,
    QWidget,
)

from .manager import Manager, Module
from .config import AwQtSettings

logger = logging.getLogger(__name__)


def get_env() -> Dict[str, str]:
    """
    Necessary for xdg-open to work properly when PyInstaller overrides LD_LIBRARY_PATH

    https://github.com/ActivityWatch/activitywatch/issues/208#issuecomment-417346407
    """
    env = dict(os.environ)  # make a copy of the environment
    lp_key = "LD_LIBRARY_PATH"  # for GNU/Linux and *BSD.
    lp_orig = env.get(lp_key + "_ORIG")
    if lp_orig is not None:
        env[lp_key] = lp_orig  # restore the original, unmodified value
    else:
        # This happens when LD_LIBRARY_PATH was not set.
        # Remove the env var as a last resort:
        env.pop(lp_key, None)
    return env


def open_url(url: str) -> None:
    if sys.platform == "linux":
        env = get_env()
        subprocess.Popen(["xdg-open", url], env=env)
    else:
        webbrowser.open(url)


def open_webui(root_url: str) -> None:
    print("Opening dashboard")
    open_url(root_url)


def open_apibrowser(root_url: str) -> None:
    print("Opening api browser")
    open_url(root_url + "/api")


def open_dir(d: str) -> None:
    """From: http://stackoverflow.com/a/1795849/965332"""
    if sys.platform == "win32":
        os.startfile(d)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", d])
    else:
        env = get_env()
        subprocess.Popen(["xdg-open", d], env=env)


def get_auth_status(root_url: str) -> tuple[bool, str]:
    """Check if user is authenticated and return status and token."""
    try:
        response = requests.get(f"{root_url}/api/0/token", timeout=5)
        if response.status_code == 200:
            data = response.json()
            token = data.get('token', '')
            return bool(token), token
        return False, ""
    except requests.RequestException:
        return False, ""


def logout_user(root_url: str) -> bool:
    """Logout user by deleting the stored token."""
    try:
        response = requests.delete(f"{root_url}/api/0/token", timeout=5)
        return response.status_code == 200
    except requests.RequestException:
        return False


def open_auth_page(root_url: str) -> None:
    """Open authentication page in web browser."""
    # This would typically be the frontend team's authentication page
    auth_url = "https://samay.example.com/auth"  # Replace with actual auth URL
    open_url(auth_url)


class TrayIcon(QSystemTrayIcon):
    def __init__(
        self,
        manager: Manager,
        icon: QIcon,
        parent: Optional[QWidget] = None,
        testing: bool = False,
    ) -> None:
        QSystemTrayIcon.__init__(self, icon, parent)
        self._parent = parent  # QSystemTrayIcon also tries to save parent info but it screws up the type info
        self.setToolTip("Samay" + (" (testing)" if testing else ""))

        self.manager = manager
        self.testing = testing

        self.root_url = f"http://localhost:{5666 if self.testing else 5600}"
        self.activated.connect(self.on_activated)
        
        # Load configuration
        self.config = AwQtSettings(testing=testing)
        
        # Authentication status (use config values)
        self.is_authenticated = self.config.is_authenticated
        self.auth_token = self.config.auth_token
        self.api_url = self.config.api_url

        self._build_rootmenu()
        self._update_auth_status()

    def on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            open_webui(self.root_url)
    
    def _update_auth_status(self) -> None:
        """Update authentication status."""
        # Use stored authentication status instead of API call
        # The old get_auth_status was for the old ActivityWatch API
        # Now we use the token and API URL from Frontend
        self._update_tooltip()
    
    def _update_tooltip(self) -> None:
        """Update tooltip with authentication status."""
        base_tooltip = "Samay" + (" (testing)" if self.testing else "")
        if self.is_authenticated:
            self.setToolTip(f"{base_tooltip} - Authenticated")
        else:
            self.setToolTip(f"{base_tooltip} - Not authenticated")
    
    def handle_samay_url(self, url: str) -> None:
        """
        Handle samay:// URL scheme from Frontend.
        Expected format: samay://token?token=JWT_TOKEN&url=API_URL
        """
        logger.info(f"🔗 TrayIcon received samay:// URL: {url}")
        
        # Parse the URL to extract token and API URL
        if url.startswith("samay://"):
            # Remove the scheme part
            url_part = url[8:]  # Remove "samay://"
            
            # Parse query parameters
            params = {}
            if "?" in url_part:
                query_part = url_part.split("?")[1]
                for param in query_part.split("&"):
                    if "=" in param:
                        key, value = param.split("=", 1)
                        params[key] = value
            
            token = params.get("token")
            api_url = params.get("url")
            
            if token and api_url:
                logger.info(f"✅ TrayIcon successfully extracted:")
                logger.info(f"   🔑 Token: {token[:20]}...{token[-10:] if len(token) > 30 else ''}")
                logger.info(f"   🌐 API URL: {api_url}")
                logger.info(f"   📊 Token length: {len(token)} characters")
                
                # Store the token and API URL
                self.auth_token = token
                self.api_url = api_url
                self.is_authenticated = True
                
                # Save to configuration
                if self.config.save_auth_data(token, api_url):
                    logger.info("💾 Authentication data saved to configuration")
                else:
                    logger.error("❌ Failed to save authentication data to configuration")
                
                # Update UI
                self._update_auth_status()
                self._build_rootmenu()  # Rebuild menu to show authenticated state
                
                # Show success message
                QMessageBox.information(
                    self._parent,
                    "Authentication Success",
                    f"Successfully connected to Samay!\n\n"
                    f"API URL: {api_url}\n"
                    f"Token: {token[:20]}...{token[-10:] if len(token) > 30 else ''}"
                )
                
                logger.info("🎉 Authentication completed successfully!")
            else:
                logger.error(f"❌ Missing required parameters:")
                logger.error(f"   Token present: {bool(token)}")
                logger.error(f"   API URL present: {bool(api_url)}")
                logger.error(f"   Available params: {list(params.keys())}")
                
                QMessageBox.warning(
                    self._parent,
                    "Authentication Error",
                    "Invalid authentication URL. Missing token or API URL."
                )
        else:
            logger.error(f"❌ Invalid URL scheme. Expected 'samay://' but got: {url[:10]}...")
            
            QMessageBox.warning(
                self._parent,
                "Invalid URL",
                f"Invalid URL scheme. Expected 'samay://' but got: {url[:10]}..."
            )
    
    def _handle_login(self) -> None:
        """Handle login button click."""
        open_auth_page(self.root_url)
        # Show message about URL scheme
        QMessageBox.information(
            self._parent,
            "Authentication",
            "Please complete authentication in your browser.\n\n"
            "After logging in, you'll be redirected back to Samay automatically."
        )
    
    def _handle_logout(self) -> None:
        """Handle logout button click."""
        if logout_user(self.root_url):
            self._update_auth_status()
            QMessageBox.information(
                self._parent,
                "Logout",
                "Successfully logged out of Samay."
            )
        else:
            QMessageBox.warning(
                self._parent,
                "Logout Failed",
                "Failed to logout. Please try again."
            )

    def _build_rootmenu(self) -> None:
        menu = QMenu(self._parent)

        if self.testing:
            menu.addAction("Running in testing mode")  # .setEnabled(False)
            menu.addSeparator()

        # Authentication section
        auth_menu = menu.addMenu("Authentication")
        
        if self.is_authenticated:
            auth_menu.addAction("✓ Authenticated", lambda: None).setEnabled(False)
            auth_menu.addAction("Logout", self._handle_logout)
        else:
            auth_menu.addAction("Login", self._handle_login)
            auth_menu.addAction("Not authenticated", lambda: None).setEnabled(False)
        
        menu.addSeparator()

        # openWebUIIcon = QIcon.fromTheme("open")
        # menu.addAction("Open Dashboard", lambda: open_webui(self.root_url))
        # menu.addAction("Open API Browser", lambda: open_apibrowser(self.root_url))

        menu.addSeparator()

        modulesMenu = menu.addMenu("Modules")
        self._build_modulemenu(modulesMenu)

        menu.addSeparator()
        menu.addAction(
            "Open log folder", lambda: open_dir(aw_core.dirs.get_log_dir(None))
        )
        menu.addAction(
            "Open config folder", lambda: open_dir(aw_core.dirs.get_config_dir(None))
        )
        menu.addSeparator()

        exitIcon = QIcon.fromTheme(
            "application-exit", QIcon("media/application_exit.png")
        )
        # This check is an attempted solution to: https://github.com/ActivityWatch/activitywatch/issues/62
        # Seems to be in agreement with: https://github.com/OtterBrowser/otter-browser/issues/1313
        #   "it seems that the bug is also triggered when creating a QIcon with an invalid path"
        if exitIcon.availableSizes():
            menu.addAction(exitIcon, "Quit Samay", lambda: exit(self.manager))
        else:
            menu.addAction("Quit Samay", lambda: exit(self.manager))

        self.setContextMenu(menu)

        def show_module_failed_dialog(module: Module) -> None:
            box = QMessageBox(self._parent)
            box.setIcon(QMessageBox.Icon.Warning)
            box.setText(f"Module {module.name} quit unexpectedly")
            box.setDetailedText(module.read_log(self.testing))

            restart_button = QPushButton("Restart", box)
            restart_button.clicked.connect(module.start)
            box.addButton(restart_button, QMessageBox.ButtonRole.AcceptRole)
            box.setStandardButtons(QMessageBox.StandardButton.Cancel)

            box.show()

        def rebuild_modules_menu() -> None:
            for action in modulesMenu.actions():
                if action.isEnabled():
                    module: Module = action.data()
                    alive = module.is_alive()
                    action.setChecked(alive)
                    # print(module.text(), alive)

            # TODO: Do it in a better way, singleShot isn't pretty...
            QtCore.QTimer.singleShot(2000, rebuild_modules_menu)

        QtCore.QTimer.singleShot(2000, rebuild_modules_menu)

        def check_module_status() -> None:
            unexpected_exits = self.manager.get_unexpected_stops()
            if unexpected_exits:
                for module in unexpected_exits:
                    show_module_failed_dialog(module)
                    module.stop()

            # TODO: Do it in a better way, singleShot isn't pretty...
            QtCore.QTimer.singleShot(2000, rebuild_modules_menu)

        QtCore.QTimer.singleShot(2000, check_module_status)
        
        # Update authentication status periodically
        def update_auth_status() -> None:
            self._update_auth_status()
            # Rebuild menu to reflect auth status changes
            self._build_rootmenu()
            QtCore.QTimer.singleShot(10000, update_auth_status)  # Check every 10 seconds
        
        QtCore.QTimer.singleShot(10000, update_auth_status)

    def _build_modulemenu(self, moduleMenu: QMenu) -> None:
        moduleMenu.clear()

        def add_module_menuitem(module: Module) -> None:
            title = module.name
            ac = moduleMenu.addAction(title, lambda: module.toggle(self.testing))

            ac.setData(module)
            ac.setCheckable(True)
            ac.setChecked(module.is_alive())

        for location, modules in [
            ("bundled", self.manager.modules_bundled),
            ("system", self.manager.modules_system),
        ]:
            header = moduleMenu.addAction(location)
            header.setEnabled(False)

            for module in sorted(modules, key=lambda m: m.name):
                add_module_menuitem(module)


def exit(manager: Manager) -> None:
    # TODO: Do cleanup actions
    # TODO: Save state for resume
    print("Shutdown initiated, stopping all services...")
    manager.stop_all()
    # Terminate entire process group, just in case.
    # os.killpg(0, signal.SIGINT)

    QApplication.quit()


def run(manager: Manager, testing: bool = False) -> Any:
    logger.info("Creating trayicon...")
    # print(QIcon.themeSearchPaths())

    app = QApplication(sys.argv)

    # This is needed for the icons to get picked up with PyInstaller
    scriptdir = Path(__file__).parent

    # When run from source:
    #   __file__ is aw_qt/trayicon.py
    #   scriptdir is ./aw_qt
    #   logodir is ./media/logo
    QtCore.QDir.addSearchPath("icons", str(scriptdir.parent / "media/logo/"))

    # When run from .app:
    #   __file__ is ./Contents/MacOS/aw-qt
    #   scriptdir is ./Contents/MacOS
    #   logodir is ./Contents/Resources/aw_qt/media/logo
    QtCore.QDir.addSearchPath(
        "icons", str(scriptdir.parent.parent / "Resources/aw_qt/media/logo/")
    )

    # logger.info(f"search paths: {QtCore.QDir.searchPaths('icons')}")

    # Without this, Ctrl+C will have no effect
    signal.signal(signal.SIGINT, lambda *args: exit(manager))
    # Ensure cleanup happens on SIGTERM
    signal.signal(signal.SIGTERM, lambda *args: exit(manager))

    timer = QtCore.QTimer()
    timer.start(100)  # You may change this if you wish.
    timer.timeout.connect(lambda: None)  # Let the interpreter run each 500 ms.

    # root widget
    widget = QWidget()

    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(
            widget,
            "Systray",
            "I couldn't detect any system tray on this system. Either get one or run the Samay modules from the console.",
        )
        sys.exit(1)

    if sys.platform == "darwin":
        icon = QIcon("icons:black-monochrome-logo.png")
        # Allow macOS to use filters for changing the icon's color
        icon.setIsMask(True)
    else:
        icon = QIcon("icons:logo.png")

    trayIcon = TrayIcon(manager, icon, widget, testing=testing)
    trayIcon.show()

    QApplication.setQuitOnLastWindowClosed(False)

    logger.info("Initialized aw-qt and trayicon successfully")
    # Run the application, blocks until quit
    return app.exec()
