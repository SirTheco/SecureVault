"""Plain (non-secret) application settings stored as JSON."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from . import APP_NAME

DEFAULTS = {
    "theme": "System",               # System | Dark | Light appearance mode
    "palette": "Lavender",            # Lavender | Ocean | Graphite | Rose | Emerald | Sunset
    "autolock_minutes": 5,
    "lock_on_minimize": True,        # lock as soon as the window is minimised
    "lock_on_close": True,           # lock when the window is closed to the tray
    "clipboard_clear_seconds": 20,   # 0 = never clear
    "animations": True,
    "icon_motion": True,
    "sort": "recent",                # recent | name
    "auto_backup": True,
    "backups_to_keep": 10,
}
CHOICES = {
    "theme": ("System", "Dark", "Light"),
    "palette": ("Lavender", "Ocean", "Graphite", "Rose", "Emerald", "Sunset"),
    "sort": ("recent", "name"),
}
INT_RANGES = {
    "autolock_minutes": (1, 240),
    "clipboard_clear_seconds": (0, 600),
    "backups_to_keep": (1, 200),
}


def data_dir() -> Path:
    """Folder that holds vault.db, settings.json and backups/."""
    override = os.environ.get("SECUREVAULT_HOME")
    if override:
        base = Path(override)
    elif sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / APP_NAME
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / APP_NAME
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / APP_NAME
    try:
        base.mkdir(parents=True, exist_ok=True)
    except OSError:                      # read-only profile: fall back to the user's home folder
        base = Path.home() / f".{APP_NAME}"
        base.mkdir(parents=True, exist_ok=True)
    return base


class Settings:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.data = dict(DEFAULTS)
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                for key, value in loaded.items():
                    if key in DEFAULTS:
                        self.data[key] = self._clean(key, value)
        except (OSError, ValueError):
            pass

    @staticmethod
    def _clean(key: str, value):
        default = DEFAULTS[key]
        if isinstance(default, bool):
            return value if isinstance(value, bool) else default
        if isinstance(default, int):
            try:
                number = int(value)
            except (TypeError, ValueError):
                return default
            lo, hi = INT_RANGES.get(key, (0, 10**9))
            return max(lo, min(hi, number))
        if key in CHOICES:
            return value if value in CHOICES[key] else default
        return value

    def get(self, key: str):
        return self.data.get(key, DEFAULTS.get(key))

    def set(self, key: str, value) -> None:
        self.data[key] = self._clean(key, value) if key in DEFAULTS else value
        try:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, indent=2), encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError:
            pass                          # a read-only settings file must not crash the app
