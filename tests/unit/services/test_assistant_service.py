from collections.abc import AsyncIterator
from datetime import date

import pytest

from nisar_hazard_watch.exceptions.assistant_errors import (
    AssistantBudgetExhaustedError,
    AssistantUnavailableError,
)
from nisar_hazard_watch.models.assistant import AssistantContext, AssistantRequest
from nisar_hazard_watch.ports.assistant_model import (
    AnswerDelta,
    AnswerEvent,
    AnswerFinished,
    PromptTurn,
)
from nisar_hazard_watch.services.assistant_prompt import SYSTEM_PROMPT
from nisar_hazard_watch.services.assistant_service import AssistantService

REQUEST = AssistantRequest(message="What is HH?", context=AssistantContext(kind="none"))
TOKENS = 1200
DAY_ONE = date(2026, 11, 15)
DAY_TWO = date(2026, 11, 16)


class FakeModel:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[PromptTurn]]] = []

    async def answer(self, system: str, turns: list[PromptTurn]) -> AsyncIterator[AnswerEvent]:
        self.calls.append((system, turns))
        yield AnswerDelta(text="HH is ")
        yield AnswerDelta(text="the co-polarized channel.")
        yield AnswerFinished(stop_reason="end_turn", model="claude-opus-5-5", tokens=TOKENS)


async def collect(service: AssistantService) -> list[AnswerEvent]:
    return [event async for event in service.answer(request=REQUEST)]


def test_without_a_model_the_assistant_is_unavailable() -> None:
    # Arrange
    service = AssistantService(model=None, daily_token_limit=10_000)

    # Act / Assert
    with pytest.raises(expected_exception=AssistantUnavailableError):
        service.ensure_available()


async def test_the_answer_streams_with_the_fixed_system_prompt_and_counts_tokens() -> None:
    # Arrange
    model = FakeModel()
    service = AssistantService(model=model, daily_token_limit=10_000)

    # Act
    events = await collect(service=service)

    # Assert
    assert [event.text for event in events if isinstance(event, AnswerDelta)] == [
        "HH is ",
        "the co-polarized channel.",
    ]
    assert model.calls[0][0] == SYSTEM_PROMPT
    assert service.used_today == TOKENS


async def test_once_the_daily_ceiling_is_reached_it_refuses_until_the_next_utc_day() -> None:
    # Arrange
    days = iter([DAY_ONE, DAY_ONE, DAY_ONE, DAY_ONE, DAY_TWO])
    service = AssistantService(
        model=FakeModel(), daily_token_limit=TOKENS, today=lambda: next(days)
    )
    await collect(service=service)

    # Act / Assert
    with pytest.raises(expected_exception=AssistantBudgetExhaustedError):
        service.ensure_available()
    assert service.ensure_available() is not None


async def test_the_status_turns_unavailable_once_the_budget_is_used() -> None:
    # Arrange
    service = AssistantService(model=FakeModel(), daily_token_limit=TOKENS, model_name="m")
    before = service.status()

    # Act
    await collect(service=service)

    # Assert
    assert (before.available, before.model) == (True, "m")
    assert service.status().available is False
