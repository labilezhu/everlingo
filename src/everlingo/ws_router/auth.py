"""认证模块：AuthProvider 抽象、PasswordAuthProvider、JWT 签发/验签。

ref: ws-router.md §3.4, §4.3, §4.4
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

LOGIN_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>EverLingo - Login</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f5f5; display: flex; justify-content: center; align-items: center; min-height: 100vh; }
.login-card { background: #fff; border-radius: 12px; padding: 40px; box-shadow: 0 2px 12px rgba(0,0,0,0.08); width: 360px; }
h1 { font-size: 24px; margin-bottom: 8px; color: #1a1a1a; }
p { color: #666; margin-bottom: 24px; font-size: 14px; }
label { display: block; font-size: 14px; font-weight: 500; margin-bottom: 6px; color: #333; }
input { width: 100%; padding: 10px 12px; border: 1px solid #ddd; border-radius: 8px; font-size: 14px; margin-bottom: 16px; }
input:focus { outline: none; border-color: #4f8cff; box-shadow: 0 0 0 3px rgba(79,140,255,0.15); }
button { width: 100%; padding: 10px; background: #4f8cff; color: #fff; border: none; border-radius: 8px; font-size: 16px; cursor: pointer; }
button:hover { background: #3a76e8; }
.error { color: #e53e3e; font-size: 14px; margin-bottom: 16px; }
</style>
</head>
<body>
<div class="login-card">
<h1>Welcome</h1>
<p>Sign in to EverLingo</p>
<form method="post" action="/login">
<label for="username">Username</label>
<input type="text" id="username" name="username" required autofocus>
<label for="password">Password</label>
<input type="password" id="password" name="password" required>
<button type="submit">Sign In</button>
</form>
</div>
</body>
</html>"""

LOGIN_HTML_ERROR = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>EverLingo - Login</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f5f5; display: flex; justify-content: center; align-items: center; min-height: 100vh; }
.login-card { background: #fff; border-radius: 12px; padding: 40px; box-shadow: 0 2px 12px rgba(0,0,0,0.08); width: 360px; }
h1 { font-size: 24px; margin-bottom: 8px; color: #1a1a1a; }
p { color: #666; margin-bottom: 24px; font-size: 14px; }
label { display: block; font-size: 14px; font-weight: 500; margin-bottom: 6px; color: #333; }
input { width: 100%; padding: 10px 12px; border: 1px solid #ddd; border-radius: 8px; font-size: 14px; margin-bottom: 16px; }
input:focus { outline: none; border-color: #4f8cff; box-shadow: 0 0 0 3px rgba(79,140,255,0.15); }
button { width: 100%; padding: 10px; background: #4f8cff; color: #fff; border: none; border-radius: 8px; font-size: 16px; cursor: pointer; }
button:hover { background: #3a76e8; }
.error { color: #e53e3e; font-size: 14px; margin-bottom: 16px; }
</style>
</head>
<body>
<div class="login-card">
<h1>Welcome</h1>
<p>Sign in to EverLingo</p>
<div class="error">Invalid username or password</div>
<form method="post" action="/login">
<label for="username">Username</label>
<input type="text" id="username" name="username" required autofocus>
<label for="password">Password</label>
<input type="password" id="password" name="password" required>
<button type="submit">Sign In</button>
</form>
</div>
</body>
</html>"""


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
