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
from everlingo.models import AVAILABLE_INTERFACE_LANGUAGES, LANGUAGES, resolve_interface_language
from everlingo.setting import bump_prompt_version, load_profile, save_profile

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


def _build_interface_languages() -> list[dict]:
    """可用界面语言列表（含 display 名，复用 LANGUAGES[code]）。"""
    return [
        {"code": code, "name": LANGUAGES[code]} for code in AVAILABLE_INTERFACE_LANGUAGES
    ]


# ── Endpoints ────────────────────────────────────────────────────


@router.get("/api/user-profile/status")
async def user_profile_status() -> dict:
    """默认目标学习语言配置状态（§3 三条件判定）+ 界面语言状态。

    interface_language：raw（可能为空）；interface_language_resolved：运行时推断值；
    available_interface_languages：供前端直接渲染的可用界面语言列表。
    needs_setup = (!is_valid) OR (interface_language 为空)。
    ref: docs/ADR/20260806-phase3-web-i18n-onboarding.md §4.6
    """
    profile = load_profile()
    target = profile.language.target_language
    raw = profile.language.interface_language
    resolved = resolve_interface_language(raw)
    vaults = await _try_list_vaults()
    vault_initialized = (target in vaults) if vaults is not None else None
    is_valid = target in LANGUAGES and vault_initialized is True
    return {
        "target_language": target,
        "is_valid": is_valid,
        "vault_initialized": vault_initialized,
        "needs_setup": (not is_valid) or not raw,
        "interface_language": raw,
        "interface_language_resolved": resolved,
        "available_interface_languages": _build_interface_languages(),
    }


@router.post("/api/user-profile/interface-language")
async def set_interface_language(body: SetDefaultBody) -> dict:
    """写入界面语言到 yaml，并 bump prompt 版本触发 Agent 重建。

    只接受 ∈ AVAILABLE_INTERFACE_LANGUAGES 的值。写 yaml 走 raw（load_profile +
    save_profile，双访问器不变量），显式 bump_prompt_version()（interface_language
    不在 prompt 文件 mtime 监控范围内，必须显式触发重建）。
    ref: docs/ADR/20260806-phase3-web-i18n-onboarding.md §4.5
    """
    lang = body.lang
    if lang not in AVAILABLE_INTERFACE_LANGUAGES:
        raise HTTPException(400, detail=f"unsupported interface language: {lang!r}")

    profile = load_profile()
    profile = profile.model_copy(
        update={
            "language": profile.language.model_copy(
                update={"interface_language": lang}
            )
        }
    )
    save_profile(profile)
    bump_prompt_version()

    return {
        "interface_language": lang,
        "available_interface_languages": _build_interface_languages(),
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


@router.post("/api/target-language/reset-vault")
async def reset_vault(body: SetDefaultBody) -> dict:
    """重新 seed 已初始化 lang 的 spec/ 目录（覆盖写入），保护用户笔记数据。"""
    lang = body.lang
    if lang not in LANGUAGES:
        raise HTTPException(400, detail=f"unsupported target language: {lang!r}")

    async with _workspace() as session:
        result = await session.call_tool("reset_vault", {"lang": lang})
        if result.isError:
            text = result.content[0].text if result.content else "unknown error"
            raise HTTPException(500, detail=text)

    return await target_language_list()
