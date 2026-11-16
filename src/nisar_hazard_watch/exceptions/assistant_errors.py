from nisar_hazard_watch.constants.errors import ReasonCode
from nisar_hazard_watch.exceptions.app_error import AppError


class AssistantUnavailableError(AppError):
    status_code = 503
    reason_code = ReasonCode.ASSISTANT_UNAVAILABLE
    title = "Assistant unavailable"


class AssistantBudgetExhaustedError(AppError):
    status_code = 429
    reason_code = ReasonCode.ASSISTANT_BUDGET_EXHAUSTED
    title = "Assistant budget used"


class AssistantUpstreamError(AppError):
    status_code = 502
    reason_code = ReasonCode.UPSTREAM_ASSISTANT_ERROR
    title = "Assistant model unavailable"
