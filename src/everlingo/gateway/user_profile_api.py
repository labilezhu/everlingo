# ref: docs/ADR/20260801-user-onboarding.md — 目标学习语言设置页与首次使用引导
# User profile API：/api/user-profile/status、/api/target-language/list、
# /api/target-language/default。复用 vault_editor_mcp_client 的 MCP client
# session 模式（list_vaults / create_vault 均为 workspace 级工具，不依赖
# session.configure，使用 mcp_session_workspace）。
#
# 三端点均不依赖认证（单用户本地拓扑同样可用）。

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from everlingo.mem.agents.mem_writer_mcp_client import IndexerOfflineError
from everlingo.models import LANGUAGES
from everlingo.setting import load_profile, save_profile

from .vault_editor_mcp_client import mcp_session_workspace

router = APIRouter(tags=["user-profile"])


class SetDefaultBody(BaseModel):
    lang: str


@asynccontextmanager
async def _workspace():
    try:
        async with mcp_session_workspace() as s:
            yield s
    except IndexerOfflineError as e:
        raise HTTPException(503, detail=str(e))


def _unwrap(result: Any) -> dict:
    text = result.content[0].text if result.content else "{}"
    return json.loads(text)


async def _list_vaults(session: Any) -> list[str]:
    result = await session.call_tool("list_vaults", {})
    if result.isError:
        text = result.content[0].text if result.content else "unknown error"
        raise HTTPException(500, detail=text)
    data = _unwrap(result)
    return data.get("vaults", [])


async def _try_list_vaults() -> list[str] | None:
    """返回已建 vault 列表；indexer 不可达时返回 None（调用方降级为「未知」）。"""
    try:
        async with _workspace() as session:
            return await _list_vaults(session)
    except HTTPException as e:
        if e.status_code == 503:
            return None
        raise


def _build_languages(current_default: str, vaults: list[str] | None) -> list[dict]:
    languages: list[dict] = []
    for code, name in LANGUAGES.items():
        if vaults is None:
            initialized = None
        else:
            initialized = code in vaults
        languages.append(
            {
                "code": code,
                "name": name,
                "is_default": code == current_default,
                "vault_initialized": initialized,
                "disabled": initialized is None,
                "disabled_reason": "笔记库状态未知（indexer 不可达）" if initialized is None else None,
            }
        )
    return languages


# ── Endpoints ────────────────────────────────────────────────────


@router.get("/api/user-profile/status")
async def user_profile_status() -> dict:
    """默认目标学习语言配置状态（§3 三条件判定）。"""
    profile = load_profile()
    target = profile.language.target_language
    vaults = await _try_list_vaults()
    vault_initialized = (target in vaults) if vaults is not None else None
    is_valid = target in LANGUAGES and vault_initialized is True
    return {
        "target_language": target,
        "is_valid": is_valid,
        "vault_initialized": vault_initialized,
        "needs_setup": not is_valid,
    }


@router.get("/api/target-language/list")
async def target_language_list() -> dict:
    """列出全部支持的目标学习语言及其默认/笔记库状态。"""
    profile = load_profile()
    current_default = profile.language.target_language
    vaults = await _try_list_vaults()
    return {
        "languages": _build_languages(current_default, vaults),
        "current_default": current_default,
    }


@router.post("/api/target-language/default")
async def set_default_language(body: SetDefaultBody) -> dict:
    """把某语言设为默认目标学习语言；未建笔记库时静默 create_vault 后写 yaml。"""
    lang = body.lang
    if lang not in LANGUAGES:
        raise HTTPException(400, detail=f"unsupported target language: {lang!r}")

    async with _workspace() as session:
        vaults = await _list_vaults(session)
        if lang not in vaults:
            result = await session.call_tool("create_vault", {"lang": lang})
            if result.isError:
                text = result.content[0].text if result.content else "unknown error"
                raise HTTPException(500, detail=text)

    profile = load_profile()
    profile = profile.model_copy(
        update={
            "language": profile.language.model_copy(
                update={"target_language": lang}
            )
        }
    )
    save_profile(profile)

    # 返回新 list（同 GET /api/target-language/list 结构）
    return await target_language_list()
