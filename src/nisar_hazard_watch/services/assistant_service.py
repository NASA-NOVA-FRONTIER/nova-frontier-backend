import logging
from collections.abc import AsyncIterator, Callable
from datetime import UTC, date, datetime

from nisar_hazard_watch.constants.assistant import (
    ASSISTANT_BUDGET_DETAIL,
    ASSISTANT_UNAVAILABLE_DETAIL,
)
from nisar_hazard_watch.exceptions.assistant_errors import (
    AssistantBudgetExhaustedError,
    AssistantUnavailableError,
)
from nisar_hazard_watch.models.assistant import AssistantRequest, AssistantStatusView
from nisar_hazard_watch.ports.assistant_model import AnswerEvent, AnswerFinished, AssistantModel
from nisar_hazard_watch.services.assistant_prompt import SYSTEM_PROMPT, prompt_turns

logger = logging.getLogger(__name__)


def _utc_today() -> date:
    return datetime.now(tz=UTC).date()


class AssistantService:
    """Nova's answers from Claude, within a daily token ceiling for the whole process.

    Without a model (no API key) every call is refused; the frontend keeps its rule answers.
    """

    def __init__(
        self,
        model: AssistantModel | None,
        daily_token_limit: int,
        model_name: str | None = None,
        today: Callable[[], date] = _utc_today,
    ) -> None:
        self._model = model
        self._model_name = model_name
        self._daily_token_limit = daily_token_limit
        self._today = today
        self._day = today()
        self._used = 0

    @property
    def used_today(self) -> int:
        self._roll_over()
        return self._used

    def status(self) -> AssistantStatusView:
        """Available when a model is configured and today's budget is not used up."""
        available = self._model is not None and self.used_today < self._daily_token_limit
        return AssistantStatusView(
            available=available, model=self._model_name if self._model is not None else None
        )

    def ensure_available(self) -> AssistantModel:
        """Refuses before any answer starts, so the caller still gets a problem response."""
        if self._model is None:
            raise AssistantUnavailableError(ASSISTANT_UNAVAILABLE_DETAIL)
        if self.used_today >= self._daily_token_limit:
            raise AssistantBudgetExhaustedError(ASSISTANT_BUDGET_DETAIL)
        return self._model

    async def answer(self, request: AssistantRequest) -> AsyncIterator[AnswerEvent]:
        model = self.ensure_available()
        async for event in model.answer(system=SYSTEM_PROMPT, turns=prompt_turns(request=request)):
            if isinstance(event, AnswerFinished):
                self._roll_over()
                self._used += event.tokens
                logger.info(
                    "assistant answered model=%s stop=%s tokens=%d used_today=%d",
                    event.model,
                    event.stop_reason,
                    event.tokens,
                    self._used,
                )
            yield event

    def _roll_over(self) -> None:
        today = self._today()
        if today != self._day:
            self._day = today
            self._used = 0
