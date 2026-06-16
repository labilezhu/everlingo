import logging

from .profile import load_setting

logger = logging.getLogger("everlingo")


def setup_tracing():
    setting = load_setting()
    ts = setting.tracing_setting

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

        handler = CallbackHandler(
            secret_key=ts.langfuse_secret_key,
            public_key=ts.langfuse_public_key,
            host=ts.langfuse_base_url or None,
        )
        logger.info("Langfuse tracing enabled")
        return handler

    logger.warning("unknown tracing_service: %s", ts.tracing_service)
    return None
