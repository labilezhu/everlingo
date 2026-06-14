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
