"""PAT（Personal Access Token）生成与验证工具。

格式：elpat_<base62 随机串>
存储：sha256 哈希
"""

from __future__ import annotations

import hashlib
import secrets

# Base62 alphabet: 0-9, a-z, A-Z
ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _base62_encode(n: int) -> str:
    """Encode an integer to base62 string."""
    if n == 0:
        return ALPHABET[0]
    chars = []
    while n > 0:
        chars.append(ALPHABET[n % 62])
        n //= 62
    return "".join(reversed(chars))


def generate_pat() -> tuple[str, str]:
    """Generate a PAT.

    Returns:
        (plain_token, sha256_hash)
    """
    random_bytes = secrets.token_bytes(32)
    random_int = int.from_bytes(random_bytes, "big")
    plain = "elpat_" + _base62_encode(random_int)
    return plain, hashlib.sha256(plain.encode()).hexdigest()


def hash_token(plain: str) -> str:
    """SHA256 hash of a token string."""
    return hashlib.sha256(plain.encode()).hexdigest()