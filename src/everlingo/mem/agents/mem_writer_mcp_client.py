# ref: docs/impl-spec/memory-writer-agent-spec.md — MCP 客户端适配
# ref: docs/impl-spec/vault-mcp/vault-mcp-spec.md — 目标 MCP Server
#
# Memory Writer Agent → Vault MCP Server 的客户端适配层。
# 用 langchain-mcp-adapters 的 MultiServerMCPClient 驱动 Streamable HTTP
# transport，按 per-entry 打开 stream，调用 session.configure 后
# 加载过滤后的 fs 工具供 LLM agent 使用。
# ulid 生成走 MCP Server 的 gen_id 工具（workspace 级，豁免 configure）。
#
# 工具清单：
#   - mcp_vault_connection(lang): 异步上下文管理器，yield (session, tools)。
#     - session: 供代码直接 call_tool（events 写入流程）。
#     - tools: 供 langchain agent（kb item 写入流程），
#       内容为 WANTED_TOOLS 子集（含 vault_mcp_gen_id）。
#
# 错误约定：
#   - IndexerOfflineError: indexer 未启动 / URL 文件不存在 / 连不上 MCP server。
#   - 调用方（mem_writer_agent）捕获后丢弃 entry + logger.error 告警。

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools
from mcp import ClientSession

from ... import workspace

logger = logging.getLogger(__name__)


class IndexerOfflineError(RuntimeError):
    """indexer 未启动 / indexer.mcp.url 不存在 / 连不上 MCP server 时抛出。

    ref: memory-writer-agent-spec.md — 阶段 6 决策
    调用方捕获后丢弃 entry 并 logger.error 告警，不重试。
    """


# ref: memory-writer-agent-spec.md — writer 实际使用的工具子集
# MCP server 共 15 个工具；writer 只需要 fs 子集 + gen_id。
# load_mcp_tools 加载全部 15 个后按名称过滤。
WANTED_TOOLS: frozenset[str] = frozenset(
    {"vault_mcp_read", "vault_mcp_write", "vault_mcp_append", "vault_mcp_delete", "vault_mcp_ls", "vault_mcp_find", "vault_mcp_search", "vault_mcp_grep", "vault_mcp_gen_id", "vault_mcp_list_tags"}
)


# ref: docs/impl-spec/chat-agent-spec.md — Chat Agent 只读工具子集
# Chat Agent 不需要写 vault（由 Chat Agent 构造 entries 后 Writer 异步完成），
# 所以只加载 search / fs 只读工具子集 + grep / find 搜索。
CHAT_AGENT_WANTED_TOOLS: frozenset[str] = frozenset(
    {"vault_mcp_read", "vault_mcp_ls", "vault_mcp_find", "vault_mcp_search", "vault_mcp_grep", "vault_mcp_list_tags"}
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
    wanted_tools: frozenset[str] | None = None,
) -> AsyncIterator[tuple[ClientSession, list[Any]]]:
    """per-entry MCP stream 上下文管理器。

    用法：
        async with mcp_vault_connection(entry.lang) as (session, tools):
            # session 供代码直接 call_tool（events 写入）
            # tools 供 langchain agent（kb item 写入）

    参数：
        lang: 目标语言代码。
        wanted_tools: 要加载的工具名子集。默认 WANTED_TOOLS（writer 全功能）。
            Chat Agent 传入 CHAT_AGENT_WANTED_TOOLS（只读子集）。

    流程：
        1. 读 $workspace/indexer.mcp.url（缺失 → IndexerOfflineError）。
        2. 创建 MultiServerMCPClient，transport=streamable_http。
        3. async with client.session("vault") 进入 stream。
        4. call_tool("session.configure", {"lang": lang})；检查 isError，
           失败抛 IndexerOfflineError（携带服务端错误文案，如
           "lang not found in workspace: xx"），不再 yield。
         5. load_mcp_tools(session) → 过滤到 WANTED_TOOLS 子集（含 vault_mcp_gen_id）。
         6. yield (session, tools)。
        7. 退出 with → stream 关闭。

    异常：连接失败 / 会话出错 / session.configure 失败 → 抛 IndexerOfflineError，
    由调用方丢弃 entry。
    """
    url = _read_mcp_url()
    client = MultiServerMCPClient(
        {"vault_mcp": {"transport": "http", "url": url}}
    )
    try:
        async with client.session("vault_mcp") as session:
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
            all_tools = await load_mcp_tools(session=session, server_name="vault_mcp", tool_name_prefix=True)
            tool_filter = wanted_tools if wanted_tools is not None else WANTED_TOOLS
            tools = [t for t in all_tools if t.name in tool_filter]
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


async def _call_compile_prompt(session, path: str) -> str:
    """在已有 MCP session 上调用 compile_prompt 工具，返回包含 include 展开后的编译文本。

    复用已打开的 session，无需额外建立 MCP 连接。
    编译失败（server 返回 isError）时抛出 RuntimeError，由调用方处理。
    """
    result = await session.call_tool(
        "compile_prompt", {"path": path}
    )
    if result.isError:
        err_text = (
            result.content[0].text
            if result.content
            else "compile_prompt returned isError"
        )
        raise RuntimeError(
            f"compile_prompt {path} failed: {err_text}"
        )
    data = result.structuredContent or {}
    return data.get("content", "")
