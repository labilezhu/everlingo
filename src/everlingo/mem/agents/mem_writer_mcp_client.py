# ref: docs/impl-spec/memory-writer-agent-spec.md — MCP 客户端适配
# ref: docs/impl-spec/vault-mcp/vault-mcp-spec.md — 目标 MCP Server
#
# Memory Writer Agent → Vault MCP Server 的客户端适配层。
# 用 langchain-mcp-adapters 的 MultiServerMCPClient 驱动 Streamable HTTP
# transport，按 per-entry 打开 stream，调用 session.configure 后
# 加载过滤后的 fs 工具供 LLM agent 使用。
#
# 工具清单：
#   - mcp_vault_connection(lang): 异步上下文管理器，yield (session, tools)。
#     - session: 供代码直接 call_tool（events 写入流程）。
#     - tools: 供 langchain agent（kb item 写入流程），
#       内容为 WANTED_TOOLS 子集 + mem_gen_id。
#   - mem_gen_id: 客户端纯计算 ULID 工具（MCP server spec 无此工具）。
#
# 错误约定：
#   - IndexerOfflineError: indexer 未启动 / URL 文件不存在 / 连不上 MCP server。
#   - 调用方（mem_writer_agent）捕获后丢弃 entry + logger.error 告警。

from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from langchain_core.tools import tool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools
from mcp import ClientSession

from ... import workspace

logger = logging.getLogger(__name__)


# ref: memory-writer-agent-spec.md — mem_gen_id · 类似 01JZABD123 格式
# 标准 ULID: 26 字符 Crockford base32 = 48-bit ms 时间戳 + 80-bit 随机数。
# 客户端纯计算，不经 MCP server（MCP spec tools.yaml 无此工具）。
_CROCKFORD_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


class IndexerOfflineError(RuntimeError):
    """indexer 未启动 / indexer.mcp.url 不存在 / 连不上 MCP server 时抛出。

    ref: memory-writer-agent-spec.md — 阶段 6 决策
    调用方捕获后丢弃 entry 并 logger.error 告警，不重试。
    """


def _gen_ulid() -> str:
    """生成标准 26 字符 ULID。前 10 字符 = ms 时间戳，后 16 字符 = 随机。"""
    ts_ms = int(time.time() * 1000) & 0xFFFFFFFFFFFF
    rand80 = int.from_bytes(os.urandom(10), "big")

    def _encode(num: int, length: int) -> str:
        chars = []
        for _ in range(length):
            chars.append(_CROCKFORD_ALPHABET[num & 0x1F])
            num >>= 5
        return "".join(reversed(chars))

    return _encode(ts_ms, 10) + _encode(rand80, 16)


@tool("mem_gen_id", parse_docstring=True)
def mem_gen_id() -> str:
    """生成一个 26 字符 ULID 格式的随机 id。

    用于新创建的 kb item markdown 文件名与 frontmatter id 字段，
    形如 '01JZABD123ABCDEFGHJKMNPQR'。前 10 字符 = ms 时间戳，
    后 16 字符 = 随机数。客户端纯计算，不经 MCP server。
    """
    return _gen_ulid()


# ref: memory-writer-agent-spec.md — writer 实际使用的工具子集
# MCP server 共 14 个工具；writer 只需要 fs 子集（不含 search/stat/tree/mkdir）。
# load_mcp_tools 加载全部 14 个后按名称过滤。
WANTED_TOOLS: frozenset[str] = frozenset(
    {"read", "write", "append", "delete", "ls", "find", "grep"}
)


def _read_mcp_url() -> str:
    """读 $workspace/indexer.mcp.url 文件，返回 URL。

    文件不存在 → IndexerOfflineError。
    文件存在但内容异常（非 http 开头）→ IndexerOfflineError。
    """
    url_path = workspace.indexer_mcp_url_path()
    if not url_path.exists():
        raise IndexerOfflineError(
            f"indexer.mcp.url not found at {url_path}; "
            "is the indexer process running?"
        )
    url = url_path.read_text(encoding="utf-8").strip()
    if not url.startswith("http"):
        raise IndexerOfflineError(
            f"indexer.mcp.url has invalid content: {url!r}"
        )
    return url


@asynccontextmanager
async def mcp_vault_connection(
    lang: str,
) -> AsyncIterator[tuple[ClientSession, list[Any]]]:
    """per-entry MCP stream 上下文管理器。

    用法：
        async with mcp_vault_connection(entry.lang) as (session, tools):
            # session 供代码直接 call_tool（events 写入）
            # tools 供 langchain agent（kb item 写入）

    流程：
        1. 读 $workspace/indexer.mcp.url（缺失 → IndexerOfflineError）。
        2. 创建 MultiServerMCPClient，transport=streamable_http。
        3. async with client.session("vault") 进入 stream。
        4. call_tool("session.configure", {"lang": lang})；检查 isError，
           失败抛 IndexerOfflineError（携带服务端错误文案，如
           "lang not found in workspace: xx"），不再 yield。
        5. load_mcp_tools(session) → 过滤到 WANTED_TOOLS 子集 + mem_gen_id。
        6. yield (session, tools)。
        7. 退出 with → stream 关闭。

    异常：连接失败 / 会话出错 / session.configure 失败 → 抛 IndexerOfflineError，
    由调用方丢弃 entry。
    """
    url = _read_mcp_url()
    client = MultiServerMCPClient(
        {"vault": {"transport": "http", "url": url}}
    )
    try:
        async with client.session("vault") as session:
            cfg_result = await session.call_tool(
                "session.configure", {"lang": lang}
            )
            if cfg_result.isError:
                err_text = (
                    cfg_result.content[0].text
                    if cfg_result.content
                    else "unknown error"
                )
                raise IndexerOfflineError(
                    f"session.configure failed: {err_text}"
                )
            all_tools = await load_mcp_tools(session)
            tools = [t for t in all_tools if t.name in WANTED_TOOLS] + [
                mem_gen_id
            ]
            yield session, tools
    except IndexerOfflineError:
        raise
    except (ConnectionError, OSError, TimeoutError) as e:
        # 连接类错误：indexer 未启 / 端口未监听 / 网络中断
        logger.warning("MCP connection to %s failed: %s", url, e)
        raise IndexerOfflineError(
            f"cannot reach MCP server at {url}: {e}"
        ) from e
    except Exception as e:
        # 其他错误（含 MCP 协议层错误）。indexer 启了但 session 异常
        # 也按"离线"处理，避免重试风暴；调用方决定是否重试。
        logger.warning("MCP session error: %s", e)
        raise IndexerOfflineError(
            f"MCP session error: {e}"
        ) from e
