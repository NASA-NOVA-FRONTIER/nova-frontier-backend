from datetime import date

from nisar_hazard_watch.constants.sar import DATE_RANGE_MAX_DAYS, DATE_RANGE_MIN_DAYS
from nisar_hazard_watch.exceptions.date_range_errors import InvalidDateRangeError

DateRange = tuple[date, date]


def checked_date_range(start: date | None, end: date | None, today: date) -> DateRange | None:
    """The user's window, or None for the default one; raises when it can't be planned."""
    if start is None and end is None:
        return None
    if start is None or end is None:
        raise InvalidDateRangeError("startDate and endDate go together")
    if end < start:
        raise InvalidDateRangeError(f"endDate {end} is before startDate {start}")
    if end > today:
        raise InvalidDateRangeError(f"endDate {end} is after today ({today}, UTC)")
    span = (end - start).days
    if not DATE_RANGE_MIN_DAYS <= span <= DATE_RANGE_MAX_DAYS:
        raise InvalidDateRangeError(
            f"the range spans {span} days; it must span {DATE_RANGE_MIN_DAYS} to "
            f"{DATE_RANGE_MAX_DAYS} days"
        )
    return start, end
