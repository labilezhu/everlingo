import json
import logging
from collections.abc import Sequence

import httpx
from langchain.agents import create_agent as _create_agent
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI

from .config import get_llm_config
from .log_utils import LLMLoggingHandler
from .tracing import setup_tracing

logger = logging.getLogger(__name__)


async def _log_malformed_async_response(response: httpx.Response) -> None:
    try:
        await response.aread()
        body = response.content
        try:
            json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            logger.warning(
                "LLM non-JSON response [status=%s]: %.500s",
                response.status_code,
                body[:500],
            )
    except Exception:
        logger.debug("LLM response hook error", exc_info=True)


def _log_malformed_sync_response(response: httpx.Response) -> None:
    try:
        response.read()
        body = response.content
        try:
            json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            logger.warning(
                "LLM non-JSON response [status=%s]: %.500s",
                response.status_code,
                body[:500],
            )
    except Exception:
        logger.debug("LLM response hook error", exc_info=True)


_HOOKS = {"response": [_log_malformed_sync_response]}
_ASYNC_HOOKS = {"response": [_log_malformed_async_response]}


def _build_llm(**kwargs: object) -> ChatOpenAI:
    cfg = get_llm_config()
    callbacks = [LLMLoggingHandler()]
    langfuse_handler = setup_tracing()
    if langfuse_handler:
        callbacks.append(langfuse_handler)
    return ChatOpenAI(
        api_key=cfg["api_key"],
        base_url=cfg["base_url"],
        model=cfg["model"],
        callbacks=callbacks,
        http_client=httpx.Client(event_hooks=_HOOKS),
        http_async_client=httpx.AsyncClient(event_hooks=_ASYNC_HOOKS),
        **kwargs,
    )


def create_llm() -> ChatOpenAI:
    return _build_llm(temperature=0.7)


def create_extract_llm() -> ChatOpenAI:
    """Memory Extract Agent 专用 LLM 工厂。

    ref: docs/impl-spec/memory-extract-agent-spec.md — 已知简化 / 待评估
    抽取任务要求结构化、确定性输出，temperature=0 避免 0.7 带来的字段漂移；
    其余配置与 create_llm() 一致（同 model / callbacks / tracing）。
    """
    return _build_llm(temperature=0)


def create_mem_writer_llm() -> ChatOpenAI:
    return _build_llm(temperature=0)


def create_agent(
    llm: ChatOpenAI,
    tools: Sequence[BaseTool] = (),
    system_prompt: str = "",
) -> "CompiledStateGraph":
    return _create_agent(model=llm, tools=list(tools), system_prompt=system_prompt)
