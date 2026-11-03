"""Password generator and a simple strength estimator."""
from __future__ import annotations

import math
import re
import secrets
import string

LOWER = string.ascii_lowercase
UPPER = string.ascii_uppercase
DIGITS = string.digits
SYMBOLS = "!@#$%^&*()-_=+[]{};:,.?/"
AMBIGUOUS = "O0oIl1|"

COMMON = {
    "password", "123456", "12345678", "123456789", "qwerty", "abc123", "letmein",
    "admin", "welcome", "iloveyou", "111111", "000000", "password1", "qwerty123",
    "1q2w3e4r", "monkey", "dragon", "football", "login", "passw0rd",
}

LABELS = ["Very weak", "Weak", "Fair", "Strong", "Very strong"]


def generate_password(
    length: int = 16,
    upper: bool = True,
    lower: bool = True,
    digits: bool = True,
    symbols: bool = True,
    avoid_ambiguous: bool = False,
) -> str:
    pools = []
    for enabled, chars in ((lower, LOWER), (upper, UPPER), (digits, DIGITS), (symbols, SYMBOLS)):
        if enabled:
            if avoid_ambiguous:
                chars = "".join(c for c in chars if c not in AMBIGUOUS)
            pools.append(chars)
    if not pools:
        raise ValueError("Select at least one character type.")
    length = max(length, len(pools))
    result = [secrets.choice(pool) for pool in pools]  # at least one of each type
    everything = "".join(pools)
    result += [secrets.choice(everything) for _ in range(length - len(result))]
    secrets.SystemRandom().shuffle(result)
    return "".join(result)


def _pool_size(pw: str) -> int:
    size = 0
    if re.search(r"[a-z]", pw):
        size += 26
    if re.search(r"[A-Z]", pw):
        size += 26
    if re.search(r"\d", pw):
        size += 10
    if re.search(r"[^\w\s]|_", pw):
        size += 32
    if re.search(r"\s", pw):
        size += 1
    if re.search(r"[^\x00-\x7f]", pw):
        size += 100
    return max(size, 1)


def estimate_bits(pw: str) -> float:
    """Rough entropy estimate with penalties for common/repetitive passwords."""
    if not pw:
        return 0.0
    if pw.lower() in COMMON:
        return 5.0
    bits = len(pw) * math.log2(_pool_size(pw))
    bits *= 0.5 + 0.5 * (len(set(pw)) / len(pw))  # repeated characters
    runs = 0
    for a, b, c in zip(pw, pw[1:], pw[2:]):
        d1, d2 = ord(b) - ord(a), ord(c) - ord(b)
        if d1 == d2 and d1 in (1, -1):
            runs += 1  # abc, 123, cba ...
    return max(bits - 6 * runs, 0.0)


def strength(pw: str) -> tuple[int, str, float]:
    """Return (level 0-4, label, estimated bits)."""
    bits = estimate_bits(pw)
    level = 0 if bits < 28 else 1 if bits < 36 else 2 if bits < 60 else 3 if bits < 80 else 4
    return level, LABELS[level], bits
