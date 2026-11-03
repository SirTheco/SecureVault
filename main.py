"""Cryptography helpers: AES-256-GCM encryption and scrypt key derivation.

Key design
----------
* A random 256-bit Data Encryption Key (DEK) encrypts everything in the vault.
* The DEK is stored "wrapped" (encrypted) twice:
    1. with a key derived from the master password (scrypt),
    2. with a key derived from the recovery key (HKDF).
  Changing the master password therefore only re-wraps the DEK.
"""
from __future__ import annotations

import base64
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

KEY_LEN = 32
NONCE_LEN = 12
TAG_LEN = 16
RECOVERY_BYTES = 25  # 200 bits -> 40 base32 characters

# OWASP-recommended minimum for scrypt: N=2^17, r=8, p=1 (~128 MB RAM, ~0.3 s)
SCRYPT_PARAMS = {"n": 2**17, "r": 8, "p": 1}


class DecryptionError(Exception):
    """Raised when data cannot be decrypted (wrong key or corrupted data)."""


def b64e(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def b64d(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"))


def new_key() -> bytes:
    return os.urandom(KEY_LEN)


def derive_key(secret: bytes, salt: bytes, params: dict) -> bytes:
    kdf = Scrypt(salt=salt, length=KEY_LEN, n=params["n"], r=params["r"], p=params["p"])
    return kdf.derive(secret)


def recovery_to_key(raw: bytes) -> bytes:
    """The recovery key is already high-entropy, so HKDF is enough."""
    return HKDF(
        algorithm=hashes.SHA256(), length=KEY_LEN, salt=None, info=b"securevault-recovery"
    ).derive(raw)


def encrypt(key: bytes, data: bytes, aad: bytes = b"") -> bytes:
    nonce = os.urandom(NONCE_LEN)
    return nonce + AESGCM(key).encrypt(nonce, data, aad)


def decrypt(key: bytes, blob: bytes, aad: bytes = b"") -> bytes:
    if len(blob) < NONCE_LEN + TAG_LEN:
        raise DecryptionError("Data is too short to be valid.")
    try:
        return AESGCM(key).decrypt(blob[:NONCE_LEN], blob[NONCE_LEN:], aad)
    except InvalidTag as exc:
        raise DecryptionError("Wrong key or corrupted data.") from exc


def new_recovery_key() -> tuple[bytes, str]:
    """Return (raw bytes, human friendly text like ABCDE-FGHIJ-...)."""
    raw = os.urandom(RECOVERY_BYTES)
    text = base64.b32encode(raw).decode("ascii")
    return raw, "-".join(text[i : i + 5] for i in range(0, len(text), 5))


def parse_recovery_key(text: str) -> bytes:
    cleaned = "".join(text.upper().split()).replace("-", "")
    try:
        raw = base64.b32decode(cleaned)
    except Exception as exc:  # binascii.Error and friends
        raise DecryptionError("The recovery key format is invalid.") from exc
    if len(raw) != RECOVERY_BYTES:
        raise DecryptionError("The recovery key format is invalid.")
    return raw
