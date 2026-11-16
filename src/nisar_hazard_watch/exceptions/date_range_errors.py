from nisar_hazard_watch.constants.errors import ReasonCode
from nisar_hazard_watch.exceptions.app_error import AppError


class InvalidDateRangeError(AppError):
    status_code = 422
    reason_code = ReasonCode.INVALID_DATE_RANGE
    title = "Invalid date range"
