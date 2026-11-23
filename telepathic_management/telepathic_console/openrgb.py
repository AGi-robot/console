"""Optional local OpenRGB bridge for Grace's activity lighting."""
from __future__ import annotations

import logging
import os
import socket
import subprocess
import threading
import time
from pathlib import Path

LOGGER = logging.getLogger(__name__)
SDK_HOST = "127.0.0.1"
SDK_PORT = 6742
DEVICE = "MSI Z790 GAMING PLUS WIFI"
COLORS = {
    "thinking": "72D65A",
    "responding": "72D65A",
    "working": "72D65A",
    "waiting": "355E2F",
    "resting": "142015",
}
BRIGHTNESS = {
    "resting": 0.25,
    "waiting": 0.50,
    "thinking": 0.75,
    "responding": 0.75,
    "working": 0.75,
}


class OpenRgb:
    """Start OpenRGB's loopback server and keep one Python SDK client connected."""

    def __init__(self, executable: str | None = None) -> None:
        default = Path.home() / "openrgb" / "OpenRGB_1.0rc2_x86_64_0fca93e.AppImage"
        self.executable = Path(executable or os.getenv("AGI_OPENRGB_APPIMAGE", default))
        self.process: subprocess.Popen | None = None
        self.client = None
        self.device = None
        self.state: str | None = None
        self.brightness = BRIGHTNESS["resting"]
        self._lock = threading.Lock()

    @staticmethod
    def _enabled() -> bool:
        return os.getenv("AGI_OPENRGB_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _server_available() -> bool:
        try:
            with socket.create_connection((SDK_HOST, SDK_PORT), timeout=0.25):
                return True
        except OSError:
            return False

    def start(self) -> None:
        if not self._enabled():
            return
        try:
            from openrgb import OpenRGBClient
            from openrgb.utils import RGBColor
        except ImportError:
            LOGGER.warning("openrgb-python is unavailable; RGB activity sync is disabled")
            return
        self._client_class = OpenRGBClient
        self._color_class = RGBColor
        if not self.executable.is_file() or not os.access(self.executable, os.X_OK):
            LOGGER.info("OpenRGB AppImage not found; RGB activity sync is disabled")
            return
        if not self._server_available():
            self.process = subprocess.Popen(
                [str(self.executable), "--server", "--server-host", SDK_HOST,
                 "--server-port", str(SDK_PORT), "--loglevel", "warning"],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, start_new_session=True,
            )
            for _ in range(40):
                if self._server_available():
                    break
                if self.process.poll() is not None:
                    LOGGER.warning("OpenRGB SDK server exited during startup")
                    return
                time.sleep(0.25)
            else:
                LOGGER.warning("OpenRGB SDK server did not become available")
                return
        if not self._connect():
            return
        self.set_state("resting")

    def _connect(self) -> bool:
        try:
            self.client = self._client_class(
                address=SDK_HOST,
                port=SDK_PORT,
                name="Grace activity lighting",
                protocol_version=4,
            )
            devices = self.client.get_devices_by_name(DEVICE, exact=False)
            if not devices:
                LOGGER.warning("OpenRGB did not report the configured motherboard: %s", DEVICE)
                self.client.disconnect()
                self.client = None
                return False
            self.device = devices[0]
            self.device.set_mode("Static")
            return True
        except Exception as error:
            LOGGER.warning("Could not connect the OpenRGB Python SDK client: %s", error)
            self._disconnect()
            return False

    def _disconnect(self) -> None:
        if self.client is not None:
            try:
                self.client.disconnect()
            except Exception:
                pass
        self.client = None
        self.device = None

    @staticmethod
    def brightness_for_state(state: str) -> float:
        """Set a steady brightness for each Grace activity state."""
        return BRIGHTNESS[state]

    def set_state(self, state: str) -> None:
        if not self._enabled():
            return
        color = COLORS.get(state)
        if color is None:
            return
        brightness = self.brightness_for_state(state)
        if state == self.state and abs(brightness - self.brightness) < 0.01:
            return
        with self._lock:
            try:
                if self.client is None or self.device is None:
                    if not self._server_available() or not self._connect():
                        return
                red, green, blue = (
                    round(int(color[index:index + 2], 16) * brightness)
                    for index in (0, 2, 4)
                )
                self.device.set_color(self._color_class(red, green, blue))
                self.state = state
                self.brightness = brightness
            except Exception as error:
                LOGGER.warning("Could not update OpenRGB lighting: %s", error)
                self._disconnect()

    def stop(self) -> None:
        self._disconnect()
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()

