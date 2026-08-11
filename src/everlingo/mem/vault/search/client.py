# ref: docs/impl-spec/search/memory-vault-search-spec.md — gateway 侧接口
# SearchClient：httpx + unix socket transport，gateway 进程内使用。
# indexer 不可达时优雅降级：search() 返回 [] + warn，index_file() 返回 False + warn。
# 协议层 (SearchHit/ChunkRef/Request/Response) 在 protocol.py 中定义，gateway
# 与 indexer 共享。
#
# 所有端点通过 path segment /{lang}/... 路由到对应语言的 DB。
# lang 为必填参数。

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Literal

import httpx

from .protocol import (
    EmbedRequest,
    EmbedResponse,
    IndexRequest,
    RebuildResponse,
    RestoreRequest,
    RestoreResponse,
    SearchHit,
    SearchRequest,
    SearchResponse,
    StatusResponse,
    TagsResponse,
    VersionLogResponse,
    VersionStatusResponse,
    VersionTestResponse,
)

logger = logging.getLogger(__name__)


class SearchClient:
    """gateway 侧 SearchClient；懒初始化 httpx Unix socket 客户端。

    协议：HTTP/1.1 over unix domain socket，path 形如 'http://localhost/{lang}/...'
    httpx 通过 transport=httpx.AsyncHTTPTransport(uds=...) 把 hostname 视为 socket 路径。
    """

    def __init__(self, uds_path: str | Path) -> None:
        self._uds_path = str(uds_path)
        self._client: httpx.Client | None = None
        self._lock = threading.Lock()

    def _ensure_client(self) -> httpx.Client:
        with self._lock:
            if self._client is None:
                self._client = httpx.Client(
                    transport=httpx.HTTPTransport(uds=self._uds_path),
                    timeout=httpx.Timeout(5.0),
                )
            return self._client

    def close(self) -> None:
        with self._lock:
            if self._client is not None:
                self._client.close()
                self._client = None

    def _is_unreachable(self, exc: BaseException) -> bool:
        return isinstance(
            exc,
            (
                httpx.ConnectError,
                httpx.ConnectTimeout,
                httpx.ReadTimeout,
                httpx.WriteTimeout,
                httpx.PoolTimeout,
                httpx.RemoteProtocolError,
                httpx.RequestError,
                OSError,
            ),
        )

    def search(
        self,
        query: str,
        *,
        lang: str,
        item_type: str | None = None,
        tags: list[str] | None = None,
        tags_op: Literal["and", "or"] = "and",
        kind: str | None = None,
        mode: Literal["exact", "semantic", "hybrid"] = "exact",
        limit: int = 20,
    ) -> list[SearchHit]:
        req = SearchRequest(
            q=query,
            item_type=item_type,
            tags=tags,
            tags_op=tags_op,
            kind=kind,
            mode=mode,
            limit=limit,
        )
        try:
            client = self._ensure_client()
            resp = client.post(f"http://localhost/{lang}/search", json=req.model_dump())
            resp.raise_for_status()
            data = resp.json()
            return SearchResponse.model_validate(data).hits
        except Exception as e:
            if self._is_unreachable(e):
                logger.warning("indexer 不可达，search 降级返回 []: %s", e)
            else:
                logger.warning("search 失败: %s", e)
            return []

    def index_file(self, lang: str, path: str) -> bool:
        """fire-and-forget 投递索引请求。失败返回 False。"""
        req = IndexRequest(path=path)
        try:
            client = self._ensure_client()
            resp = client.post(f"http://localhost/{lang}/index", json=req.model_dump())
            resp.raise_for_status()
            return True
        except Exception as e:
            if self._is_unreachable(e):
                logger.warning("indexer 不可达，index_file 丢弃: %s", e)
            else:
                logger.warning("index_file 失败: %s", e)
            return False

    def delete_file(self, lang: str, path: str) -> bool:
        req = IndexRequest(path=path)
        try:
            client = self._ensure_client()
            resp = client.post(f"http://localhost/{lang}/delete", json=req.model_dump())
            resp.raise_for_status()
            return True
        except Exception as e:
            if self._is_unreachable(e):
                logger.warning("indexer 不可达，delete 丢弃: %s", e)
            else:
                logger.warning("delete 失败: %s", e)
            return False

    def rebuild(self, lang: str) -> RebuildResponse | None:
        try:
            client = self._ensure_client()
            resp = client.post(f"http://localhost/{lang}/rebuild")
            resp.raise_for_status()
            return RebuildResponse.model_validate(resp.json())
        except Exception as e:
            if self._is_unreachable(e):
                logger.warning("indexer 不可达，rebuild 失败: %s", e)
            else:
                logger.warning("rebuild 失败: %s", e)
            return None

    def status(self) -> StatusResponse | None:
        try:
            client = self._ensure_client()
            resp = client.get("http://localhost/status")
            resp.raise_for_status()
            return StatusResponse.model_validate(resp.json())
        except Exception as e:
            if self._is_unreachable(e):
                logger.warning("indexer 不可达，status 失败: %s", e)
            else:
                logger.warning("status 失败: %s", e)
            return None

    def list_tags(
        self,
        lang: str,
        kind: str | None = None,
        item_type: str | None = None,
    ) -> TagsResponse | None:
        """返回该 lang vault 的 tag 字典及计数。"""
        params = {}
        if kind is not None:
            params["kind"] = kind
        if item_type is not None:
            params["item_type"] = item_type
        try:
            client = self._ensure_client()
            resp = client.get(f"http://localhost/{lang}/tags", params=params)
            resp.raise_for_status()
            return TagsResponse.model_validate(resp.json())
        except Exception as e:
            if self._is_unreachable(e):
                logger.warning("indexer 不可达，list_tags 返回 None: %s", e)
            else:
                logger.warning("list_tags 失败: %s", e)
            return None

    def embed(self, lang: str, *, rebuild: bool = False, batch: int = 64, wait: bool = True) -> EmbedResponse | None:
        """触发 indexer 跑一轮 embedding 补嵌。

        rebuild=True: drop 旧 vec0+embeddings 全量重嵌。
        wait=True: 同步等到全量完成；False: fire-and-forget（仅返回当前状态）。
        """
        req = EmbedRequest(rebuild=rebuild, batch=batch, wait=wait)
        try:
            client = self._ensure_client()
            resp = client.post(f"http://localhost/{lang}/embed", json=req.model_dump())
            resp.raise_for_status()
            return EmbedResponse.model_validate(resp.json())
        except Exception as e:
            if self._is_unreachable(e):
                logger.warning("indexer 不可达，embed 失败: %s", e)
            else:
                logger.warning("embed 失败: %s", e)
            return None

    # ── /version/*：Memory Vault 版本控制与远端备份 ────────────────

    def version_status(self) -> VersionStatusResponse | None:
        try:
            client = self._ensure_client()
            resp = client.get("http://localhost/version/status")
            resp.raise_for_status()
            return VersionStatusResponse.model_validate(resp.json())
        except Exception as e:
            if self._is_unreachable(e):
                logger.warning("indexer 不可达，version/status 返回 None: %s", e)
            else:
                logger.warning("version/status 失败: %s", e)
            return None

    def version_commit(self) -> bool | None:
        """同步触发一次 commit。返回是否产生了 commit；失败/不可达返回 None。"""
        try:
            client = self._ensure_client()
            resp = client.post("http://localhost/version/commit")
            resp.raise_for_status()
            return resp.json().get("ok")
        except Exception as e:
            if self._is_unreachable(e):
                logger.warning("indexer 不可达，version/commit 失败: %s", e)
            else:
                logger.warning("version/commit 失败: %s", e)
            return None

    def version_push(self) -> bool | None:
        try:
            client = self._ensure_client()
            resp = client.post("http://localhost/version/push")
            resp.raise_for_status()
            return resp.json().get("ok")
        except Exception as e:
            if self._is_unreachable(e):
                logger.warning("indexer 不可达，version/push 失败: %s", e)
            else:
                logger.warning("version/push 失败: %s", e)
            return None

    def version_force_push(self) -> bool | None:
        """git push --force（无条件覆盖远端历史）。"""
        try:
            client = self._ensure_client()
            resp = client.post("http://localhost/version/force-push")
            resp.raise_for_status()
            return resp.json().get("ok")
        except Exception as e:
            if self._is_unreachable(e):
                logger.warning("indexer 不可达，version/force-push 失败: %s", e)
            else:
                logger.warning("version/force-push 失败: %s", e)
            return None

    def version_pull(self) -> RestoreResponse | None:
        """走 restore 流程（commit→fetch→rebase）；冲突返回 backup 分支。"""
        try:
            client = self._ensure_client()
            resp = client.post("http://localhost/version/pull")
            resp.raise_for_status()
            return RestoreResponse.model_validate(resp.json())
        except Exception as e:
            if self._is_unreachable(e):
                logger.warning("indexer 不可达，version/pull 返回 None: %s", e)
            else:
                logger.warning("version/pull 失败: %s", e)
            return None

    def version_log(self, limit: int = 20) -> VersionLogResponse | None:
        try:
            client = self._ensure_client()
            resp = client.get("http://localhost/version/log", params={"limit": limit})
            resp.raise_for_status()
            return VersionLogResponse.model_validate(resp.json())
        except Exception as e:
            if self._is_unreachable(e):
                logger.warning("indexer 不可达，version/log 返回 None: %s", e)
            else:
                logger.warning("version/log 失败: %s", e)
            return None

    def version_restore(self, commit_hash: str) -> RestoreResponse | None:
        """把指定历史版本检出到 backup 分支（不直接覆盖工作区）。"""
        try:
            client = self._ensure_client()
            resp = client.post(
                "http://localhost/version/restore",
                json=RestoreRequest(commit_hash=commit_hash).model_dump(),
            )
            resp.raise_for_status()
            return RestoreResponse.model_validate(resp.json())
        except Exception as e:
            if self._is_unreachable(e):
                logger.warning("indexer 不可达，version/restore 返回 None: %s", e)
            else:
                logger.warning("version/restore 失败: %s", e)
            return None

    def version_apply_config(self) -> bool | None:
        """保存 git_backup 配置后触发 committer 热重载。"""
        try:
            client = self._ensure_client()
            resp = client.post("http://localhost/version/apply-config")
            resp.raise_for_status()
            return resp.json().get("ok")
        except Exception as e:
            if self._is_unreachable(e):
                logger.warning("indexer 不可达，version/apply-config 失败: %s", e)
            else:
                logger.warning("version/apply-config 失败: %s", e)
            return None

    def version_test_remote(self) -> VersionTestResponse | None:
        """用配置凭证探测远端连通性。"""
        try:
            client = self._ensure_client()
            resp = client.post("http://localhost/version/test")
            resp.raise_for_status()
            return VersionTestResponse.model_validate(resp.json())
        except Exception as e:
            if self._is_unreachable(e):
                logger.warning("indexer 不可达，version/test 返回 None: %s", e)
            else:
                logger.warning("version/test 失败: %s", e)
            return None

    def version_reset_hard(self) -> RestoreResponse | None:
        """强操作：reset --hard 到远端（丢弃本地差异）。"""
        try:
            client = self._ensure_client()
            resp = client.post("http://localhost/version/reset-hard")
            resp.raise_for_status()
            return RestoreResponse.model_validate(resp.json())
        except Exception as e:
            if self._is_unreachable(e):
                logger.warning("indexer 不可达，version/reset-hard 返回 None: %s", e)
            else:
                logger.warning("version/reset-hard 失败: %s", e)
            return None
