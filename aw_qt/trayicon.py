import json
import logging
import os
import signal
import subprocess
import sys
import webbrowser
import requests
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse, parse_qs, unquote

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

# macOS URL scheme handling
if sys.platform == "darwin":
    try:
        import AppKit
    except ImportError:
        AppKit = None

logger = logging.getLogger(__name__)

# Import the pending buffer from main
try:
    from .main import pending_samay_url
except Exception:
    pending_samay_url = None


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
    # Use local Frontend URL for development
    auth_url = "http://localhost:3001/login"  # Local Frontend login page
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
        
        # After menu/build is ready, check for stored authentication data
        try:
            # Check for stored auth data (from QEvent.FileOpen or previous sessions)
            self._load_stored_auth_data()
            
            # Process any pending URL from QEvent.FileOpen
            global pending_samay_url
            logger.info(f"🔧 TrayIcon init - checking pending URL: {pending_samay_url}")
            if pending_samay_url:
                logger.info("🔄 Found pending samay:// URL at startup; processing now")
                self.handle_samay_url(pending_samay_url)
                pending_samay_url = None
            else:
                logger.info("ℹ️ No pending URL at startup")
        except Exception as e:
            logger.exception(f"❌ Error loading auth data at startup: {e}")

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
    
    def _load_stored_auth_data(self):
        """Load authentication data from Keychain or file storage."""
        try:
            # Try Keychain first
            try:
                import keyring
                token = keyring.get_password("net.samay.Samay", "token")
                api_url = keyring.get_password("net.samay.Samay", "target_url")
                if token and api_url:
                    logger.info("🔐 Loaded auth data from Keychain")
                    self.auth_token = token
                    self.api_url = api_url
                    self.is_authenticated = True
                    # Update config as well
                    self.config.save_auth_data(token, api_url)
                    return
            except Exception:
                pass
            
            # Fallback to file storage
            auth_file = os.path.expanduser("~/Library/Application Support/activitywatch/aw-qt/auth.json")
            if os.path.exists(auth_file):
                with open(auth_file, "r") as f:
                    auth_data = json.load(f)
                    token = auth_data.get("token")
                    api_url = auth_data.get("url")
                    if token and api_url:
                        logger.info("🔐 Loaded auth data from file storage")
                        self.auth_token = token
                        self.api_url = api_url
                        self.is_authenticated = True
                        # Update config as well
                        self.config.save_auth_data(token, api_url)
                        return
            
            logger.info("ℹ️ No stored authentication data found")
        except Exception as e:
            logger.exception(f"❌ Error loading stored auth data: {e}")

    def handle_samay_url(self, url: str):
        """Handle samay:// URL scheme events."""
        try:
            logger.info(f"🔗 Processing samay:// URL: {url}")

            parsed = urlparse(url)
            if parsed.scheme != "samay":
                logger.error(f"❌ Invalid URL scheme: {parsed.scheme}")
                return

            # Extract token and API URL
            query_params = parse_qs(parsed.query)
            token = query_params.get("token", [None])[0]
            api_url = query_params.get("url", [None])[0]

            if not token or not api_url:
                logger.error("❌ Missing token or API URL in samay:// URL")
                return

            api_url = unquote(api_url)

            # Trim logging of sensitive token
            safe_tok = token[:10] + "…" if len(token) > 10 else token
            logger.info(f"🔐 Extracted token: {safe_tok}")
            logger.info(f"🔗 Extracted API URL: {api_url}")

            # Store authentication data
            self.auth_token = token
            self.api_url = api_url
            self.is_authenticated = True

            # Persist to config
            try:
                self.config.save_auth_data(token, api_url)
            except Exception:
                logger.exception("⚠️ Failed to save auth data to config")

            # Rebuild menu to reflect auth status
            try:
                self._update_auth_status()
                self._build_rootmenu()
            except Exception:
                logger.exception("⚠️ Failed to rebuild tray menu after auth")

            # Notify user
            try:
                QMessageBox.information(
                    self._parent or None,
                    "Authentication Success",
                    f"Successfully connected to desktop!\nAPI URL: {api_url}"
                )
            except Exception:
                logger.exception("⚠️ Failed to show authentication message box")

        except Exception as e:
            logger.exception(f"❌ Error processing samay:// URL: {e}")
    
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

        # Use proper QTimer instead of recursive singleShot to prevent high CPU usage
        self.module_timer = QtCore.QTimer()
        self.module_timer.timeout.connect(lambda: self._update_modules_menu(modulesMenu, show_module_failed_dialog))
        self.module_timer.start(5000)  # Check every 5 seconds instead of 2
        
        # Update authentication status periodically
        self.auth_timer = QtCore.QTimer()
        self.auth_timer.timeout.connect(self._update_auth_status)
        self.auth_timer.start(30000)  # Check every 30 seconds instead of 10

    def _update_modules_menu(self, modulesMenu: QMenu, show_module_failed_dialog) -> None:
        """Update modules menu and check for unexpected exits."""
        for action in modulesMenu.actions():
            if action.isEnabled():
                module: Module = action.data()
                alive = module.is_alive()
                action.setChecked(alive)
        
        # Check for unexpected exits
        unexpected_exits = self.manager.get_unexpected_stops()
        if unexpected_exits:
            for module in unexpected_exits:
                show_module_failed_dialog(module)
                module.stop()

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


def run(manager: Manager, testing: bool = False, samay_url: Optional[str] = None) -> Any:
    logger.info("Creating trayicon...")
    # print(QIcon.themeSearchPaths())

    app = QApplication(sys.argv)

    # Install QEvent.FileOpen filter for URL scheme handling (no PyObjC needed!)
    if sys.platform == "darwin":
        try:
            from PyQt6.QtCore import QObject, QEvent
            import urllib.parse
            import json
            import os
            
            # Optional secure storage with keyring
            USE_KEYCHAIN = False
            try:
                import keyring
                USE_KEYCHAIN = True
                logger.info("🔐 Keyring available - will use Keychain for secure storage")
            except Exception:
                logger.info("🔐 Keyring not available - will use file-based storage")
            
            BUNDLE_ID = "net.samay.Samay"
            FALLBACK_STORE = os.path.expanduser("~/Library/Application Support/activitywatch/aw-qt/auth.json")
            
            def ensure_dir(path):
                d = os.path.dirname(path)
                if d and not os.path.exists(d):
                    os.makedirs(d, exist_ok=True)
            
            def save_token_url(token: str, target_url: str):
                if USE_KEYCHAIN:
                    keyring.set_password(BUNDLE_ID, "token", token)
                    keyring.set_password(BUNDLE_ID, "target_url", target_url)
                    logger.info("🔐 Token+URL saved to Keychain")
                else:
                    ensure_dir(FALLBACK_STORE)
                    with open(FALLBACK_STORE, "w") as f:
                        json.dump({"token": token, "url": target_url}, f)
                    logger.info(f"🔐 Token+URL saved to {FALLBACK_STORE}")
            
            def parse_and_store(raw_url: str):
                """Parse samay:// URL and store token/URL securely."""
                try:
                    parsed = urllib.parse.urlparse(raw_url)
                    if parsed.scheme != "samay":
                        return False
                    
                    # Action is in netloc part: samay://token
                    if parsed.netloc.lower() != "token":
                        return False
                    
                    qs = urllib.parse.parse_qs(parsed.query or "")
                    token = (qs.get("token") or [None])[0]
                    target_url = urllib.parse.unquote((qs.get("url") or [None])[0] or "")
                    
                    if not token or not target_url:
                        logger.error("❌ Missing token or URL in samay:// URL")
                        return False
                    
                    # Basic allowlist for security
                    if not (target_url.startswith("http://") or target_url.startswith("https://") or 
                           target_url.startswith("http://localhost") or target_url.startswith("http://127.0.0.1")):
                        logger.error(f"❌ Invalid target URL: {target_url}")
                        return False
                    
                    save_token_url(token, target_url)
                    return True
                except Exception as e:
                    logger.exception(f"❌ Error parsing/storing samay:// URL: {e}")
                    return False
            
            class UrlOpenFilter(QObject):
                def eventFilter(self, obj, event):
                    """Handle QEvent.FileOpen events from macOS for samay:// URLs."""
                    if event.type() == QEvent.Type.FileOpen:
                        url = ""
                        try:
                            if hasattr(event, "url") and event.url().isValid():
                                url = event.url().toString()
                            else:
                                # Some Qt builds pass raw string via event.file()
                                url = getattr(event, "file", lambda: "")()
                        except Exception:
                            pass
                        
                        if url and url.startswith("samay://"):
                            logger.info(f"🔗 Received samay:// URL via QEvent.FileOpen: {url}")
                            handled = parse_and_store(url)
                            if handled:
                                logger.info("✅ Successfully processed samay:// URL")
                                # Signal to TrayIcon that auth data is available
                                global pending_samay_url
                                pending_samay_url = url
                            return True  # Consume the event
                    return super().eventFilter(obj, event)
            
            # Install the event filter immediately after QApplication creation
            url_filter = UrlOpenFilter()
            app.installEventFilter(url_filter)
            logger.info("🔗 Registered QEvent.FileOpen filter for samay:// URLs")
            
            # Handle URL passed as command line argument (extra resilience)
            if len(sys.argv) > 1 and sys.argv[1].startswith("samay://"):
                logger.info(f"🔗 Processing samay:// URL from command line: {sys.argv[1]}")
                parse_and_store(sys.argv[1])
                
        except Exception as e:
            logger.exception(f"❌ Failed to register QEvent.FileOpen filter: {e}")

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
    timer.start(1000)  # Reduced frequency to 1 second to prevent high CPU usage
    timer.timeout.connect(lambda: None)  # Let the interpreter run each 1 second.

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

    # Handle samay:// URL if provided
    if samay_url:
        logger.info(f"🔗 Processing samay:// URL in trayicon: {samay_url}")
        trayIcon.handle_samay_url(samay_url)

    QApplication.setQuitOnLastWindowClosed(False)

    logger.info("Initialized aw-qt and trayicon successfully")
    # Run the application, blocks until quit
    return app.exec()
