import pytest
from pydantic import ValidationError

from everlingo.gateway.channels.envelope import (
    UserInputEnvelope,
    SourcePlain,
    SourceWeb,
    ScreenshotPart,
    render_envelope_to_message_text,
    wrap_plain_text,
)


class TestWrapPlainText:
    def test_wraps_plain_text(self):
        env = wrap_plain_text("hello")
        assert env.task == "none"
        assert env.chat.message == "hello"
        assert isinstance(env.source, SourcePlain)
        assert env.selection.text == ""
        assert env.context.text == ""
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
        env.selection.text = "bank"
        env.context.text = "I sat on the bank of the river."

        rendered = render_envelope_to_message_text(env)
        assert '"task":"translate"' in rendered
        assert '为什么这里不是银行' in rendered
        assert '"text":"bank"' in rendered
        assert '"kind":"web"' in rendered
        assert '"url":"https://example.com"' in rendered

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
        env = UserInputEnvelope(
            source=SourceWeb(url="http://test.com", surface="sidecar")
        )
        assert env.source.surface == "sidecar"

    def test_web_source_invalid_surface_raises(self):
        with pytest.raises(ValidationError):
            SourceWeb(url="http://test.com", surface="full_page")

    def test_unknown_kind_raises(self):
        with pytest.raises(ValidationError):
            UserInputEnvelope(source={"kind": "unknown"})


class TestUserInputEnvelopeDefaults:
    def test_all_defaults(self):
        env = UserInputEnvelope()
        assert env.task == "none"
        assert env.chat.message == ""
        assert env.selection.text == ""
        assert env.context.text == ""
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


class TestScreenshotPart:
    def test_screenshot_none_by_default(self):
        env = UserInputEnvelope()
        assert env.context.screenshot is None

    def test_screenshot_with_fields(self):
        env = UserInputEnvelope(
            context={"screenshot": ScreenshotPart(data_url="data:image/png;base64,abc")}
        )
        assert env.context.screenshot is not None
        assert env.context.screenshot.data_url == "data:image/png;base64,abc"
        assert env.context.screenshot.mime == "image/png"

    def test_screenshot_roundtrip(self):
        env = UserInputEnvelope(
            context={"screenshot": ScreenshotPart(data_url="data:image/png;base64,abc", mime="image/png")}
        )
        rendered = render_envelope_to_message_text(env)
        assert "data:image/png;base64,abc" in rendered
        assert '"mime":"image/png"' in rendered
