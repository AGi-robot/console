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
MINT = (88, 199, 126)  # greener mint, #58C77E
RESTING_MINT = MINT  # Mint is reserved for offline resting.
PLUM = (184, 70, 105)  # Deeper, more saturated chamber rose
DARK_ROSE = (104, 45, 63)  # Deep rose for the online baseline
BRIGHTNESS = {
    "resting": 0.50,
    "waiting": 0.50,
    "thinking": 0.75,
    "responding": 0.75,
    "working": 0.75,
}
FULL_CYCLE_SECONDS = {"waiting": 1.0, "thinking": 0.4, "responding": 0.4, "working": 0.4}
UPDATE_INTERVAL_SECONDS = 0.033
PULSE_ATTACK_FRACTION = 0.15
PULSE_RELEASE_FRACTION = 0.35
ACTIVE_PULSE_ATTACK_FRACTION = 0.10
ACTIVE_PULSE_RELEASE_FRACTION = 0.20
BASE_ROSE_BRIGHTNESS = 0.50
WAITING_ROSE_BRIGHTNESS = 0.68


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
        self._state_started = time.monotonic()
        self._animation_stop = threading.Event()
        self._animation_thread: threading.Thread | None = None
        self._last_color: tuple[int, int, int] | None = None

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
        self._animation_stop.clear()
        self._animation_thread = threading.Thread(
            target=self._animate, name="grace-openrgb-animation", daemon=True
        )
        self._animation_thread.start()

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
        self._last_color = None

    @staticmethod
    def brightness_for_state(state: str) -> float:
        """Keep the established baseline brightness for each Grace activity state."""
        return BRIGHTNESS[state]

    @staticmethod
    def color_for_state(state: str) -> tuple[int, int, int]:
        """Return resting mint or the dark rose online baseline."""
        if state == "resting":
            source = RESTING_MINT
            target_peak = round(255 * BRIGHTNESS[state])
        else:
            source = DARK_ROSE
            target_peak = round(255 * BASE_ROSE_BRIGHTNESS)
        source_peak = max(source)
        return tuple(round(channel * target_peak / source_peak) for channel in source)

    @staticmethod
    def _active_pulse_color(amount: float, state: str) -> tuple[int, int, int]:
        """Pulse active states from dark rose to a vivid chamber-rose light."""
        mixed = tuple(round(start + (end - start) * amount)
                      for start, end in zip(DARK_ROSE, PLUM))
        base_peak = round(255 * BASE_ROSE_BRIGHTNESS)
        active_peak = round(255 * BRIGHTNESS[state])
        target_peak = round(base_peak + (active_peak - base_peak) * amount)
        source_peak = max(mixed)
        return tuple(round(channel * target_peak / source_peak) for channel in mixed)

    @staticmethod
    def _waiting_pulse_color(amount: float) -> tuple[int, int, int]:
        """Give online waiting a soft rose beat over its dark-rose baseline."""
        mixed = tuple(round(start + (end - start) * amount)
                      for start, end in zip(DARK_ROSE, PLUM))
        base_peak = round(255 * BASE_ROSE_BRIGHTNESS)
        rose_peak = round(255 * WAITING_ROSE_BRIGHTNESS)
        target_peak = round(base_peak + (rose_peak - base_peak) * amount)
        source_peak = max(mixed)
        return tuple(round(channel * target_peak / source_peak) for channel in mixed)

    @staticmethod
    def _pulse_amount(
        phase_seconds: float,
        cycle_seconds: float,
        attack_fraction: float = PULSE_ATTACK_FRACTION,
        release_fraction: float = PULSE_RELEASE_FRACTION,
    ) -> float:
        """Return a smooth rose beat followed by the state's resting interval."""
        attack = cycle_seconds * attack_fraction
        release = cycle_seconds * release_fraction

        def smoothstep(value: float) -> float:
            value = min(1.0, max(0.0, value))
            return value * value * (3.0 - 2.0 * value)

        if phase_seconds < attack:
            return smoothstep(phase_seconds / attack)
        if phase_seconds < attack + release:
            return 1.0 - smoothstep((phase_seconds - attack) / release)
        return 0.0

    def _apply_color(self, color: tuple[int, int, int]) -> None:
        with self._lock:
            try:
                if self.client is None or self.device is None:
                    if not self._server_available() or not self._connect():
                        return
                if color == self._last_color:
                    return
                self.device.set_color(self._color_class(*color))
                self._last_color = color
            except Exception as error:
                LOGGER.warning("Could not update OpenRGB lighting: %s", error)
                self._disconnect()

    def _animate(self) -> None:
        while not self._animation_stop.is_set():
            state = self.state
            if self._animation_stop.wait(UPDATE_INTERVAL_SECONDS):
                break
            state = self.state
            if state is None:
                continue
            if state == "resting":
                # set_state already applied mint; avoid repeated static writes.
                continue
            cycle = FULL_CYCLE_SECONDS[state]
            phase_seconds = (time.monotonic() - self._state_started) % cycle
            # Every online state stays in the rose palette. Waiting pulses at
            # 60 BPM; active states pulse faster and brighter at 150 BPM.
            if state == "waiting":
                amount = self._pulse_amount(phase_seconds, cycle)
                color = self._waiting_pulse_color(amount)
            else:
                amount = self._pulse_amount(
                    phase_seconds,
                    cycle,
                    ACTIVE_PULSE_ATTACK_FRACTION,
                    ACTIVE_PULSE_RELEASE_FRACTION,
                )
                color = self._active_pulse_color(amount, state)
            self._apply_color(color)

    def set_state(self, state: str) -> None:
        if not self._enabled():
            return
        if state not in BRIGHTNESS:
            return
        if state != self.state:
            self.state = state
            self._state_started = time.monotonic()
            self.brightness = self.brightness_for_state(state)
            # Offline rests in mint; every online transition starts in dark rose.
            self._apply_color(self.color_for_state(state))

    def stop(self) -> None:
        self._animation_stop.set()
        if self._animation_thread is not None:
            self._animation_thread.join(timeout=2)
            self._animation_thread = None
        # AIVA can stop while Grace is active. Leave the board at its offline mint
        # instead of freezing at an arbitrary point in the animation.
        if self.client is not None and self.device is not None:
            self._apply_color(self.color_for_state("resting"))
        self._disconnect()
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()

