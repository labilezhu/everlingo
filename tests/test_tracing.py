from unittest.mock import patch

from everlingo.models import EverLingoSetting, TracingSetting


def test_setup_tracing_returns_none_when_service_empty(monkeypatch):
    monkeypatch.setattr(
        "everlingo.tracing.load_setting",
        lambda: EverLingoSetting(tracing_setting=TracingSetting()),
    )
    from everlingo.tracing import setup_tracing

    assert setup_tracing() is None


def test_setup_tracing_returns_none_when_unknown_service(monkeypatch):
    monkeypatch.setattr(
        "everlingo.tracing.load_setting",
        lambda: EverLingoSetting(
            tracing_setting=TracingSetting(tracing_service="unknown")
        ),
    )
    from everlingo.tracing import setup_tracing

    assert setup_tracing() is None


def test_setup_tracing_langfuse_missing_keys(monkeypatch):
    monkeypatch.setattr(
        "everlingo.tracing.load_setting",
        lambda: EverLingoSetting(
            tracing_setting=TracingSetting(tracing_service="langfuse")
        ),
    )
    from everlingo.tracing import setup_tracing

    assert setup_tracing() is None


def test_setup_tracing_langfuse_success(monkeypatch):
    monkeypatch.setattr(
        "everlingo.tracing.load_setting",
        lambda: EverLingoSetting(
            tracing_setting=TracingSetting(
                tracing_service="langfuse",
                langfuse_secret_key="sk-lf-test",
                langfuse_public_key="pk-lf-test",
                langfuse_base_url="http://localhost:3300",
            )
        ),
    )
    mock_handler = object()
    with patch("langfuse.langchain.CallbackHandler", return_value=mock_handler):
        from everlingo.tracing import setup_tracing

        result = setup_tracing()
        assert result is mock_handler


def test_setup_tracing_langfuse_no_base_url(monkeypatch):
    monkeypatch.setattr(
        "everlingo.tracing.load_setting",
        lambda: EverLingoSetting(
            tracing_setting=TracingSetting(
                tracing_service="langfuse",
                langfuse_secret_key="sk-lf-test",
                langfuse_public_key="pk-lf-test",
            )
        ),
    )
    mock_handler = object()
    with patch("langfuse.langchain.CallbackHandler", return_value=mock_handler) as m:
        from everlingo.tracing import setup_tracing

        result = setup_tracing()
        assert result is mock_handler
        assert m.call_args[1]["host"] is None
