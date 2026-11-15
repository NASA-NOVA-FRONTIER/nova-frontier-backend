from typing import Annotated, Literal

from pydantic import ConfigDict, Field, StringConstraints

from nisar_hazard_watch.constants.assistant import (
    MAX_FACTS,
    MAX_HISTORY_TURNS,
    MAX_LIMITATIONS,
    MAX_LONG_TEXT,
    MAX_MESSAGE_CHARS,
    MAX_SHORT_TEXT,
    MAX_SOURCES,
    MAX_TURN_CHARS,
)
from nisar_hazard_watch.models.base_model import CamelModel

ShortText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=MAX_SHORT_TEXT)]
LongText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=MAX_LONG_TEXT)]


class StrictModel(CamelModel):
    model_config = ConfigDict(extra="forbid")


class AssistantTurn(StrictModel):
    role: Literal["user", "assistant"]
    content: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_TURN_CHARS)
    ]


class ContextFact(StrictModel):
    label: ShortText
    value: LongText
    source: LongText | None = None


class AssistantContext(StrictModel):
    """What the screen shows, summarised by the frontend. Data for the model, never instructions."""

    kind: Literal["case", "exploration", "none"]
    title: ShortText = ""
    question: ShortText = ""
    result: LongText = ""
    dates: ShortText = ""
    provenance: LongText = ""
    facts: list[ContextFact] = Field(default_factory=list, max_length=MAX_FACTS)
    limitations: list[LongText] = Field(default_factory=list, max_length=MAX_LIMITATIONS)
    sources: list[LongText] = Field(default_factory=list, max_length=MAX_SOURCES)


class AssistantRequest(StrictModel):
    message: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_MESSAGE_CHARS)
    ]
    history: list[AssistantTurn] = Field(default_factory=list, max_length=MAX_HISTORY_TURNS)
    context: AssistantContext
