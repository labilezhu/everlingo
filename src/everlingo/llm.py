from collections.abc import Sequence

from langchain.agents import create_agent as _create_agent
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI

from .config import get_llm_config


def create_llm() -> ChatOpenAI:
    cfg = get_llm_config()
    return ChatOpenAI(
        api_key=cfg["api_key"],
        base_url=cfg["base_url"],
        model=cfg["model"],
        temperature=0.7,
    )


def create_agent(
    llm: ChatOpenAI,
    tools: Sequence[BaseTool] = (),
    system_prompt: str = "",
) -> "CompiledStateGraph":
    return _create_agent(model=llm, tools=list(tools), system_prompt=system_prompt)
