from collections.abc import Sequence

from langchain.agents import create_agent as _create_agent
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI

from .config import get_llm_config
from .log_utils import LLMLoggingHandler
from .tracing import setup_tracing


def create_llm() -> ChatOpenAI:
    cfg = get_llm_config()
    callbacks = [LLMLoggingHandler()]
    langfuse_handler = setup_tracing()
    if langfuse_handler:
        callbacks.append(langfuse_handler)
    return ChatOpenAI(
        api_key=cfg["api_key"],
        base_url=cfg["base_url"],
        model=cfg["model"],
        temperature=0.7,
        callbacks=callbacks,
    )


def create_extract_llm() -> ChatOpenAI:
    """Memory Extract Agent 专用 LLM 工厂。

    ref: docs/impl-spec/memory-extract-agent-spec.md — 已知简化 / 待评估
    抽取任务要求结构化、确定性输出，temperature=0 避免 0.7 带来的字段漂移；
    其余配置与 create_llm() 一致（同 model / callbacks / tracing）。
    """
    cfg = get_llm_config()
    callbacks = [LLMLoggingHandler()]
    langfuse_handler = setup_tracing()
    if langfuse_handler:
        callbacks.append(langfuse_handler)
    return ChatOpenAI(
        api_key=cfg["api_key"],
        base_url=cfg["base_url"],
        model=cfg["model"],
        temperature=0,
        callbacks=callbacks,
    )

def create_mem_writer_llm() -> ChatOpenAI:
    cfg = get_llm_config()
    callbacks = [LLMLoggingHandler()]
    langfuse_handler = setup_tracing()
    if langfuse_handler:
        callbacks.append(langfuse_handler)
    return ChatOpenAI(
        api_key=cfg["api_key"],
        base_url=cfg["base_url"],
        model=cfg["model"],
        temperature=0,
        callbacks=callbacks,
    )

def create_agent(
    llm: ChatOpenAI,
    tools: Sequence[BaseTool] = (),
    system_prompt: str = "",
) -> "CompiledStateGraph":
    return _create_agent(model=llm, tools=list(tools), system_prompt=system_prompt)
