# ref: docs/ADR/20260810-vault-version-control.md — P3（二期）gateway REST API
# Backup API：/api/backup/*。git 操作全部复用 indexer 的 /version/* 端点
# （经 SearchClient 走 UDS），配置读写 everlingo.yaml（git_backup 段）。
#
# P3 边界：凭证模式仅 ssh / https_none；https_pat 输入与 PAT 掩码留 P4。
# GET 配置时 pat 一律返回空串，避免 P3 提前泄露。

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from everlingo import workspace
from everlingo.mem.vault.search.client import SearchClient
from everlingo.models import GitBackup, GitBackupAuth
from everlingo.setting import load_git_backup, save_git_backup

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/backup", tags=["backup"])

# P3 允许的凭证模式（https_pat 留 P4）
ALLOWED_METHODS = {"ssh", "https_none"}

_client: SearchClient | None = None


def _get_client() -> SearchClient:
    """懒初始化 UDS 客户端（对 indexer.sock）。"""
    global _client
    if _client is None:
        _client = SearchClient(workspace.indexer_socket_path())
    return _client


class BackupConfigBody(BaseModel):
    """保存 git_backup 配置（P3 字段）。"""

    enabled: bool = False
    remote_url: str = ""
    branch: str = "main"
    method: str = "ssh"
    ssh_private_key_file: str = ""
    commit_interval: int | None = Field(
        default=None, ge=1, description="留空则保持原值"
    )
    push_interval: int | None = Field(
        default=0, ge=0, description="0=仅手动触发"
    )


class RestoreBody(BaseModel):
    commit_hash: str


def _to_public(backup: GitBackup) -> dict:
    """序列化为前端可见配置。P3：pat 一律置空（掩码留 P4）。"""
    data = backup.model_dump()
    data["auth"] = {**data["auth"], "pat": ""}
    return data


def _unwrap(client_response: Any, *, what: str) -> Any:
    """SearchClient 同步方法返回 None（不可达/失败）→ 503。"""
    if client_response is None:
        raise HTTPException(status_code=503, detail=f"{what} 失败：indexer 不可达或返回异常")
    return client_response


@router.get("/status")
async def backup_status() -> dict:
    """聚合 git repo 状态 + 配置。"""
    client = _get_client()
    status = await run_in_threadpool(client.version_status)
    return _unwrap(status, what="version/status").model_dump()


@router.get("/config")
async def backup_get_config() -> dict:
    """当前 git_backup 配置（pat 掩码，P4 才实现）。"""
    return _to_public(load_git_backup())


@router.post("/config")
async def backup_save_config(body: BackupConfigBody) -> dict:
    """校验并保存 git_backup，随后热重载 indexer committer。"""
    if body.method not in ALLOWED_METHODS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持凭证模式 {body.method!r}（P3 仅 ssh / https_none，https_pat 待 P4）",
        )
    current = load_git_backup()
    # 保留既有 pat 等未覆盖字段，避免覆盖 CLI 侧配置
    updated = current.model_copy(
        update={
            "enabled": body.enabled,
            "remote_url": body.remote_url,
            "branch": body.branch or "main",
            "auth": current.auth.model_copy(
                update={
                    "method": body.method,
                    "ssh_private_key_file": body.ssh_private_key_file,
                }
            ),
            "commit_interval": (
                body.commit_interval if body.commit_interval is not None else current.commit_interval
            ),
            "push_interval": body.push_interval,
        }
    )
    save_git_backup(updated)

    client = _get_client()
    ok = await run_in_threadpool(client.version_apply_config)
    if ok is False:
        logger.warning("apply-config 热重载失败，配置已落盘（下次 indexer 重启生效）")
    return _to_public(updated)


@router.post("/snapshot")
async def backup_snapshot() -> dict:
    client = _get_client()
    ok = await run_in_threadpool(client.version_commit)
    if ok is None:
        raise HTTPException(status_code=503, detail="version/commit 失败：indexer 不可达或返回异常")
    return {"ok": ok}


@router.post("/push")
async def backup_push() -> dict:
    client = _get_client()
    ok = await run_in_threadpool(client.version_push)
    if ok is None:
        raise HTTPException(status_code=503, detail="version/push 失败：indexer 不可达或返回异常")
    return {"ok": ok}


@router.post("/pull")
async def backup_pull() -> dict:
    """软恢复：commit → fetch → rebase。冲突时给 backup 分支。"""
    client = _get_client()
    resp = await run_in_threadpool(client.version_pull)
    return _unwrap(resp, what="version/pull").model_dump()


@router.post("/test")
async def backup_test() -> dict:
    """测试连接：用配置凭证探测远端连通性。"""
    client = _get_client()
    resp = await run_in_threadpool(client.version_test_remote)
    return _unwrap(resp, what="version/test").model_dump()


@router.post("/reset-hard")
async def backup_reset_hard() -> dict:
    """强操作：commit → fetch → git reset --hard origin/<branch>。"""
    client = _get_client()
    resp = await run_in_threadpool(client.version_reset_hard)
    return _unwrap(resp, what="version/reset-hard").model_dump()


@router.get("/log")
async def backup_log(limit: int = 20) -> dict:
    client = _get_client()
    resp = await run_in_threadpool(client.version_log, limit)
    return _unwrap(resp, what="version/log").model_dump()


@router.post("/restore")
async def backup_restore(body: RestoreBody) -> dict:
    client = _get_client()
    resp = await run_in_threadpool(client.version_restore, body.commit_hash)
    return _unwrap(resp, what="version/restore").model_dump()