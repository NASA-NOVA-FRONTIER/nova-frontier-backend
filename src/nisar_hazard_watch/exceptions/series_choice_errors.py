from nisar_hazard_watch.constants.errors import ReasonCode
from nisar_hazard_watch.exceptions.app_error import AppError


class InvalidSeriesChoiceError(AppError):
    status_code = 422
    reason_code = ReasonCode.INVALID_REQUEST
    title = "Invalid series choice"
