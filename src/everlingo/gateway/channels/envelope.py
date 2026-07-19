from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field

TaskKind = Literal["translate", "look_up", "none"]


class ChatPart(BaseModel):
    message: str = ""


class SelectionPart(BaseModel):
    text: str = ""


class ContextPart(BaseModel):
    text: str = ""
    kind: Literal["paragraph", "page", "screen", "plain"] = "plain"


class SourcePlain(BaseModel):
    kind: Literal["plain"] = "plain"


class SourceWeb(BaseModel):
    kind: Literal["web"] = "web"
    url: str = ""
    title: str = ""


class SourcePdf(BaseModel):
    kind: Literal["pdf"] = "pdf"
    file_path: str = ""
    page_number: int | None = None


class SourceEpub(BaseModel):
    kind: Literal["epub"] = "epub"
    book_id: str = ""


class SourceIosApp(BaseModel):
    kind: Literal["ios_app"] = "ios_app"
    bundle_id: str = ""


SourcePart = Annotated[
    Union[SourcePlain, SourceWeb, SourcePdf, SourceEpub, SourceIosApp],
    Field(discriminator="kind")
]


class DevicePart(BaseModel):
    platform: Literal["chrome_ext", "ios_app", "pdf_reader", "web", "cli"] = "cli"
    locale: str | None = None
    timezone: str | None = None


class UserInputEnvelope(BaseModel):
    schema_version: int = 1
    task: TaskKind = "none"
    chat: ChatPart = ChatPart()
    selection: SelectionPart = SelectionPart()
    context: ContextPart = ContextPart()
    source: SourcePart = Field(default_factory=SourcePlain)
    device: DevicePart | None = None


def wrap_plain_text(text: str) -> UserInputEnvelope:
    return UserInputEnvelope(
        task="none",
        chat=ChatPart(message=text),
        source=SourcePlain(),
    )


def render_envelope_to_message_text(env: UserInputEnvelope) -> str:
    json_str = env.model_dump_json(ensure_ascii=False)
    return f"<envelope>\n{json_str}\n</envelope>"
