"""Encrypted vault storage on top of SQLite.

Everything sensitive (titles, passwords, notes, attachment names and bytes) is
encrypted with AES-256-GCM before it is written. The only plain-text columns
are structural: item kind, timestamps, and the due time of reminders (needed so
a "reminder is due" notification can appear while the vault is locked).
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from . import crypto
from .crypto import DecryptionError

KINDS = ("account", "note", "study", "reminder")
MAX_ATTACHMENT_BYTES = 50 * 1024 * 1024
TRASH_DAYS = 30

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS items (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    kind       TEXT NOT NULL,
    blob       BLOB NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    deleted_at REAL,
    due_at     REAL
);
CREATE TABLE IF NOT EXISTS attachments (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id    INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    meta       BLOB NOT NULL,
    data       BLOB NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_items_deleted ON items(deleted_at);
CREATE INDEX IF NOT EXISTS idx_att_item ON attachments(item_id);
"""


@dataclass
class Item:
    id: int
    kind: str
    data: dict
    created_at: float
    updated_at: float
    deleted_at: float | None
    due_at: float | None

    @property
    def title(self) -> str:
        return self.data.get("title") or "(untitled)"


class VaultDB:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self._dek: bytes | None = None
        self.unreadable = 0
        self._open()

    # ------------------------------------------------------------ connection
    def _open(self) -> None:
        self.conn = sqlite3.connect(self.path)
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA secure_delete = ON")   # overwrite deleted rows instead of leaving them in the file
        self.conn.execute("PRAGMA synchronous = FULL")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def _get_meta(self, key: str) -> str | None:
        row = self.conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row[0] if row else None

    def _set_meta(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO meta(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )

    # ------------------------------------------------------------ vault keys
    def is_initialized(self) -> bool:
        return self._get_meta("wrapped_master") is not None

    @property
    def unlocked(self) -> bool:
        return self._dek is not None

    def _require_key(self) -> bytes:
        if self._dek is None:
            raise RuntimeError("The vault is locked.")
        return self._dek

    def _wrap_master(self, dek: bytes, password: str) -> None:
        salt = os.urandom(16)
        params = dict(crypto.SCRYPT_PARAMS)
        kek = crypto.derive_key(password.encode("utf-8"), salt, params)
        self._set_meta("kdf", json.dumps({**params, "salt": crypto.b64e(salt)}))
        self._set_meta("wrapped_master", crypto.b64e(crypto.encrypt(kek, dek, b"dek-master")))

    def _wrap_recovery(self, dek: bytes) -> str:
        raw, text = crypto.new_recovery_key()
        kek = crypto.recovery_to_key(raw)
        self._set_meta("wrapped_recovery", crypto.b64e(crypto.encrypt(kek, dek, b"dek-recovery")))
        return text

    def create(self, master_password: str) -> str:
        """Initialise a new vault. Returns the recovery key text."""
        if self.is_initialized():
            raise RuntimeError("Vault already exists.")
        dek = crypto.new_key()
        self._wrap_master(dek, master_password)
        recovery = self._wrap_recovery(dek)
        self.conn.commit()
        self._dek = dek
        return recovery

    def _unwrap_master(self, password: str) -> bytes | None:
        kdf = json.loads(self._get_meta("kdf") or "{}")
        kek = crypto.derive_key(password.encode("utf-8"), crypto.b64d(kdf["salt"]), kdf)
        try:
            return crypto.decrypt(kek, crypto.b64d(self._get_meta("wrapped_master")), b"dek-master")
        except DecryptionError:
            return None

    def prepare_unlock(self, master_password: str):
        """Return a function doing the slow key derivation. It touches no SQLite objects, so it may run in a thread."""
        kdf = json.loads(self._get_meta("kdf") or "{}")
        wrapped = crypto.b64d(self._get_meta("wrapped_master"))
        secret = master_password.encode("utf-8")

        def work() -> bytes | None:
            kek = crypto.derive_key(secret, crypto.b64d(kdf["salt"]), kdf)
            try:
                return crypto.decrypt(kek, wrapped, b"dek-master")
            except DecryptionError:
                return None

        return work

    def finish_unlock(self, dek: bytes) -> None:
        self._dek = dek

    def unlock(self, master_password: str) -> bool:
        dek = self._unwrap_master(master_password)
        if dek is None:
            return False
        self._dek = dek
        return True

    def verify_master(self, master_password: str) -> bool:
        return self._unwrap_master(master_password) is not None

    def unlock_with_recovery(self, recovery_text: str, new_password: str) -> bool:
        """Unlock with the recovery key and immediately set a new master password."""
        try:
            kek = crypto.recovery_to_key(crypto.parse_recovery_key(recovery_text))
            dek = crypto.decrypt(kek, crypto.b64d(self._get_meta("wrapped_recovery")), b"dek-recovery")
        except DecryptionError:
            return False
        self._wrap_master(dek, new_password)
        self.conn.commit()
        self._dek = dek
        return True

    def change_master_password(self, current: str, new: str) -> bool:
        dek = self._unwrap_master(current)
        if dek is None:
            return False
        self._wrap_master(dek, new)
        self.conn.commit()
        return True

    def rotate_recovery_key(self) -> str:
        recovery = self._wrap_recovery(self._require_key())
        self.conn.commit()
        return recovery

    def lock(self) -> None:
        self._dek = None

    # ----------------------------------------------------------------- items
    def _enc_item(self, data: dict) -> bytes:
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        return crypto.encrypt(self._require_key(), payload, b"item")

    def _row_to_item(self, row) -> Item:
        id_, kind, blob, created, updated, deleted, due = row
        data = json.loads(crypto.decrypt(self._require_key(), blob, b"item"))
        return Item(id_, kind, data, created, updated, deleted, due)

    def add_item(self, kind: str, data: dict, due_at: float | None = None) -> int:
        if kind not in KINDS:
            raise ValueError(f"Unknown item kind: {kind}")
        now = time.time()
        cur = self.conn.execute(
            "INSERT INTO items(kind,blob,created_at,updated_at,due_at) VALUES(?,?,?,?,?)",
            (kind, self._enc_item(data), now, now, due_at),
        )
        self.conn.commit()
        return cur.lastrowid

    def update_item(self, item_id: int, data: dict, due_at: float | None = None) -> None:
        self.conn.execute(
            "UPDATE items SET blob=?, updated_at=?, due_at=? WHERE id=?",
            (self._enc_item(data), time.time(), due_at, item_id),
        )
        self.conn.commit()

    def get_items(self, trashed: bool = False, kind: str | None = None) -> list[Item]:
        """All items. A damaged row is skipped (and counted in `unreadable`) instead of breaking the whole vault."""
        cond = "deleted_at IS NOT NULL" if trashed else "deleted_at IS NULL"
        args: tuple = ()
        if kind:
            cond += " AND kind = ?"
            args = (kind,)
        rows = self.conn.execute(
            "SELECT id,kind,blob,created_at,updated_at,deleted_at,due_at "
            f"FROM items WHERE {cond} ORDER BY updated_at DESC", args
        ).fetchall()
        items, self.unreadable = [], 0
        for row in rows:
            try:
                items.append(self._row_to_item(row))
            except (DecryptionError, ValueError, KeyError):
                self.unreadable += 1
        return items

    def trash_item(self, item_id: int) -> None:
        self.conn.execute("UPDATE items SET deleted_at=? WHERE id=?", (time.time(), item_id))
        self.conn.commit()

    def restore_item(self, item_id: int) -> None:
        self.conn.execute("UPDATE items SET deleted_at=NULL, updated_at=? WHERE id=?", (time.time(), item_id))
        self.conn.commit()

    def delete_forever(self, item_id: int) -> None:
        self.conn.execute("DELETE FROM items WHERE id=?", (item_id,))
        self.conn.commit()

    def empty_trash(self) -> None:
        self.conn.execute("DELETE FROM items WHERE deleted_at IS NOT NULL")
        self.conn.commit()

    def purge_old_trash(self, days: int = TRASH_DAYS) -> None:
        self.conn.execute(
            "DELETE FROM items WHERE deleted_at IS NOT NULL AND deleted_at < ?",
            (time.time() - days * 86400,),
        )
        self.conn.commit()

    def due_reminders(self, now: float) -> list[tuple[int, float]]:
        """(id, due_at) of reminders that are due. Works while locked (plain columns)."""
        return self.conn.execute(
            "SELECT id, due_at FROM items WHERE kind='reminder' AND deleted_at IS NULL "
            "AND due_at IS NOT NULL AND due_at <= ?",
            (now,),
        ).fetchall()

    # ----------------------------------------------------------- attachments
    def add_attachment(self, item_id: int, file_path: Path | str) -> int:
        path = Path(file_path)
        size = path.stat().st_size
        if size > MAX_ATTACHMENT_BYTES:
            raise ValueError("File is too large (limit is 50 MB).")
        key = self._require_key()
        meta = json.dumps({"name": path.name, "size": size}).encode("utf-8")
        cur = self.conn.execute(
            "INSERT INTO attachments(item_id,meta,data,created_at) VALUES(?,?,?,?)",
            (
                item_id,
                crypto.encrypt(key, meta, b"att-meta"),
                crypto.encrypt(key, path.read_bytes(), b"att-data"),
                time.time(),
            ),
        )
        self.conn.commit()
        return cur.lastrowid

    def list_attachments(self, item_id: int) -> list[dict]:
        key = self._require_key()
        out = []
        for att_id, meta in self.conn.execute(
            "SELECT id, meta FROM attachments WHERE item_id=? ORDER BY id", (item_id,)
        ):
            try:
                info = json.loads(crypto.decrypt(key, meta, b"att-meta"))
            except (DecryptionError, ValueError):
                continue
            out.append({"id": att_id, "name": info["name"], "size": info["size"]})
        return out

    def export_attachment(self, att_id: int, dest: Path | str) -> None:
        row = self.conn.execute("SELECT data FROM attachments WHERE id=?", (att_id,)).fetchone()
        if row is None:
            raise KeyError(att_id)
        Path(dest).write_bytes(crypto.decrypt(self._require_key(), row[0], b"att-data"))

    def delete_attachment(self, att_id: int) -> None:
        self.conn.execute("DELETE FROM attachments WHERE id=?", (att_id,))
        self.conn.commit()

    # --------------------------------------------------------------- backups
    def backup_to(self, dest: Path | str) -> None:
        """Consistent copy of the (already encrypted) database file."""
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        target = sqlite3.connect(dest)
        try:
            with target:
                self.conn.backup(target)
        finally:
            target.close()

    @staticmethod
    def is_valid_vault_file(path: Path | str) -> bool:
        """True if `path` looks like a SecureVault database (so a random .db can never replace the vault)."""
        try:
            con = sqlite3.connect(f"file:{Path(path).as_posix()}?mode=ro", uri=True)
            try:
                have = {r[0] for r in con.execute("SELECT key FROM meta")}
                con.execute("SELECT COUNT(*) FROM items").fetchone()
            finally:
                con.close()
            return {"wrapped_master", "wrapped_recovery", "kdf"} <= have
        except sqlite3.Error:
            return False

    def integrity_ok(self) -> bool:
        try:
            return self.conn.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        except sqlite3.Error:
            return False

    def replace_with(self, backup_path: Path | str) -> Path:
        """Restore a backup over the live database. Returns the safety copy path."""
        if not self.is_valid_vault_file(backup_path):
            raise ValueError("That file is not a SecureVault backup.")
        self.lock()
        self.conn.close()
        stamp = time.strftime("%Y%m%d-%H%M%S")
        safety = self.path.with_name(f"{self.path.stem}.before-restore-{stamp}{self.path.suffix}")
        try:
            shutil.copy2(self.path, safety)
            shutil.copy2(backup_path, self.path)
        finally:
            self._open()          # the app must never be left without a database connection
        return safety
