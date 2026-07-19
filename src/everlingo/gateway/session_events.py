from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol

from everlingo.gateway.channels.envelope import UserInputEnvelope


class SessionEvent:
    """Base type for all events flowing through Session's event queue."""


@dataclass
class UserMessage(SessionEvent):
    """User input from channel.recv_envelope()."""
    envelope: UserInputEnvelope


@dataclass
class SystemNotice(SessionEvent):
    """System-triggered notification (e.g. from Memory Writer)."""
    source: str                     # "memory_writer"
    updated_files: list[str]        # vault file paths, e.g. ["items/vocab/ufo.md"]
    update_summary: str             # brief description, e.g. "新建词条 ufo，含释义与例句"
    title: str                   # title, e.g. "ufo"
    lang: str                       # target language code, e.g. "en"


@dataclass
class QuitEvent(SessionEvent):
    """Signal to exit the run loop (channel closed)."""


class NoticeSink(Protocol):
    """Protocol for injecting session-bound notices from background agents.

    Memory Writer Agent etc. hold a reference to this protocol
    and call notify() after successful async operations.
    """

    def notify(
        self,
        *,
        session_id: str,
        source: str,
        updated_files: list[str],
        update_summary: str,
        title: str,
        lang: str,
    ) -> None:
        ...
