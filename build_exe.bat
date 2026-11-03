"""Allow only one SecureVault window per data folder; a second launch just wakes the first one."""
from __future__ import annotations

import socket
import sys
import threading
import zlib

MAGIC_OPEN = b"securevault-open"
MAGIC_QUIT = b"securevault-quit"


class SingleInstance:
    def __init__(self, key: str):
        self.port = 20000 + zlib.crc32(key.encode("utf-8")) % 20000
        self.sock: socket.socket | None = None

    def acquire(self) -> bool:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if sys.platform.startswith("win") and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            s.bind(("127.0.0.1", self.port))
            s.listen(4)
        except OSError:
            s.close()
            return False
        self.sock = s
        return True

    def notify_existing(self, command: str = "open") -> bool:
        """Send "open" (bring to front) or "quit" to the running instance. True if one answered."""
        try:
            with socket.create_connection(("127.0.0.1", self.port), timeout=1.5) as c:
                c.sendall(MAGIC_QUIT if command == "quit" else MAGIC_OPEN)
            return True
        except OSError:
            return False

    def serve(self, callback) -> None:
        def loop():
            while self.sock is not None:
                try:
                    conn, _addr = self.sock.accept()
                except OSError:
                    return
                try:
                    conn.settimeout(1.0)
                    data = conn.recv(32)
                    if data.startswith(MAGIC_QUIT):
                        callback("quit")
                    elif data.startswith(MAGIC_OPEN):
                        callback("open")
                except OSError:
                    pass
                finally:
                    conn.close()
        threading.Thread(target=loop, daemon=True).start()

    def close(self) -> None:
        s, self.sock = self.sock, None
        if s is not None:
            try:
                s.close()
            except OSError:
                pass
