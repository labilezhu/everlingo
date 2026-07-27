import pytest
from pydantic import ValidationError

from everlingo.gateway.channels.envelope import (
    UserInputEnvelope,
    SourcePlain,
    SourceWeb,
    SourceChromeExt,
    ResourceContextVaultFile,
    ResourceContextWebPage,
    ResourceContextSelectedText,
    render_envelope_to_message_text,
    wrap_plain_text,
)


class TestWrapPlainText:
    def test_wraps_plain_text(self):
        env = wrap_plain_text("hello")
        assert env.task == "none"
        assert env.chat.message == "hello"
        assert isinstance(env.source, SourcePlain)
        assert env.chat_context.resource_contexts == []
        assert env.schema_version == 1

    def test_wraps_empty_text(self):
        env = wrap_plain_text("")
        assert env.chat.message == ""

    def test_wraps_json_looking_text(self):
        env = wrap_plain_text('{"name":"mark"}')
        assert env.chat.message == '{"name":"mark"}'
        assert isinstance(env.source, SourcePlain)


class TestRenderEnvelopeToMessageText:
    def test_renders_tagged_json(self):
        env = wrap_plain_text("hello")
        rendered = render_envelope_to_message_text(env)
        assert rendered.startswith("<envelope>\n")
        assert rendered.endswith("\n</envelope>")
        assert '"task":"none"' in rendered
        assert '"message":"hello"' in rendered

    def test_rich_envelope_roundtrip(self):
        env = UserInputEnvelope(
            task="translate",
            source=SourceWeb(url="https://example.com", title="Example"),
        )
        env.chat.message = "为什么这里不是银行？"
        env.chat_context.resource_contexts = [
            ResourceContextSelectedText(
                text="bank",
                paragraph_text="I sat on the bank of the river.",
            ),
        ]

        rendered = render_envelope_to_message_text(env)
        assert '"task":"translate"' in rendered
        assert '为什么这里不是银行' in rendered
        assert '"text":"bank"' in rendered
        assert '"kind":"web"' in rendered
        assert '"url":"https://example.com"' in rendered
        assert '"paragraph_text"' in rendered
        assert '"resource_contexts"' in rendered

    def test_schema_version_present(self):
        env = wrap_plain_text("hi")
        rendered = render_envelope_to_message_text(env)
        assert '"schema_version":1' in rendered


class TestSourceTaggedUnion:
    def test_plain_source_default(self):
        env = wrap_plain_text("hello")
        assert env.source.kind == "plain"
        assert isinstance(env.source, SourcePlain)

    def test_web_source(self):
        env = UserInputEnvelope(source=SourceWeb(url="http://test.com"))
        assert env.source.kind == "web"
        assert env.source.url == "http://test.com"

    def test_web_source_default_surface(self):
        env = UserInputEnvelope(source=SourceWeb(url="http://test.com"))
        assert env.source.surface == "fullscreen"

    def test_web_source_explicit_surface(self):
        env = UserInputEnvelope(source=SourceWeb(url="http://test.com"))
        assert env.source.surface == "fullscreen"
        # sidecar was moved to SourceChromeExt
        with pytest.raises(ValidationError):
            SourceWeb(url="http://test.com", surface="sidecar")

    def test_web_source_invalid_surface_raises(self):
        with pytest.raises(ValidationError):
            SourceWeb(url="http://test.com", surface="full_page")

    def test_unknown_kind_raises(self):
        with pytest.raises(ValidationError):
            UserInputEnvelope(source={"kind": "unknown"})


class TestSourceChromeExt:
    def test_chrome_ext_kind(self):
        env = UserInputEnvelope(source=SourceChromeExt(url="http://example.com"))
        assert env.source.kind == "chrome_ext"

    def test_chrome_ext_default_surface(self):
        env = UserInputEnvelope(source=SourceChromeExt(url="http://example.com"))
        assert env.source.surface == "sidecar"

    def test_chrome_ext_explicit_surface_sidecar(self):
        env = UserInputEnvelope(
            source=SourceChromeExt(url="http://test.com", surface="sidecar")
        )
        assert env.source.surface == "sidecar"

    def test_chrome_ext_explicit_surface_popup(self):
        env = UserInputEnvelope(
            source=SourceChromeExt(url="http://test.com", surface="popup")
        )
        assert env.source.surface == "popup"

    def test_chrome_ext_rejects_fullscreen(self):
        with pytest.raises(ValidationError):
            SourceChromeExt(url="http://test.com", surface="fullscreen")

    def test_chrome_ext_invalid_surface_raises(self):
        with pytest.raises(ValidationError):
            SourceChromeExt(url="http://test.com", surface="invalid")

    def test_chrome_ext_url_and_title(self):
        env = UserInputEnvelope(
            source=SourceChromeExt(url="https://example.com", title="Test Page")
        )
        assert env.source.url == "https://example.com"
        assert env.source.title == "Test Page"


class TestUserInputEnvelopeDefaults:
    def test_all_defaults(self):
        env = UserInputEnvelope()
        assert env.task == "none"
        assert env.chat.message == ""
        assert env.chat_context.resource_contexts == []
        assert isinstance(env.source, SourcePlain)
        assert env.device is None
        assert env.schema_version == 1

    def test_task_is_literal(self):
        for t in ("translate", "look_up", "none"):
            env = UserInputEnvelope(task=t)
            assert env.task == t

    def test_invalid_task_raises(self):
        with pytest.raises(ValidationError):
            UserInputEnvelope(task="summarize")


class TestDevicePart:
    def test_device_none_by_default(self):
        env = UserInputEnvelope()
        assert env.device is None

    def test_device_with_fields(self):
        from everlingo.gateway.channels.envelope import DevicePart

        env = UserInputEnvelope(
            device=DevicePart(platform="chrome_ext", locale="zh-CN")
        )
        assert env.device is not None
        assert env.device.platform == "chrome_ext"
        assert env.device.locale == "zh-CN"


class TestChatContext:
    def test_resource_contexts_defaults_to_empty(self):
        env = UserInputEnvelope()
        assert env.chat_context.resource_contexts == []

    def test_vault_file_context(self):
        env = UserInputEnvelope(
            chat_context={
                "resource_contexts": [
                    {"kind": "vault_file", "file_path": "items/vocab/embedding.md"},
                ],
            },
        )
        ctx = env.chat_context.resource_contexts[0]
        assert isinstance(ctx, ResourceContextVaultFile)
        assert ctx.file_path == "items/vocab/embedding.md"

    def test_web_page_context(self):
        env = UserInputEnvelope(
            chat_context={
                "resource_contexts": [
                    {"kind": "web_page", "url": "https://example.com", "title": "Test"},
                ],
            },
        )
        ctx = env.chat_context.resource_contexts[0]
        assert isinstance(ctx, ResourceContextWebPage)
        assert ctx.url == "https://example.com"
        assert ctx.title == "Test"

    def test_selected_text_context_with_all_fields(self):
        env = UserInputEnvelope(
            chat_context={
                "resource_contexts": [
                    {
                        "kind": "selected_text",
                        "text": "bank",
                        "start_line": 5,
                        "start_column": 10,
                        "paragraph_text": "I sat on the bank of the river.",
                    },
                ],
            },
        )
        ctx = env.chat_context.resource_contexts[0]
        assert isinstance(ctx, ResourceContextSelectedText)
        assert ctx.text == "bank"
        assert ctx.start_line == 5
        assert ctx.start_column == 10
        assert ctx.paragraph_text == "I sat on the bank of the river."

    def test_selected_text_with_nulls(self):
        env = UserInputEnvelope(
            chat_context={
                "resource_contexts": [
                    {
                        "kind": "selected_text",
                        "text": "word",
                    },
                ],
            },
        )
        ctx = env.chat_context.resource_contexts[0]
        assert ctx.text == "word"
        assert ctx.start_line is None
        assert ctx.start_column is None
        assert ctx.paragraph_text is None

    def test_multiple_contexts(self):
        env = UserInputEnvelope(
            chat_context={
                "resource_contexts": [
                    {"kind": "vault_file", "file_path": "items/vocab/foo.md"},
                    {"kind": "selected_text", "text": "hello"},
                ],
            },
        )
        assert len(env.chat_context.resource_contexts) == 2


class TestResourceContextTaggedUnion:
    def test_vault_file_missing_file_path_raises(self):
        with pytest.raises(ValidationError):
            UserInputEnvelope(
                chat_context={"resource_contexts": [{"kind": "vault_file"}]},
            )

    def test_web_page_missing_url_raises(self):
        with pytest.raises(ValidationError):
            UserInputEnvelope(
                chat_context={"resource_contexts": [{"kind": "web_page"}]},
            )

    def test_selected_text_missing_text_raises(self):
        with pytest.raises(ValidationError):
            UserInputEnvelope(
                chat_context={"resource_contexts": [{"kind": "selected_text"}]},
            )

    def test_unknown_kind_raises(self):
        with pytest.raises(ValidationError):
            UserInputEnvelope(
                chat_context={
                    "resource_contexts": [{"kind": "unknown_kind"}],
                },
            )
