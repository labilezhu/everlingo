from unittest.mock import MagicMock, patch

from everlingo.models import EverLingoSetting, SysSetting, TracingSetting


def test_setup_tracing_returns_none_when_service_empty(monkeypatch):
    monkeypatch.setattr(
        "everlingo.tracing.load_setting",
        lambda: EverLingoSetting(sys_setting=SysSetting(tracing_setting=TracingSetting())),
    )
    from everlingo.tracing import setup_tracing

    assert setup_tracing() is None


def test_setup_tracing_returns_none_when_unknown_service(monkeypatch):
    monkeypatch.setattr(
        "everlingo.tracing.load_setting",
        lambda: EverLingoSetting(
            sys_setting=SysSetting(
                tracing_setting=TracingSetting(tracing_service="unknown")
            )
        ),
    )
    from everlingo.tracing import setup_tracing

    assert setup_tracing() is None


def test_setup_tracing_langfuse_missing_keys(monkeypatch):
    monkeypatch.setattr(
        "everlingo.tracing.load_setting",
        lambda: EverLingoSetting(
            sys_setting=SysSetting(
                tracing_setting=TracingSetting(tracing_service="langfuse")
            )
        ),
    )
    from everlingo.tracing import setup_tracing

    assert setup_tracing() is None


def test_setup_tracing_langfuse_success(monkeypatch):
    monkeypatch.setattr(
        "everlingo.tracing.load_setting",
        lambda: EverLingoSetting(
            sys_setting=SysSetting(
                tracing_setting=TracingSetting(
                    tracing_service="langfuse",
                    langfuse_secret_key="sk-lf-test",
                    langfuse_public_key="pk-lf-test",
                    langfuse_base_url="http://localhost:3300",
                )
            )
        ),
    )
    mock_handler = object()
    # Langfuse 4.x: 凭证传入 langfuse.Langfuse()，CallbackHandler() 无参数
    with patch("langfuse.Langfuse") as mock_lf, \
         patch("langfuse.langchain.CallbackHandler", return_value=mock_handler):
        from everlingo.tracing import setup_tracing

        result = setup_tracing()
        assert result is mock_handler
        mock_lf.assert_called_once_with(
            secret_key="sk-lf-test",
            public_key="pk-lf-test",
            host="http://localhost:3300",
        )


def test_setup_tracing_langfuse_no_base_url(monkeypatch):
    monkeypatch.setattr(
        "everlingo.tracing.load_setting",
        lambda: EverLingoSetting(
            sys_setting=SysSetting(
                tracing_setting=TracingSetting(
                    tracing_service="langfuse",
                    langfuse_secret_key="sk-lf-test",
                    langfuse_public_key="pk-lf-test",
                )
            )
        ),
    )
    mock_handler = object()
    # base_url 为空时，host 应传 None
    with patch("langfuse.Langfuse") as mock_lf, \
         patch("langfuse.langchain.CallbackHandler", return_value=mock_handler):
        from everlingo.tracing import setup_tracing

        result = setup_tracing()
        assert result is mock_handler
        assert mock_lf.call_args[1]["host"] is None
