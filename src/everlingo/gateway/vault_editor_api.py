from __future__ import annotations

import json
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from everlingo.image.image_store import ALLOWED_MIME, _is_valid_lang, save_vault_image
from everlingo.mem.agents.mem_writer_mcp_client import IndexerOfflineError
from everlingo.mem.vault.frontmatter import parse_frontmatter
from everlingo.setting import load_profile, load_resolved_profile
from everlingo.workspace import lang_vault_dir

from .vault_editor_mcp_client import mcp_session_configured, mcp_session_workspace

router = APIRouter(prefix="/api/vault")

# ── Pydantic models ──────────────────────────────────────────────


class WriteBody(BaseModel):
    path: str
    content: str


class AppendBody(BaseModel):
    path: str
    content: str


class MkdirBody(BaseModel):
    path: str


class DeleteBody(BaseModel):
    path: str


class RenameBody(BaseModel):
    source: str
    target: str


class SearchBody(BaseModel):
    q: str = ""
    mode: str = "hybrid"
    kind: str | None = None
    item_type: str | None = None
    tags: list[str] | None = None
    tags_op: str = "and"
    limit: int = 10


# ── Helpers ──────────────────────────────────────────────────────


def _map_mcp_error(text: str) -> tuple[int, str]:
    if "not configured" in text:
        return 500, f"internal: {text}"
    if re.search(r"path escape|out of vault|escape", text, re.IGNORECASE):
        return 400, text
    if re.search(r"not found|No such", text, re.IGNORECASE):
        return 404, text
    if "lang not" in text.lower():
        return 404, text
    return 500, text


def _filter_hidden_entries(entries: list[dict]) -> list[dict]:
    result = []
    for e in entries:
        if e.get("name", "").startswith("."):
            continue
        if e.get("type") == "dir" and "children" in e:
            e = dict(e)
            e["children"] = _filter_hidden_entries(e["children"])
        result.append(e)
    return result


def _filter_tmp_entries(entries: list[dict]) -> list[dict]:
    result = []
    for e in entries:
        if e.get("name") == "tmp":
            continue
        if e.get("type") == "dir" and "children" in e:
            e = dict(e)
            e["children"] = _filter_tmp_entries(e["children"])
        result.append(e)
    return result


def _unwrap(result: Any) -> dict:
    text = result.content[0].text if result.content else "{}"
    return json.loads(text)


def _inject_titles(entries: list[dict], vault_root: Path) -> None:
    for entry in entries:
        try:
            if entry.get("type") == "file":
                name = entry.get("name", "")
                if not name.endswith(".md"):
                    continue
                if name == "index.md":
                    continue
                abs_path = vault_root / entry["path"]
                if not abs_path.is_file():
                    continue
                raw = abs_path.open("rb").read(4096).decode("utf-8", errors="replace")
                fm, _ = parse_frontmatter(raw)
                title = fm.get("title")
                if title and isinstance(title, str):
                    entry["title"] = title
            elif entry.get("type") == "dir":
                index_path = vault_root / entry["path"] / "index.md"
                if index_path.is_file():
                    raw = index_path.open("rb").read(4096).decode("utf-8", errors="replace")
                    fm, _ = parse_frontmatter(raw)
                    title = fm.get("title")
                    if title and isinstance(title, str):
                        entry["title"] = title
                children = entry.get("children")
                if children:
                    _inject_titles(children, vault_root)
        except Exception:
            pass


@asynccontextmanager
async def _configured(lang: str, interface_language: str | None = None):
    if not interface_language:
        try:
            interface_language = (
                load_resolved_profile().language.interface_language
            )
        except Exception:
            interface_language = None
    try:
        async with mcp_session_configured(lang, interface_language) as s:
            yield s
    except IndexerOfflineError as e:
        raise HTTPException(503, detail=str(e))


@asynccontextmanager
async def _workspace():
    try:
        async with mcp_session_workspace() as s:
            yield s
    except IndexerOfflineError as e:
        raise HTTPException(503, detail=str(e))


# ── Endpoints ────────────────────────────────────────────────────


@router.get("/langs")
async def list_langs():
    async with _workspace() as session:
        result = await session.call_tool("list_vaults", {})
        if result.isError:
            text = result.content[0].text if result.content else "unknown error"
            raise HTTPException(500, detail=text)
        data = _unwrap(result)
        data["default"] = load_profile().language.target_language
        return data


@router.get("/{lang}/tree")
async def tree(
    lang: str,
    path: str = Query(default=""),
    depth: int = Query(default=2, ge=1, le=10),
    include_tmp: bool = Query(default=False, alias="include_tmp"),
):
    async with _configured(lang) as session:
        result = await session.call_tool("tree", {"path": path, "depth": depth})
        if result.isError:
            text = result.content[0].text if result.content else "unknown error"
            status, detail = _map_mcp_error(text)
            raise HTTPException(status, detail=detail)
        data = _unwrap(result)
        if data.get("entries"):
            data["entries"] = _filter_hidden_entries(data["entries"])
        if not include_tmp and data.get("entries"):
            data["entries"] = _filter_tmp_entries(data["entries"])
        if data.get("entries"):
            _inject_titles(data["entries"], lang_vault_dir(lang).resolve())
        return data


@router.get("/{lang}/read")
async def read(lang: str, path: str = Query()):
    async with _configured(lang) as session:
        result = await session.call_tool("read", {"path": path})
        if result.isError:
            text = result.content[0].text if result.content else "unknown error"
            status, detail = _map_mcp_error(text)
            raise HTTPException(status, detail=detail)
        return _unwrap(result)


@router.post("/{lang}/write")
async def write(lang: str, body: WriteBody):
    async with _configured(lang) as session:
        result = await session.call_tool("write", {"path": body.path, "content": body.content})
        if result.isError:
            text = result.content[0].text if result.content else "unknown error"
            status, detail = _map_mcp_error(text)
            raise HTTPException(status, detail=detail)
        return _unwrap(result)


@router.post("/{lang}/append")
async def append(lang: str, body: AppendBody):
    async with _configured(lang) as session:
        result = await session.call_tool("append", {"path": body.path, "content": body.content})
        if result.isError:
            text = result.content[0].text if result.content else "unknown error"
            status, detail = _map_mcp_error(text)
            raise HTTPException(status, detail=detail)
        return _unwrap(result)


@router.post("/{lang}/mkdir")
async def mkdir(lang: str, body: MkdirBody):
    async with _configured(lang) as session:
        result = await session.call_tool("mkdir", {"path": body.path})
        if result.isError:
            text = result.content[0].text if result.content else "unknown error"
            status, detail = _map_mcp_error(text)
            raise HTTPException(status, detail=detail)
        return _unwrap(result)


@router.post("/{lang}/delete")
async def delete(lang: str, body: DeleteBody):
    async with _configured(lang) as session:
        result = await session.call_tool("delete", {"path": body.path})
        if result.isError:
            text = result.content[0].text if result.content else "unknown error"
            status, detail = _map_mcp_error(text)
            raise HTTPException(status, detail=detail)
        return _unwrap(result)


@router.post("/{lang}/rename")
async def rename(lang: str, body: RenameBody):
    async with _configured(lang) as session:
        stat_to = await session.call_tool("stat", {"path": body.target})
        if not stat_to.isError:
            stat_data = _unwrap(stat_to)
            if stat_data.get("exists"):
                raise HTTPException(409, detail=f"target path already exists: {body.target}")

        read_result = await session.call_tool("read", {"path": body.source})
        if read_result.isError:
            text = read_result.content[0].text if read_result.content else "unknown error"
            status, detail = _map_mcp_error(text)
            raise HTTPException(status, detail=detail)
        read_data = _unwrap(read_result)
        content = read_data["content"]

        write_result = await session.call_tool("write", {"path": body.target, "content": content})
        if write_result.isError:
            text = write_result.content[0].text if write_result.content else "unknown error"
            raise HTTPException(500, detail=f"write to target failed: {text}")

        delete_result = await session.call_tool("delete", {"path": body.source})
        if delete_result.isError:
            text = delete_result.content[0].text if delete_result.content else "unknown error"
            return JSONResponse(
                status_code=500,
                content={
                    "detail": f"renamed to {body.target}, but failed to delete source {body.source}: {text}"
                },
            )

        return {"ok": True, "source": body.source, "target": body.target}


@router.post("/{lang}/search")
async def search(lang: str, body: SearchBody):
    async with _configured(lang) as session:
        args: dict[str, Any] = {"q": body.q, "mode": body.mode, "limit": body.limit}
        if body.kind is not None:
            args["kind"] = body.kind
        if body.item_type is not None:
            args["item_type"] = body.item_type
        if body.tags is not None:
            args["tags"] = body.tags
            args["tags_op"] = body.tags_op
        result = await session.call_tool("search", args)
        if result.isError:
            text = result.content[0].text if result.content else "unknown error"
            status, detail = _map_mcp_error(text)
            raise HTTPException(status, detail=detail)
        return _unwrap(result)


@router.get("/{lang}/tags")
async def list_tags(
    lang: str,
    kind: str | None = Query(default=None),
    item_type: str | None = Query(default=None),
):
    async with _configured(lang) as session:
        args: dict[str, Any] = {}
        if kind is not None:
            args["kind"] = kind
        if item_type is not None:
            args["item_type"] = item_type
        result = await session.call_tool("list_tags", args)
        if result.isError:
            text = result.content[0].text if result.content else "unknown error"
            status, detail = _map_mcp_error(text)
            raise HTTPException(status, detail=detail)
        return _unwrap(result)


# ── Raw file endpoints ────────────────────────────────────────────
# ref: docs/ADR/20260816-markdown-image.md — 决策 3 / 决策 4 / 决策 5
# GET/PUT /api/vault/raw/{lang}/{vault_rel_path} 服务 vault 内任意文件字节，
# 用于 markdown 图片的取回（浏览器预览）与上传。纯本地文件系统，不走 MCP。
# 信任边界与现有 read?path= 一致：先 resolve() 再校验 is_relative_to(vault_root)。

# 扩展名 → Content-Type：图片 inline、文本类 text/plain、其它 octet-stream
_RAW_CONTENT_TYPE = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".md": "text/plain",
    ".txt": "text/plain",
    ".json": "text/plain",
    ".yaml": "text/plain",
    ".yml": "text/plain",
    ".csv": "text/plain",
}

# 图片文件取回带 content hash 语义，走 immutable 长缓存（与静态资源一致）
_RAW_IMAGE_CACHE_CONTROL = "public, max-age=31536000, immutable"


def _raw_compute_ct(path: str) -> str:
    return _RAW_CONTENT_TYPE.get(Path(path).suffix.lower(), "application/octet-stream")


def _resolve_raw_vault_path(lang: str, vault_rel_path: str) -> Path:
    """把 {lang}/{vault_rel_path} 解析为 lang vault 内的绝对路径；逃逸/非法 lang 抛 400。"""
    if not _is_valid_lang(lang):
        raise HTTPException(status_code=400, detail="invalid lang name")
    if not vault_rel_path:
        raise HTTPException(status_code=400, detail="path escape")
    vault_root = lang_vault_dir(lang).resolve()
    candidate = (vault_root / vault_rel_path).resolve()
    if not candidate.is_relative_to(vault_root):
        raise HTTPException(status_code=400, detail="path escape")
    return candidate


@router.get("/raw/{lang}/{vault_rel_path:path}")
async def raw_get(lang: str, vault_rel_path: str):
    """通用取回 vault 内任意文件字节（图片 inline、文本类 text/plain、其它 octet-stream）。

    ref: docs/ADR/20260816-markdown-image.md — 决策 3
    """
    candidate = _resolve_raw_vault_path(lang, vault_rel_path)
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail="file not found")
    headers = {"Cache-Control": _RAW_IMAGE_CACHE_CONTROL}
    return FileResponse(path=candidate, media_type=_raw_compute_ct(str(candidate)), headers=headers)


@router.put("/raw/{lang}/{vault_rel_path:path}")
async def raw_upload(lang: str, vault_rel_path: str, file: UploadFile = File(...)):
    """上传图片字节到 vault 内相对路径（multipart file=<binary>）。

    ref: docs/ADR/20260816-markdown-image.md — 决策 4 / 决策 5
    服务端校验：MIME 允许列表（415）；空文件（400）；vault 逃逸 / sha256 mismatch /
    图片不可解析（400）；同 sha 重复上传幂等。
    """
    candidate = _resolve_raw_vault_path(lang, vault_rel_path)

    mime_type = (file.content_type or "").lower()
    if mime_type not in ALLOWED_MIME:
        raise HTTPException(status_code=415, detail=f"unsupported mime type: {mime_type}")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty file")

    try:
        asset = save_vault_image(lang, vault_rel_path, data, mime_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {"image": asset.model_dump()}
