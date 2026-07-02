# ref: docs/impl-spec/search/memory-vault-search-spec.md — IPC 协议 / 返回类型
# SearchHit / ChunkRef pydantic 模型，供 gateway 与 indexer 共享。
# gateway 侧只需 import 此文件 + client.py，不加载 jieba/fugashi/SQLite。
#
# mode / source / chunk 字段为混合检索（vec / hybrid）预留；本期只产出
# mode='exact' + source='fts'。

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ChunkRef(BaseModel):
    """段级命中引用。

    section_title / section_kind 在 events 文件中可能为 None（整文件一行 FTS）。
    """

    model_config = ConfigDict(extra="forbid")

    chunk_id: int
    section_title: str | None = None
    section_kind: str | None = None
    char_offset: int = 0
    text: str


class SearchHit(BaseModel):
    """单条搜索结果。

    source 标识命中来源（fts/vec/hybrid），本期固定 'fts'；
    chunk 在文件级 FTS 命中时为 None，段级命中时填入。
    snippet 为 FTS snippet() 或 chunk.text 片段。
    """

    model_config = ConfigDict(extra="forbid")

    ulid: str
    kind: Literal["item", "event", "user"]
    lang: str | None = None
    item_type: str | None = None
    file_path: str
    title: str | None = None
    score: float
    source: Literal["fts", "vec", "hybrid"] = "fts"
    chunk: ChunkRef | None = None
    snippet: str = ""


# ── 请求/响应模型 ────────────────────────────────────────────────────


class SearchRequest(BaseModel):
    """POST /search 请求体。"""

    model_config = ConfigDict(extra="forbid")

    q: str = Field(..., description="查询字符串（indexer 侧会先 tokenize）")
    lang: str | None = None
    item_type: str | None = None
    tags: list[str] | None = None
    kind: Literal["item", "event", "user"] | None = None
    mode: Literal["exact", "semantic", "hybrid"] = "exact"
    limit: int = Field(20, ge=1, le=100)


class SearchResponse(BaseModel):
    """POST /search 响应体。"""

    model_config = ConfigDict(extra="forbid")

    hits: list[SearchHit]
    count: int
    took_ms: float


class IndexRequest(BaseModel):
    """POST /index / POST /delete 请求体（path 相对 $workspace/memory）。"""

    model_config = ConfigDict(extra="forbid")

    path: str = Field(..., description="相对 $workspace/memory 的 .md 路径")


class OkResponse(BaseModel):
    """POST /index / POST /delete 通用响应。"""

    model_config = ConfigDict(extra="forbid")

    ok: bool = True


class RebuildResponse(BaseModel):
    """POST /rebuild 响应。"""

    model_config = ConfigDict(extra="forbid")

    ok: bool = True
    indexed: int
    chunks: int
    took_ms: float


class EmbedRequest(BaseModel):
    """POST /embed 请求体。"""

    model_config = ConfigDict(extra="forbid")

    rebuild: bool = Field(False, description="True=drop vec0+embeddings，全量重嵌")
    batch: int = Field(64, ge=1, le=512, description="每批嵌入 chunk 数")
    wait: bool = Field(True, description="True=同步等到全量完成；False=fire-and-forget")


class EmbedResponse(BaseModel):
    """POST /embed 响应。"""

    model_config = ConfigDict(extra="forbid")

    ok: bool = True
    embedded: int = Field(0, description="本次嵌入的 chunk 数（wait=False 时为 0）")
    total_chunks: int
    embedded_chunks: int
    embedding_model_id: str | None = None
    embedding_dim: int | None = None
    took_ms: float = 0.0


class StatusResponse(BaseModel):
    """GET /status 响应。"""

    model_config = ConfigDict(extra="forbid")

    running: bool
    tokenizer_version: str
    docs: int
    chunks: int
    uptime_s: float
    embedding_model_id: str | None = None
    embedding_dim: int | None = None
    embedded_chunks: int = 0
