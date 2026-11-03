"""System-tray icon + desktop notifications (optional; the app works without it)."""
from __future__ import annotations

import queue

try:  # pystray can raise more than ImportError when no tray backend exists
    import pystray
    from .icon import make_icon
except Exception:  # noqa: BLE001
    pystray = None


class Tray:
    def __init__(self, events: queue.Queue):
        self.events = events
        self.icon = None
        self.available = False

    def start(self) -> None:
        if pystray is None:
            return
        try:
            menu = pystray.Menu(
                pystray.MenuItem("Open SecureVault", lambda: self.events.put("open"), default=True),
                pystray.MenuItem("Lock", lambda: self.events.put("lock")),
                pystray.MenuItem("Quit", lambda: self.events.put("quit")),
            )
            self.icon = pystray.Icon("SecureVault", make_icon(64), "SecureVault", menu)
            self.icon.run_detached()
            self.available = True
        except Exception:  # noqa: BLE001
            self.icon = None
            self.available = False

    def notify(self, message: str, title: str = "SecureVault") -> None:
        if self.available and self.icon is not None:
            try:
                self.icon.notify(message, title)
            except Exception:  # noqa: BLE001
                pass

    def stop(self) -> None:
        if self.icon is not None:
            try:
                self.icon.stop()
            except Exception:  # noqa: BLE001
                pass
