"""
Desktop alerts for trade signals (macOS-friendly, degrades gracefully elsewhere).

When a green ▶ signal fires you usually want to step away from the terminal.
These helpers ping you so you don't have to babysit the feed:

  - sound:        play a system chime (afplay on macOS)
  - notification: banner in the macOS Notification Center (osascript)
  - speech:       speak the asset/side out loud (say on macOS)

Everything is best-effort: if a tool is missing we just skip it silently so the
dry-run loop never crashes because of an alert.
"""

from __future__ import annotations

import platform
import shutil
import subprocess
from dataclasses import dataclass

# A built-in macOS chime that exists on every install.
_MAC_SOUND = "/System/Library/Sounds/Glass.aiff"


@dataclass
class AlertConfig:
    sound: bool = True
    notification: bool = True
    speech: bool = False

    @property
    def any_enabled(self) -> bool:
        return self.sound or self.notification or self.speech


def _is_mac() -> bool:
    return platform.system() == "Darwin"


def _run(cmd: list[str]) -> None:
    """Fire-and-forget a command; never raise into the caller."""
    try:
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


def play_sound() -> None:
    if _is_mac() and shutil.which("afplay"):
        _run(["afplay", _MAC_SOUND])
    else:
        # Terminal bell as a universal fallback.
        print("\a", end="", flush=True)


def show_notification(title: str, message: str) -> None:
    if _is_mac() and shutil.which("osascript"):
        safe_msg = message.replace('"', "'")
        safe_title = title.replace('"', "'")
        script = (
            f'display notification "{safe_msg}" '
            f'with title "{safe_title}" sound name "Glass"'
        )
        _run(["osascript", "-e", script])


def speak(text: str) -> None:
    if _is_mac() and shutil.which("say"):
        _run(["say", text])


def fire(config: AlertConfig, title: str, message: str, spoken: str = "") -> None:
    """Trigger every enabled alert channel for one signal."""
    if not config.any_enabled:
        return
    if config.sound:
        play_sound()
    if config.notification:
        show_notification(title, message)
    if config.speech and spoken:
        speak(spoken)


def alert_for_signal(
    config: AlertConfig,
    *,
    asset: str,
    strategy: str,
    message: str,
    platform: str = "poly",
) -> None:
    """Chime/notify/speak for a dry-run trade signal (markov or hedged)."""
    if "WOULD BUY YES" in message or "BUY YES" in message:
        spoken_side = "Yes"
    elif strategy == "hedged" or "WOULD HEDGE" in message:
        spoken_side = "hedge"
    else:
        spoken_side = "trade"
    fire(
        config,
        title=f"{platform} signal: {asset} {strategy}",
        message=message,
        spoken=f"{strategy} signal on {asset}, {spoken_side}",
    )
