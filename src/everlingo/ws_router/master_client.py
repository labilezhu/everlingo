"""WS-Master Internal API 客户端。

封装对 WS-Master 所有 Internal API 端点的 HTTP 调用。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)


@dataclass
class UserInfo:
    user_id: str
    user_name: str
    display_name: str


@dataclass
class BackendInfo:
    ws_container_id: str
    backend_url: str
    status: str


@dataclass
class PatInfo:
    id: str
    label: str
    created_at: str
    last_used_at: str | None = None
    expires_at: str | None = None


@dataclass
class PatCreateResult:
    id: str
    token: str
    label: str
    created_at: str
    expires_at: str | None = None


class MasterClient:
    def __init__(self, base_url: str, secret: str, timeout: int = 90):
        self._base_url = base_url.rstrip("/")
        self._headers = {"X-Master-Token": secret, "Content-Type": "application/json"}
        self._client = httpx.AsyncClient(base_url=self._base_url, headers=self._headers, timeout=httpx.Timeout(float(timeout)))

    async def close(self) -> None:
        await self._client.aclose()

    async def authenticate(self, username: str, password: str) -> UserInfo | None:
        try:
            resp = await self._client.post(
                "/internal/authenticate",
                json={"username": username, "password": password},
            )
            if resp.status_code == 200:
                data = resp.json()
                return UserInfo(
                    user_id=data["user_id"],
                    user_name=data["user_name"],
                    display_name=data["display_name"],
                )
            logger.warning("MasterClient.authenticate: master returned status=%d", resp.status_code)
            return None
        except httpx.RequestError as e:
            logger.warning("MasterClient.authenticate failed: %s", e)
            return None

    async def pat_verify(self, token: str) -> UserInfo | None:
        try:
            resp = await self._client.post(
                "/internal/pat/verify",
                json={"token": token},
            )
            if resp.status_code == 200:
                data = resp.json()
                return UserInfo(
                    user_id=data["user_id"],
                    user_name=data["user_name"],
                    display_name=data["display_name"],
                )
            logger.warning("MasterClient.pat_verify: master returned status=%d", resp.status_code)
            return None
        except httpx.RequestError as e:
            logger.warning("MasterClient.pat_verify failed: %s", e)
            return None

    async def pat_list(self, user_id: str) -> list[PatInfo] | None:
        try:
            resp = await self._client.get(f"/internal/users/{user_id}/pat")
            if resp.status_code == 200:
                data = resp.json()
                return [
                    PatInfo(
                        id=item["id"],
                        label=item["label"],
                        created_at=item["created_at"],
                        last_used_at=item.get("last_used_at"),
                        expires_at=item.get("expires_at"),
                    )
                    for item in data
                ]
            logger.warning("MasterClient.pat_list: master returned status=%d", resp.status_code)
            return None
        except httpx.RequestError as e:
            logger.warning("MasterClient.pat_list failed: %s", e)
            return None

    async def pat_create(self, user_id: str, label: str, expires_at: str | None = None) -> PatCreateResult | None:
        try:
            resp = await self._client.post(
                "/internal/pat",
                json={"user_id": user_id, "label": label, "expires_at": expires_at},
            )
            if resp.status_code == 201:
                data = resp.json()
                return PatCreateResult(
                    id=data["id"],
                    token=data["token"],
                    label=data["label"],
                    created_at=data["created_at"],
                    expires_at=data.get("expires_at"),
                )
            logger.warning("MasterClient.pat_create: master returned status=%d", resp.status_code)
            return None
        except httpx.RequestError as e:
            logger.warning("MasterClient.pat_create failed: %s", e)
            return None

    async def get_user(self, user_id: str) -> UserInfo | None:
        try:
            resp = await self._client.get(f"/internal/users/{user_id}")
            if resp.status_code == 200:
                data = resp.json()
                return UserInfo(
                    user_id=data["user_id"],
                    user_name=data["user_name"],
                    display_name=data["display_name"],
                )
            logger.warning("MasterClient.get_user: master returned status=%d", resp.status_code)
            return None
        except httpx.RequestError as e:
            logger.warning("MasterClient.get_user failed: %s", e)
            return None

    async def get_default_backend(self, user_id: str) -> BackendInfo | None:
        try:
            resp = await self._client.get(f"/internal/users/{user_id}/default-ws/backend")
            if resp.status_code == 200:
                data = resp.json()
                return BackendInfo(
                    ws_container_id=data["ws_container_id"],
                    backend_url=data["backend_url"],
                    status=data["status"],
                )
            logger.warning("MasterClient.get_default_backend: master returned status=%d", resp.status_code)
            return None
        except httpx.RequestError as e:
            logger.warning("MasterClient.get_default_backend failed: %s", e)
            return None
