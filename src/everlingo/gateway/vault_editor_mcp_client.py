from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from langchain_mcp_adapters.client import MultiServerMCPClient
from mcp import ClientSession

from everlingo.mem.agents.mem_writer_mcp_client import IndexerOfflineError, _read_mcp_url

logger = logging.getLogger(__name__)


@asynccontextmanager
async def mcp_session_configured(
    lang: str, interface_language: str | None = None
) -> AsyncIterator[ClientSession]:
    url = _read_mcp_url()
    client = MultiServerMCPClient(
        {"vault_mcp": {"transport": "http", "url": url}}
    )
    try:
        async with client.session("vault_mcp") as session:
            cfg_args: dict[str, Any] = {"lang": lang}
            if interface_language:
                cfg_args["interface_language"] = interface_language
            cfg_result = await session.call_tool("session.configure", cfg_args)
            if cfg_result.isError:
                err_text = (
                    cfg_result.content[0].text
                    if cfg_result.content
                    else "unknown error"
                )
                raise RuntimeError(f"session.configure failed: {err_text}")
            yield session
    except IndexerOfflineError:
        raise
    except (ConnectionError, OSError, TimeoutError) as e:
        logger.warning("MCP connection to %s failed: %s", url, e)
        raise IndexerOfflineError(f"cannot reach MCP server at {url}: {e}") from e
    except RuntimeError:
        raise
    except Exception as e:
        logger.warning("MCP session error: %s", e)
        raise IndexerOfflineError(f"MCP session error: {e}") from e


@asynccontextmanager
async def mcp_session_workspace() -> AsyncIterator[ClientSession]:
    url = _read_mcp_url()
    client = MultiServerMCPClient(
        {"vault_mcp": {"transport": "http", "url": url}}
    )
    try:
        async with client.session("vault_mcp") as session:
            yield session
    except IndexerOfflineError:
        raise
    except (ConnectionError, OSError, TimeoutError) as e:
        logger.warning("MCP connection to %s failed: %s", url, e)
        raise IndexerOfflineError(f"cannot reach MCP server at {url}: {e}") from e
    except Exception as e:
        logger.warning("MCP session error: %s", e)
        raise IndexerOfflineError(f"MCP session error: {e}") from e
