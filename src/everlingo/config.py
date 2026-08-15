import os
from dotenv import load_dotenv

from .setting import load_setting

load_dotenv()


def get_llm_config() -> dict:
    setting = load_setting()
    ss = setting.sys_setting

    api_key = ss.openai_api_key or os.getenv("OPENAI_API_KEY", "")
    base_url = ss.openai_base_url or os.getenv("OPENAI_BASE_URL", "")
    model = ss.openai_model or os.getenv("OPENAI_MODEL", "")
    embedding_model = (
        ss.openai_embedding_model or os.getenv("OPENAI_EMBEDDING_MODEL", "")
    )

    if not api_key:
        raise ValueError(
            "OPENAI_API_KEY 未设置。"
            "请复制 .env.example 为 .env 并填入 API Key，"
            "或在 $workspace/everlingo.yaml 的 sys_setting.openai_api_key 中配置。"
        )

    return {
        "api_key": api_key,
        "base_url": base_url or "https://openrouter.ai/api/v1",
        "model": model or "gpt-3.5-turbo",
        "embedding_model": embedding_model,
    }


def get_vision_llm_config() -> dict:
    """Vision Service 使用的 LLM 配置。

    ref: docs/ADR/20260812-image-chat.md §19 — 与 chat LLM 复用 OpenRouter
    api_key / base_url，仅 model 独立（默认 xiaomi/mimo-v2.5）。
    优先级：setting.sys_setting.vision_model > env VISION_MODEL > 默认值。
    """
    setting = load_setting()
    ss = setting.sys_setting
    api_key = ss.openai_api_key or os.getenv("OPENAI_API_KEY", "")
    base_url = ss.openai_base_url or os.getenv("OPENAI_BASE_URL", "")
    vision_model = (
        getattr(ss, "vision_model", None) or os.getenv("VISION_MODEL") or "xiaomi/mimo-v2.5"
    )
    return {
        "api_key": api_key,
        "base_url": base_url or "https://openrouter.ai/api/v1",
        "model": vision_model,
    }
