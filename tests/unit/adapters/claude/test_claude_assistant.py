from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any, cast

import httpx2
import pytest
from anthropic import APIConnectionError, APIStatusError, AsyncAnthropic
from anthropic.types.beta import BetaUsage

from nisar_hazard_watch.adapters.claude.claude_assistant import ClaudeAssistant, billed_tokens
from nisar_hazard_watch.constants.assistant import (
    ASSISTANT_EFFORT,
    ASSISTANT_MAX_OUTPUT_TOKENS,
    FALLBACK_BETA,
)
from nisar_hazard_watch.exceptions.assistant_errors import AssistantUpstreamError
from nisar_hazard_watch.ports.assistant_model import AnswerDelta, AnswerEvent, PromptTurn

SYSTEM = "rules"
TURNS = [
    PromptTurn(role="user", text="What is HH?"),
    PromptTurn(role="assistant", text="A channel."),
    PromptTurn(role="user", text="And HV?"),
]
REQUEST = httpx2.Request(method="POST", url="https://api.anthropic.com/v1/messages")


class FakeStream:
    def __init__(self, texts: list[str], final: object) -> None:
        self._texts = texts
        self._final = final

    @property
    def text_stream(self) -> AsyncIterator[str]:
        async def texts() -> AsyncIterator[str]:
            for text in self._texts:
                yield text

        return texts()

    async def get_final_message(self) -> object:
        return self._final


class FakeManager:
    def __init__(self, stream: FakeStream | None, error: Exception | None) -> None:
        self._stream = stream
        self._error = error

    async def __aenter__(self) -> FakeStream:
        if self._error is not None:
            raise self._error
        assert self._stream is not None
        return self._stream

    async def __aexit__(self, *_: object) -> None:
        return None


class FakeClient:
    """Just enough of AsyncAnthropic: beta.messages.stream(**request)."""

    def __init__(self, stream: FakeStream | None = None, error: Exception | None = None) -> None:
        self.requests: list[dict[str, Any]] = []

        def stream_call(**request: Any) -> FakeManager:
            self.requests.append(request)
            return FakeManager(stream=stream, error=error)

        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=stream_call))


def final(stop_reason: str = "end_turn") -> object:
    usage = BetaUsage(input_tokens=900, output_tokens=120, cache_read_input_tokens=30)
    return SimpleNamespace(stop_reason=stop_reason, model="claude-opus-5-5", usage=usage)


async def collect(assistant: ClaudeAssistant) -> list[AnswerEvent]:
    return [event async for event in assistant.answer(system=SYSTEM, turns=TURNS)]


def assistant_with(client: FakeClient, model: str = "claude-opus-5-5") -> ClaudeAssistant:
    return ClaudeAssistant(client=cast(AsyncAnthropic, client), model=model)


async def test_it_streams_the_text_then_says_how_it_stopped_and_what_it_cost() -> None:
    # Arrange
    client = FakeClient(stream=FakeStream(texts=["HV is ", "cross-polarized."], final=final()))

    # Act
    events = await collect(assistant=assistant_with(client=client))

    # Assert
    assert events[:2] == [AnswerDelta(text="HV is "), AnswerDelta(text="cross-polarized.")]
    finished = events[-1]
    assert not isinstance(finished, AnswerDelta)
    assert (finished.stop_reason, finished.model, finished.tokens) == (
        "end_turn",
        "claude-opus-5-5",
        1050,
    )


async def test_the_request_caps_output_uses_low_effort_caches_the_rules_and_falls_back() -> None:
    # Arrange
    client = FakeClient(stream=FakeStream(texts=[], final=final()))

    # Act
    await collect(assistant=assistant_with(client=client))

    # Assert
    request = client.requests[0]
    assert request["model"] == "claude-opus-5-5"
    assert request["max_tokens"] == ASSISTANT_MAX_OUTPUT_TOKENS
    assert request["output_config"] == {"effort": ASSISTANT_EFFORT}
    assert request["system"] == [
        {"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}
    ]
    assert [message["role"] for message in request["messages"]] == ["user", "assistant", "user"]
    assert (request["betas"], request["fallbacks"]) == ([FALLBACK_BETA], "default")


async def test_a_model_without_server_side_fallback_is_asked_without_it() -> None:
    # Arrange
    client = FakeClient(stream=FakeStream(texts=[], final=final()))

    # Act
    await collect(assistant=assistant_with(client=client, model="claude-haiku-5-5"))

    # Assert
    assert "fallbacks" not in client.requests[0]
    assert "betas" not in client.requests[0]


@pytest.mark.parametrize(
    argnames="error",
    argvalues=[
        APIStatusError(
            message="overloaded",
            response=httpx2.Response(status_code=529, request=REQUEST),
            body=None,
        ),
        APIConnectionError(request=REQUEST),
    ],
)
async def test_api_failures_become_an_upstream_error(error: Exception) -> None:
    # Arrange
    client = FakeClient(error=error)

    # Act / Assert
    with pytest.raises(expected_exception=AssistantUpstreamError):
        await collect(assistant=assistant_with(client=client))


def test_tokens_of_a_replaced_attempt_still_count() -> None:
    # Arrange
    attempt = {"cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
    usage = BetaUsage.model_validate(
        {
            "input_tokens": 500,
            "output_tokens": 50,
            "iterations": [
                {**attempt, "type": "message", "input_tokens": 500, "output_tokens": 10},
                {
                    **attempt,
                    "type": "fallback_message",
                    "model": "claude-opus-4-8",
                    "input_tokens": 500,
                    "output_tokens": 50,
                },
            ],
        }
    )

    # Act / Assert
    assert billed_tokens(usage=usage) == 1060
