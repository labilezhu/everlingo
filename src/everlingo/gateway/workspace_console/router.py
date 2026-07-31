# ref: docs/impl-spec/workspace-console/architecture.md — router 与 API 端点
# Workspace Console router：/api/wechat-channel/* 直调 gateway.wechat_runtime
# （in-process 内存调用，不经 IPC）。

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/wechat-channel", tags=["workspace-console"])


def _runtime() -> Any:
    """返回 gateway 持有的 WechatRuntime 实例（经 web_acceptor 注入的 _gateway）。"""
    from everlingo.gateway import web_acceptor  # lazy：避免与 web_acceptor 循环导入

    gw = web_acceptor._gateway
    if gw is None:
        return None
    return gw.wechat_runtime


@router.get("/status")
async def wechat_status() -> dict:
    """wechat channel 综合状态（running / state / qr_url / last_error）。"""
    rt = _runtime()
    if rt is None:
        return {"running": False, "state": "stopped", "qr_url": None, "last_error": None}
    return rt.status()


@router.post("/start")
async def wechat_start() -> dict:
    """启动 wechat（幂等；锁冲突返回 conflict 态）。"""
    rt = _runtime()
    if rt is None:
        raise HTTPException(status_code=503, detail="wechat runtime not available")
    return await rt.start_wechat()


@router.post("/stop")
async def wechat_stop() -> dict:
    """停止 wechat（优雅停 + 写 enable=false）。"""
    rt = _runtime()
    if rt is None:
        raise HTTPException(status_code=503, detail="wechat runtime not available")
    return await rt.stop_wechat()
