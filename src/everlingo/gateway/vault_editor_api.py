from __future__ import annotations

import json
import re
from contextlib import asynccontextmanager
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from everlingo.mem.agents.mem_writer_mcp_client import IndexerOfflineError

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


@asynccontextmanager
async def _configured(lang: str):
    try:
        async with mcp_session_configured(lang) as s:
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
        return _unwrap(result)


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
        if not include_tmp and data.get("entries"):
            data["entries"] = _filter_tmp_entries(data["entries"])
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
