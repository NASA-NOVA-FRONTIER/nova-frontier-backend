from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Literal, Protocol


@dataclass(frozen=True)
class PromptTurn:
    role: Literal["user", "assistant"]
    text: str


@dataclass(frozen=True)
class AnswerDelta:
    text: str


@dataclass(frozen=True)
class AnswerFinished:
    stop_reason: str | None
    model: str
    tokens: int


AnswerEvent = AnswerDelta | AnswerFinished


class AssistantModel(Protocol):
    """A language model that writes an answer as it goes, then says how it stopped."""

    def answer(self, system: str, turns: list[PromptTurn]) -> AsyncIterator[AnswerEvent]: ...
