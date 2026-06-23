from typing import TYPE_CHECKING, Any

from . import conf_manager, clock, user_doc

if TYPE_CHECKING:
    from ..gateway.channels.channel import ChannelMetadata


def get_tools(name: str | None = None) -> list:
    if name == "conf_manager":
        return [conf_manager.get_schema, conf_manager.get_config, conf_manager.set_config]
    if name == "clock":
        return [clock.get_datetime]
    if name == "user_doc":
        return [user_doc.user_doc_get, user_doc.user_doc_set]
    return []


def get_all_tools() -> list:
    return [
        conf_manager.get_schema,
        conf_manager.get_config,
        conf_manager.set_config,
        user_doc.user_doc_get,
        user_doc.user_doc_set,
        clock.get_datetime,
    ]


def build_tools(metadata: "ChannelMetadata", channel: Any) -> list:
    """按 channel 能力动态构造 tools 列表。

    当 channel 支持 mp3 时，附加 voice_speak 工具。
    """
    from .voice import make_voice_speak_tool

    tools = get_all_tools()
    if "mp3" in metadata.supported_sound_media_format:
        tools.append(make_voice_speak_tool(channel))
    return tools
