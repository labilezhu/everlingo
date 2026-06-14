import os
from dotenv import load_dotenv

load_dotenv()


def get_llm_config() -> dict:
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        raise ValueError(
            "OPENAI_API_KEY 未设置。"
            "请复制 .env.example 为 .env 并填入 API Key，"
            "或通过环境变量注入。"
        )
    return {
        "api_key": api_key,
        "base_url": os.getenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1"),
        "model": os.getenv("OPENAI_MODEL", "gpt-3.5-turbo"),
    }
