import logging
import tempfile
from pathlib import Path

import pytest
from everlingo.log_utils import LLMLoggingHandler, _LOG_LEVEL_MAP, setup_logging
from everlingo.models import EverLingoSetting, LoggingSetting, SysSetting, UserProfile


@pytest.fixture(autouse=True)
def _cleanup_everlingo_handlers():
    yield
    root = logging.getLogger("everlingo")
    root.handlers.clear()


def test_loglevel_map_contains_all_levels():
    assert "debug" in _LOG_LEVEL_MAP
    assert "info" in _LOG_LEVEL_MAP
    assert "warn" in _LOG_LEVEL_MAP
    assert "error" in _LOG_LEVEL_MAP
    assert _LOG_LEVEL_MAP["debug"] == logging.DEBUG
    assert _LOG_LEVEL_MAP["info"] == logging.INFO
    assert _LOG_LEVEL_MAP["error"] == logging.ERROR


def test_setup_logging_creates_log_file(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        log_file = Path(tmpdir) / "test.log"
        monkeypatch.setattr(
            "everlingo.log_utils._get_setting",
            lambda: LoggingSetting(log_file=str(log_file), log_level="debug"),
        )
        setup_logging()
        assert log_file.exists()


def test_setup_logging_custom_loglevel(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setattr(
            "everlingo.log_utils._get_setting",
            lambda: LoggingSetting(log_file=str(Path(tmpdir) / "test.log"), log_level="error"),
        )
        setup_logging()
        logger = logging.getLogger("everlingo")
        assert logger.level == logging.ERROR


def test_setup_logging_format(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        log_file = Path(tmpdir) / "test.log"
        monkeypatch.setattr(
            "everlingo.log_utils._get_setting",
            lambda: LoggingSetting(log_file=str(log_file), log_level="debug"),
        )
        setup_logging()
        child_logger = logging.getLogger("everlingo.tests.child")
        child_logger.info("hello world")
        for h in logging.getLogger("everlingo").handlers:
            h.flush()
        line = log_file.read_text(encoding="utf-8").strip().splitlines()[-1]
        import re
        pattern = (
            r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3} "
            r"\[INFO\] \[\d+\] \[MainThread\] \[test_log_utils\] \[everlingo\.tests\.child\] : hello world$"
        )
        assert re.match(pattern, line), f"unexpected format: {line!r}"


def test_llm_logging_handler_start_logs_debug(caplog):
    caplog.set_level(logging.DEBUG, logger="everlingo")
    handler = LLMLoggingHandler()
    handler.on_llm_start({}, ["test prompt"])
    assert "LLM Request" in caplog.text
    assert "test prompt" in caplog.text


def test_llm_logging_handler_end_logs_debug(caplog):
    caplog.set_level(logging.DEBUG, logger="everlingo")
    handler = LLMLoggingHandler()
    handler.on_llm_end("fake response")
    assert "LLM Response" in caplog.text


def test_llm_logging_handler_error_logs_error(caplog):
    caplog.set_level(logging.ERROR, logger="everlingo")
    handler = LLMLoggingHandler()
    handler.on_llm_error(ValueError("test error"))
    assert "LLM Error" in caplog.text
    assert "test error" in caplog.text
