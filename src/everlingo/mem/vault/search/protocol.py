# ref: docs/impl-spec/search/memory-vault-search-spec.md — IPC 协议 / 返回类型
# SearchHit / ChunkRef pydantic 模型，供 gateway 与 indexer 共享。
# gateway 侧只需 import 此文件 + client.py，不加载 jieba/fugashi/SQLite。
#
# mode / source / chunk 字段为混合检索（vec / hybrid）预留。
# lang 字段由 indexer 按请求 lang 回填（不来自 documents 列，per-lang DB 隐含）。

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

    source 标识命中来源（fts/vec/hybrid）；
    chunk 在文件级 FTS 命中时为 None，段级命中时填入。
    snippet 为 FTS snippet() 或 chunk.text 片段。
    lang 由 indexer 按请求 path 中的 lang 回填（不来自 documents 列）。
    ulid 为可选（LLM 文件自动带；用户手写文件缺 ulid 时返回 None）。
    """

    model_config = ConfigDict(extra="forbid")

    ulid: str | None
    kind: Literal["item", "event"]  # type: ignore[assignment]
    lang: str
    item_type: str | None = None
    file_path: str
    title: str | None = None
    score: float
    source: str = "fts"
    chunk: ChunkRef | None = None
    snippet: str = ""


# ── 请求/响应模型 ────────────────────────────────────────────────────


class SearchRequest(BaseModel):
    """POST /{lang}/search 请求体。lang 已在 path 中，不在 body 中。"""

    model_config = ConfigDict(extra="forbid")

    q: str = Field(..., description="查询字符串（indexer 侧会先 tokenize）")
    item_type: str | None = None
    tags: list[str] | None = None
    tags_op: Literal["and", "or"] = Field("and", description="多 tag 过滤模式：and=全部匹配，or=任一匹配")
    kind: Literal["item", "event"] | None = None
    mode: Literal["exact", "semantic", "hybrid"] = "exact"
    limit: int = Field(20, ge=1, le=100)


class SearchResponse(BaseModel):
    """POST /{lang}/search 响应体。"""

    model_config = ConfigDict(extra="forbid")

    hits: list[SearchHit]
    count: int
    took_ms: float


class TagCount(BaseModel):
    """GET /{lang}/tags 的单条 tag 计数。"""

    model_config = ConfigDict(extra="forbid")

    tag: str
    count: int


class TagsResponse(BaseModel):
    """GET /{lang}/tags 响应。"""

    model_config = ConfigDict(extra="forbid")

    tags: list[TagCount]
    total: int
    took_ms: float = 0.0


class IndexRequest(BaseModel):
    """POST /{lang}/index / POST /{lang}/delete 请求体（path 相对 lang vault）。"""

    model_config = ConfigDict(extra="forbid")

    path: str = Field(..., description="相对 $workspace/memory/languages/$lang/vault 的 .md 路径")


class OkResponse(BaseModel):
    """POST /{lang}/index / POST /{lang}/delete 通用响应。"""

    model_config = ConfigDict(extra="forbid")

    ok: bool = True


class RebuildResponse(BaseModel):
    """POST /{lang}/rebuild 响应。"""

    model_config = ConfigDict(extra="forbid")

    ok: bool = True
    indexed: int
    chunks: int
    took_ms: float


class EmbedRequest(BaseModel):
    """POST /{lang}/embed 请求体。"""

    model_config = ConfigDict(extra="forbid")

    rebuild: bool = Field(False, description="True=drop vec0+embeddings，全量重嵌")
    batch: int = Field(64, ge=1, le=512, description="每批嵌入 chunk 数")
    wait: bool = Field(True, description="True=同步等到全量完成；False=fire-and-forget")


class EmbedResponse(BaseModel):
    """POST /{lang}/embed 响应。"""

    model_config = ConfigDict(extra="forbid")

    ok: bool = True
    embedded: int = Field(0, description="本次嵌入的 chunk 数（wait=False 时为 0）")
    total_chunks: int
    embedded_chunks: int
    embedding_model_id: str | None = None
    embedding_dim: int | None = None
    took_ms: float = 0.0


class LangStatus(BaseModel):
    """GET /status 中单个语言的状态信息。"""

    model_config = ConfigDict(extra="forbid")

    lang: str
    tokenizer_version: str
    docs: int
    chunks: int
    embedded_chunks: int
    embedding_model_id: str | None = None


class StatusResponse(BaseModel):
    """GET /status 响应（聚合所有 lang DB）。"""

    model_config = ConfigDict(extra="forbid")

    running: bool
    uptime_s: float
    langs: list[LangStatus]


# ── /version/*（Memory Vault 版本控制与远端备份）────────────────────


class GitCommitInfo(BaseModel):
    """git log 中的一条提交（/version/log 列表项）。"""

    model_config = ConfigDict(extra="forbid")

    hash: str
    time: str
    message: str


class VersionStatusResponse(BaseModel):
    """GET /version/status 响应。"""

    model_config = ConfigDict(extra="forbid")

    enabled: bool
    initialized: bool
    dirty: bool
    has_commits: bool
    last_commit_at: str | None = None
    last_push_at: str | None = None
    remote_configured: bool
    ahead: int
    behind: int
    branch: str
    remote_url: str


class VersionLogResponse(BaseModel):
    """GET /version/log 响应。"""

    model_config = ConfigDict(extra="forbid")

    commits: list[GitCommitInfo]


class RestoreRequest(BaseModel):
    """POST /version/restore 请求体：主机上唯一 id（commit hash 或引用）。"""

    model_config = ConfigDict(extra="forbid")

    commit_hash: str


class RestoreResponse(BaseModel):
    """POST /version/restore / POST /version/pull 响应。"""

    model_config = ConfigDict(extra="forbid")

    ok: bool
    backup_branch: str | None = None
    conflicts: list[str] = []
    message: str = ""


class VersionTestResponse(BaseModel):
    """POST /version/test 响应（远端连通性探测）。"""

    model_config = ConfigDict(extra="forbid")

    ok: bool
    message: str = ""
