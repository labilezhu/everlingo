import os
from dotenv import load_dotenv

from .profile import load_setting

load_dotenv()


def get_llm_config() -> dict:
    setting = load_setting()
    ss = setting.sys_setting

    api_key = ss.openai_api_key or os.getenv("OPENAI_API_KEY", "")
    base_url = ss.openai_base_url or os.getenv("OPENAI_BASE_URL", "")
    model = ss.openai_model or os.getenv("OPENAI_MODEL", "")

    if not api_key:
        raise ValueError(
            "OPENAI_API_KEY 未设置。"
            "请复制 .env.example 为 .env 并填入 API Key，"
            "或在 ~/.everlingo/everlingo.yaml 的 sys_setting.openai_api_key 中配置。"
        )

    return {
        "api_key": api_key,
        "base_url": base_url or "https://openrouter.ai/api/v1",
        "model": model or "gpt-3.5-turbo",
    }
