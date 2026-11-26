"""Optional local OpenRGB bridge for Grace's activity lighting."""
from __future__ import annotations

import logging
import os
import socket
import subprocess
import threading
import time
from pathlib import Path
from dataclasses import asdict

from .lighting import LightingEffect

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
        self._scene_lock = threading.RLock()
        self._effect: LightingEffect | None = None
        self._effect_started = 0.0
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

    @staticmethod
    def activity_defaults() -> dict:
        """Expose the exact existing activity renderer settings, not approximated effects."""
        return {"resting_color": RESTING_MINT, "online_base_color": DARK_ROSE,
                "online_pulse_color": PLUM, "brightness": dict(BRIGHTNESS),
                "cycle_seconds": dict(FULL_CYCLE_SECONDS),
                "base_brightness": BASE_ROSE_BRIGHTNESS,
                "waiting_peak_brightness": WAITING_ROSE_BRIGHTNESS,
                "waiting_attack_release": [PULSE_ATTACK_FRACTION, PULSE_RELEASE_FRACTION],
                "active_attack_release": [ACTIVE_PULSE_ATTACK_FRACTION, ACTIVE_PULSE_RELEASE_FRACTION]}

    def set_effect(self, effect: LightingEffect) -> dict:
        with self._scene_lock:
            if not self._enabled() or self._animation_thread is None or not self._animation_thread.is_alive():
                raise RuntimeError("OpenRGB lighting is disabled or unavailable")
            self._effect = effect
            self._effect_started = time.monotonic()
            self._apply_color(effect.color_at(0))
            LOGGER.info("Grace lighting effect: %s", effect)
            return self.effect_status()

    def effect_status(self) -> dict:
        with self._scene_lock:
            effect = self._effect
            remaining = (max(0, effect.duration_seconds - (time.monotonic() - self._effect_started))
                         if effect and effect.duration_seconds is not None else None)
            details = {k: v for k, v in asdict(effect).items() if not k.startswith('_')} if effect else None
            return {"active": bool(effect and (remaining is None or remaining > 0)), "effect": details,
                    "remaining_seconds": remaining, "connected": self.device is not None,
                    "activity_state": self.state,
                    "morse_message_seconds": len(effect._morse) * effect.morse_unit_seconds if effect and effect.rhythm == 'morse' else None}

    def clear_effect(self) -> dict:
        with self._scene_lock:
            self._effect = None
            if self.state is not None:
                self._apply_color(self.color_for_state(self.state))
            return self.effect_status()

    def _animate(self) -> None:
        while not self._animation_stop.wait(UPDATE_INTERVAL_SECONDS):
            with self._scene_lock:
                now = time.monotonic()
                if self._effect is not None:
                    elapsed = now - self._effect_started
                    if self._effect.duration_seconds is None or elapsed < self._effect.duration_seconds:
                        self._apply_color(self._effect.color_at(elapsed))
                        continue
                    self.clear_effect()
                state = self.state
                if state is None or state == "resting":
                    continue
                cycle = FULL_CYCLE_SECONDS[state]
                phase_seconds = (now - self._state_started) % cycle
                if state == "waiting":
                    amount = self._pulse_amount(phase_seconds, cycle)
                    color = self._waiting_pulse_color(amount)
                else:
                    amount = self._pulse_amount(phase_seconds, cycle,
                                               ACTIVE_PULSE_ATTACK_FRACTION,
                                               ACTIVE_PULSE_RELEASE_FRACTION)
                    color = self._active_pulse_color(amount, state)
                self._apply_color(color)

    def set_state(self, state: str) -> None:
        if not self._enabled() or state not in BRIGHTNESS:
            return
        with self._scene_lock:
            if state != self.state:
                self.state = state
                self._state_started = time.monotonic()
                self.brightness = self.brightness_for_state(state)
                if self._effect is None:
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
        self._effect = None
        self._disconnect()
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()

