import logging
import sys
from pathlib import Path

from langchain_core.callbacks import BaseCallbackHandler

from . import workspace
from .models import LoggingSetting
from .setting import load_setting

logger = logging.getLogger(__name__)


def _get_setting() -> LoggingSetting:
    try:
        return load_setting().sys_setting.logging_setting
    except Exception:
        return LoggingSetting()


def _default_log_path() -> Path:
    # ref: docs/impl-spec/worksplace/workspace.md — workspace 日志路径
    return workspace.log_path()


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

    formatter = logging.Formatter(
        "%(asctime)s.%(msecs)03d [%(levelname)s] [%(thread)d] [%(threadName)s] "
        "[%(module)s] [%(name)s] : %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root_logger = logging.getLogger("everlingo")
    root_logger.setLevel(level)

    # 按 handler 类型幂等去重：重复调用 setup_logging 不叠加同类型 handler。
    # FileHandler 是 StreamHandler 子类，判空需先排除文件 handler。
    has_file = any(isinstance(h, logging.FileHandler) for h in root_logger.handlers)
    has_stdout = any(
        isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
        for h in root_logger.handlers
    )

    if not has_file:
        handler = logging.FileHandler(str(log_path), encoding="utf-8")
        handler.setLevel(level)
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)

    if not has_stdout:
        stdout_handler = logging.StreamHandler(sys.stdout)
        stdout_handler.setLevel(level)
        stdout_handler.setFormatter(formatter)
        root_logger.addHandler(stdout_handler)


class LLMLoggingHandler(BaseCallbackHandler):
    def on_llm_start(
        self, serialized: dict, prompts: list[str], **kwargs
    ) -> None:
        logger.debug("LLM Request - prompts: %s", prompts)

    def on_llm_end(self, response, **kwargs) -> None:
        logger.debug("LLM Response - %s", response)

    def on_llm_error(self, error: Exception, **kwargs) -> None:
        logger.error("LLM Error - %s", error)
