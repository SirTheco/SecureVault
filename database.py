"""Automatic and manual backups of the encrypted vault file."""
from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

from .database import VaultDB

PREFIX = "vault-"
SUFFIX = ".db"


def list_backups(folder: Path) -> list[Path]:
    if not folder.exists():
        return []
    return sorted(folder.glob(f"{PREFIX}*{SUFFIX}"), reverse=True)


def make_backup(db: VaultDB, folder: Path, keep: int) -> Path:
    name = datetime.now().strftime(f"{PREFIX}%Y%m%d-%H%M%S{SUFFIX}")
    dest = folder / name
    db.backup_to(dest)
    for old in list_backups(folder)[max(keep, 1):]:
        try:
            old.unlink()
        except OSError:
            pass
    return dest


def auto_backup_if_needed(db: VaultDB, folder: Path, keep: int, max_age_hours: float = 12) -> Path | None:
    """Create a backup unless a recent one already exists."""
    if not db.is_initialized():
        return None
    existing = list_backups(folder)
    if existing and time.time() - existing[0].stat().st_mtime < max_age_hours * 3600:
        return None
    return make_backup(db, folder, keep)
