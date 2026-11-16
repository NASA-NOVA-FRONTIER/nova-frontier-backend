from collections.abc import Mapping

from nisar_hazard_watch.constants.errors import ReasonCode


class AppError(Exception):
    status_code: int = 500
    reason_code: ReasonCode = ReasonCode.INTERNAL_ERROR
    title: str = "Internal Server Error"

    def __init__(self, detail: str, headers: Mapping[str, str] | None = None) -> None:
        super().__init__(detail)
        self.detail = detail
        self.headers = dict(headers or {})
