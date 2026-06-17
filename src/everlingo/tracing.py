import logging

from .setting import load_setting

logger = logging.getLogger("everlingo")


def setup_tracing():
    setting = load_setting()
    ts = setting.sys_setting.tracing_setting

    if not ts.tracing_service:
        return None

    if ts.tracing_service == "langfuse":
        try:
            from langfuse.langchain import CallbackHandler
        except ImportError:
            logger.warning("langfuse not installed, tracing disabled")
            return None

        if not ts.langfuse_secret_key or not ts.langfuse_public_key:
            logger.warning("langfuse secret/public key not configured, tracing disabled")
            return None

        try:
            import langfuse
        except ImportError:
            logger.warning("langfuse not installed, tracing disabled")
            return None

        # Langfuse 4.x: 初始化 client 以配置 OTEL exporter，凭证通过此处传入
        langfuse.Langfuse(
            secret_key=ts.langfuse_secret_key,
            public_key=ts.langfuse_public_key,
            host=ts.langfuse_base_url or None,
        )
        # CallbackHandler 在 4.x 中无需再传凭证
        handler = CallbackHandler()
        logger.info("Langfuse tracing enabled")
        return handler

    logger.warning("unknown tracing_service: %s", ts.tracing_service)
    return None
