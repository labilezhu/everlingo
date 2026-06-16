import logging
from pathlib import Path

from langchain_core.callbacks import BaseCallbackHandler

from .models import LoggingSetting
from .profile import load_setting

logger = logging.getLogger("everlingo")


def _get_setting() -> LoggingSetting:
    try:
        return load_setting().sys_setting.logging_setting
    except Exception:
        return LoggingSetting()


def _default_log_path() -> Path:
    return Path.home() / ".everlingo" / "logs" / "everlingo.log"


_LOG_LEVEL_MAP: dict[str, int] = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warn": logging.WARNING,
    "error": logging.ERROR,
}


def setup_logging() -> None:
    ls = _get_setting()
    log_path = Path(ls.log_file) if ls.log_file else _default_log_path()
    level_name = ls.log_level if ls.log_level in _LOG_LEVEL_MAP else "debug"
    level = _LOG_LEVEL_MAP[level_name]

    log_path.parent.mkdir(parents=True, exist_ok=True)

    handler = logging.FileHandler(str(log_path), encoding="utf-8")
    handler.setLevel(level)
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)

    root_logger = logging.getLogger("everlingo")
    root_logger.setLevel(level)
    root_logger.addHandler(handler)


class LLMLoggingHandler(BaseCallbackHandler):
    def on_llm_start(
        self, serialized: dict, prompts: list[str], **kwargs
    ) -> None:
        logger.debug("LLM Request - prompts: %s", prompts)

    def on_llm_end(self, response, **kwargs) -> None:
        logger.debug("LLM Response - %s", response)

    def on_llm_error(self, error: Exception, **kwargs) -> None:
        logger.error("LLM Error - %s", error)
