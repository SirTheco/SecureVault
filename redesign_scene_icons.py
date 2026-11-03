"""Run with:  python -m unittest discover -s tests -v"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from vault import crypto  # noqa: E402
from vault.backup import auto_backup_if_needed, list_backups, make_backup  # noqa: E402
from vault.database import VaultDB  # noqa: E402
from vault.passwords import generate_password, strength  # noqa: E402

crypto.SCRYPT_PARAMS["n"] = 2**10  # fast tests only; the app uses 2**17


class CryptoTests(unittest.TestCase):
    def test_roundtrip_and_tamper(self):
        key = crypto.new_key()
        blob = crypto.encrypt(key, b"hello", b"x")
        self.assertEqual(crypto.decrypt(key, blob, b"x"), b"hello")
        with self.assertRaises(crypto.DecryptionError):
            crypto.decrypt(key, blob, b"other-aad")
        with self.assertRaises(crypto.DecryptionError):
            crypto.decrypt(crypto.new_key(), blob, b"x")
        tampered = blob[:-1] + bytes([blob[-1] ^ 1])
        with self.assertRaises(crypto.DecryptionError):
            crypto.decrypt(key, tampered, b"x")

    def test_recovery_key_format(self):
        raw, text = crypto.new_recovery_key()
        self.assertEqual(crypto.parse_recovery_key(text.lower().replace("-", " ")), raw)
        with self.assertRaises(crypto.DecryptionError):
            crypto.parse_recovery_key("NOT-A-KEY")


class PasswordTests(unittest.TestCase):
    def test_generator(self):
        pw = generate_password(20, symbols=False, avoid_ambiguous=True)
        self.assertEqual(len(pw), 20)
        self.assertFalse(any(c in "O0oIl1|" for c in pw))
        self.assertTrue(any(c.isdigit() for c in pw) and any(c.isupper() for c in pw))

    def test_strength_order(self):
        self.assertLess(strength("password")[2], strength("Tr0ub4dor&3xtra")[2])
        self.assertEqual(strength("password")[0], 0)
        self.assertGreaterEqual(strength(generate_password(24))[0], 3)


class VaultTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "vault.db"
        self.db = VaultDB(self.path)

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def test_unlock_flow_and_recovery(self):
        self.assertFalse(self.db.is_initialized())
        recovery = self.db.create("correct horse battery")
        self.db.lock()
        self.assertFalse(self.db.unlock("wrong password"))
        self.assertTrue(self.db.unlock("correct horse battery"))
        item_id = self.db.add_item("note", {"title": "n1"})
        self.db.lock()
        self.assertTrue(self.db.unlock_with_recovery(recovery, "brand new password"))
        self.assertEqual(self.db.get_items()[0].id, item_id)
        self.db.lock()
        self.assertFalse(self.db.unlock("correct horse battery"))
        self.assertTrue(self.db.unlock("brand new password"))

    def test_change_password_and_rotate_recovery(self):
        recovery = self.db.create("first password!")
        self.assertFalse(self.db.change_master_password("nope", "x"))
        self.assertTrue(self.db.change_master_password("first password!", "second password!"))
        new_recovery = self.db.rotate_recovery_key()
        self.db.lock()
        self.assertTrue(self.db.unlock("second password!"))
        self.db.lock()
        self.assertFalse(self.db.unlock_with_recovery(recovery, "zzzzzzzzzzzz"))
        self.assertTrue(self.db.unlock_with_recovery(new_recovery, "third password!"))

    def test_data_is_encrypted_on_disk(self):
        self.db.create("a long master password")
        self.db.add_item("account", {"title": "SecretSiteName", "password": "hunter2-unique"})
        self.db.conn.commit()
        raw = self.path.read_bytes()
        self.assertNotIn(b"SecretSiteName", raw)
        self.assertNotIn(b"hunter2-unique", raw)

    def test_items_trash_and_due(self):
        self.db.create("a long master password")
        a = self.db.add_item("account", {"title": "A"})
        r = self.db.add_item("reminder", {"title": "R"}, due_at=100.0)
        self.assertEqual([i for i, _ in self.db.due_reminders(200.0)], [r])
        self.assertEqual(self.db.due_reminders(50.0), [])
        self.db.update_item(a, {"title": "A2"})
        self.assertEqual({i.title for i in self.db.get_items()}, {"A2", "R"})
        self.db.trash_item(a)
        self.assertEqual([i.id for i in self.db.get_items(trashed=True)], [a])
        self.db.restore_item(a)
        self.db.trash_item(a)
        self.db.empty_trash()
        self.assertEqual(self.db.get_items(trashed=True), [])

    def test_attachments(self):
        self.db.create("a long master password")
        item = self.db.add_item("note", {"title": "with file"})
        src = Path(self.tmp.name) / "doc.bin"
        payload = os.urandom(5000)
        src.write_bytes(payload)
        att = self.db.add_attachment(item, src)
        info = self.db.list_attachments(item)
        self.assertEqual(info, [{"id": att, "name": "doc.bin", "size": 5000}])
        out = Path(self.tmp.name) / "out.bin"
        self.db.export_attachment(att, out)
        self.assertEqual(out.read_bytes(), payload)
        self.assertNotIn(payload[:64], self.path.read_bytes())
        self.db.delete_forever(item)  # cascade
        self.assertEqual(self.db.conn.execute("SELECT COUNT(*) FROM attachments").fetchone()[0], 0)

    def test_backup_and_restore(self):
        self.db.create("a long master password")
        self.db.add_item("note", {"title": "before"})
        folder = Path(self.tmp.name) / "backups"
        backup = make_backup(self.db, folder, keep=3)
        self.assertEqual(list_backups(folder), [backup])
        self.assertIsNone(auto_backup_if_needed(self.db, folder, 3))  # fresh backup exists
        self.db.add_item("note", {"title": "after"})
        self.db.replace_with(backup)
        self.assertTrue(self.db.unlock("a long master password"))
        self.assertEqual([i.title for i in self.db.get_items()], ["before"])

    def test_backup_pruning(self):
        self.db.create("a long master password")
        folder = Path(self.tmp.name) / "b"
        for n in range(4):
            dest = folder / f"vault-2020010{n}-000000.db"
            self.db.backup_to(dest)
        make_backup(self.db, folder, keep=2)
        self.assertEqual(len(list_backups(folder)), 2)


if __name__ == "__main__":
    unittest.main()
