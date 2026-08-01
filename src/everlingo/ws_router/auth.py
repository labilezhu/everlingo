"""认证模块：AuthProvider 抽象、PasswordAuthProvider、JWT 签发/验签。

ref: ws-router.md §3.4, §4.4
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional, Protocol

import jwt as pyjwt

from .cache import TTLCache
from .master_client import MasterClient, UserInfo

logger = logging.getLogger(__name__)


class AuthProvider(Protocol):
    async def login(self, username: str, password: str) -> UserInfo | None: ...


class PasswordAuthProvider:
    def __init__(self, master: MasterClient):
        self._master = master

    async def login(self, username: str, password: str) -> UserInfo | None:
        return await self._master.authenticate(username, password)


def create_session_token(
    user_id: str,
    user_name: str,
    secret: str,
    ttl: int = 28800,
) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "user_name": user_name,
        "exp": now + timedelta(seconds=ttl),
        "iat": now,
        "jti": uuid.uuid4().hex,
    }
    return pyjwt.encode(payload, secret, algorithm="HS256")


def verify_session_token(token: str, secret: str) -> Optional[dict]:
    try:
        payload = pyjwt.decode(token, secret, algorithms=["HS256"])
        return payload
    except pyjwt.ExpiredSignatureError:
        return None
    except pyjwt.InvalidTokenError:
        return None
