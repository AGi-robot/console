"""Optional local OpenRGB bridge for Grace's activity lighting."""
from __future__ import annotations

import logging
import os
import socket
import subprocess
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
    "resting": "0A1007",
}


class OpenRgb:
    """Start OpenRGB's loopback SDK server and set the motherboard's static color."""

    def __init__(self, executable: str | None = None) -> None:
        default = Path.home() / "openrgb" / "OpenRGB_1.0rc2_x86_64_0fca93e.AppImage"
        self.executable = Path(executable or os.getenv("AGI_OPENRGB_APPIMAGE", default))
        self.process: subprocess.Popen | None = None
        self.state: str | None = None

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
        self.set_state("resting")

    def set_state(self, state: str) -> None:
        if not self._enabled():
            return
        color = COLORS.get(state)
        if color is None or state == self.state:
            return
        if not self._server_available():
            LOGGER.debug("OpenRGB SDK server is unavailable")
            return
        try:
            result = subprocess.run(
                [str(self.executable), "--client", f"{SDK_HOST}:{SDK_PORT}",
                 "--device", DEVICE, "--mode", "Static", "--color", color],
                check=False, capture_output=True, text=True, timeout=12,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            LOGGER.warning("Could not update OpenRGB lighting: %s", error)
            return
        if result.returncode:
            LOGGER.warning("OpenRGB lighting update failed: %s", result.stderr.strip())
            return
        self.state = state

    def stop(self) -> None:
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()

