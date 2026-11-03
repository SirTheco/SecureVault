"""Small helpers shared by the UI."""
from __future__ import annotations

import calendar
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def fmt_ts(ts: float | None, with_time: bool = True) -> str:
    if not ts:
        return ""
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M" if with_time else "%Y-%m-%d")


def human_size(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{n} B"


def add_month(dt: datetime) -> datetime:
    year = dt.year + dt.month // 12
    month = dt.month % 12 + 1
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


def open_path(path: Path) -> None:
    """Open a file or folder with the system's default application."""
    if sys.platform.startswith("win"):
        os.startfile(str(path))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])
