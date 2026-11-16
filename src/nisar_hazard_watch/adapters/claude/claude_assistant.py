import logging
from collections.abc import AsyncIterator

from anthropic import APIConnectionError, APIStatusError, AsyncAnthropic
from anthropic.types.beta import (
    BetaAssistantMessageParam,
    BetaMessageParam,
    BetaUsage,
    BetaUserMessageParam,
)

from nisar_hazard_watch.constants.assistant import (
    ASSISTANT_EFFORT,
    ASSISTANT_MAX_OUTPUT_TOKENS,
    FALLBACK_BETA,
    FALLBACK_MODELS,
)
from nisar_hazard_watch.exceptions.assistant_errors import AssistantUpstreamError
from nisar_hazard_watch.ports.assistant_model import (
    AnswerDelta,
    AnswerEvent,
    AnswerFinished,
    PromptTurn,
)

logger = logging.getLogger(__name__)


def billed_tokens(usage: BetaUsage) -> int:
    """Every token of the answer, including attempts a server-side fallback replaced."""
    if usage.iterations:
        return sum(
            item.input_tokens
            + item.output_tokens
            + item.cache_creation_input_tokens
            + item.cache_read_input_tokens
            for item in usage.iterations
        )
    return (
        usage.input_tokens
        + usage.output_tokens
        + (usage.cache_creation_input_tokens or 0)
        + (usage.cache_read_input_tokens or 0)
    )


def _message(turn: PromptTurn) -> BetaMessageParam:
    if turn.role == "user":
        return BetaUserMessageParam(role="user", content=turn.text)
    return BetaAssistantMessageParam(role="assistant", content=turn.text)


class ClaudeAssistant:
    """Nova's answers from Claude through the Anthropic SDK, streamed as they are written."""

    def __init__(self, client: AsyncAnthropic, model: str) -> None:
        self._client = client
        self._model = model

    async def answer(self, system: str, turns: list[PromptTurn]) -> AsyncIterator[AnswerEvent]:
        messages = [_message(turn=turn) for turn in turns]
        try:
            async with self._client.beta.messages.stream(
                model=self._model,
                max_tokens=ASSISTANT_MAX_OUTPUT_TOKENS,
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                messages=messages,
                output_config={"effort": ASSISTANT_EFFORT},
                # A declined answer is re-run on Anthropic's recommended model inside the same call.
                **(
                    {"betas": [FALLBACK_BETA], "fallbacks": "default"}
                    if self._model in FALLBACK_MODELS
                    else {}
                ),
            ) as stream:
                async for text in stream.text_stream:
                    yield AnswerDelta(text=text)
                final = await stream.get_final_message()
        except APIStatusError as exc:
            # Status only: no question, screen summary or key reaches the logs.
            logger.warning("assistant model answered %s", exc.status_code)
            raise AssistantUpstreamError(f"the assistant model answered {exc.status_code}") from exc
        except APIConnectionError as exc:
            logger.warning("assistant model unreachable: %s", type(exc).__name__)
            raise AssistantUpstreamError("the assistant model could not be reached") from exc
        yield AnswerFinished(
            stop_reason=final.stop_reason, model=final.model, tokens=billed_tokens(final.usage)
        )
