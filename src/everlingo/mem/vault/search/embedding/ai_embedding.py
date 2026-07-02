"""本项目用的 Embedding 封装，基于 langchain OpenAIEmbeddings。

OpenRouter 作为 OpenAI 兼容 provider 提供 embedding 端点（如
openai/text-embedding-3-small）。本类复用 OPENAI_API_KEY / OPENAI_BASE_URL
配置 embedding 请求。子类继承 OpenAIEmbeddings，可直接用于 langchain
VectorStore（embed_query / embed_documents 协议已满足）。

OpenRouter 兼容要点：
- 关闭 tiktoken 编码检查（`tiktoken_enabled=False`、
  `check_embedding_ctx_length=False`），非 OpenAI provider 上
  tiktoken 编码会抛 ValueError。
"""

from __future__ import annotations

from langchain_openai import OpenAIEmbeddings

from everlingo.config import get_llm_config


class AIEmbedding(OpenAIEmbeddings):
    """项目专用 Embedding，OpenRouter provider 适配。

    实例可直接传给 langchain VectorStore（如 PGVector / FAISS / Chroma）。
    """

    @classmethod
    def create(cls) -> "AIEmbedding":
        """基于项目配置构造 AIEmbedding。

        行为：
        - 复用 ``OPENAI_API_KEY`` / ``OPENAI_BASE_URL`` 走 OpenRouter。
        - 若 ``OPENAI_EMBEDDING_MODEL`` 未配置，抛 ``ValueError``。
        - 强制 ``tiktoken_enabled=False`` 与 ``check_embedding_ctx_length=False``
          以兼容非 OpenAI provider（OpenRouter 上 tiktoken 编码会失败）。
        """
        cfg = get_llm_config()
        embedding_model: str = cfg["embedding_model"]
        if not embedding_model:
            raise ValueError(
                "OPENAI_EMBEDDING_MODEL 未设置。"
                "请在 .env 或 $workspace/everlingo.yaml 的 "
                "sys_setting.openai_embedding_model 中配置 embedding 模型名"
                "（如 openai/text-embedding-3-small）。"
            )
        return cls(
            model=embedding_model,
            openai_api_key=cfg["api_key"],
            openai_api_base=cfg["base_url"],
            tiktoken_enabled=False,
            check_embedding_ctx_length=False,
        )
