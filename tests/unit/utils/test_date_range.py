from datetime import date, timedelta

import pytest

from nisar_hazard_watch.constants.errors import ReasonCode
from nisar_hazard_watch.constants.sar import DATE_RANGE_MAX_DAYS, DATE_RANGE_MIN_DAYS
from nisar_hazard_watch.exceptions.date_range_errors import InvalidDateRangeError
from nisar_hazard_watch.utils.date_range import checked_date_range

TODAY = date(2026, 11, 12)
START = date(2026, 6, 1)
END = date(2026, 10, 31)


def test_no_dates_mean_the_default_window() -> None:
    # Arrange / Act
    checked = checked_date_range(start=None, end=None, today=TODAY)

    # Assert
    assert checked is None


def test_a_valid_range_comes_back_as_it_was_sent() -> None:
    # Arrange / Act
    checked = checked_date_range(start=START, end=END, today=TODAY)

    # Assert
    assert checked == (START, END)


@pytest.mark.parametrize(
    ("start", "end"),
    [
        pytest.param(START, TODAY, id="ends-today"),
        pytest.param(END - timedelta(days=DATE_RANGE_MIN_DAYS), END, id="shortest"),
        pytest.param(END - timedelta(days=DATE_RANGE_MAX_DAYS), END, id="longest"),
    ],
)
def test_the_edges_of_the_limits_are_accepted(start: date, end: date) -> None:
    # Arrange / Act
    checked = checked_date_range(start=start, end=end, today=TODAY)

    # Assert
    assert checked == (start, end)


@pytest.mark.parametrize(
    ("start", "end"),
    [
        pytest.param(START, None, id="start-only"),
        pytest.param(None, END, id="end-only"),
        pytest.param(END, START, id="end-before-start"),
        pytest.param(START, TODAY + timedelta(days=1), id="ends-after-today"),
        pytest.param(END - timedelta(days=DATE_RANGE_MIN_DAYS - 1), END, id="too-short"),
        pytest.param(END - timedelta(days=DATE_RANGE_MAX_DAYS + 1), END, id="too-long"),
    ],
)
def test_a_range_that_cant_be_planned_is_refused_with_its_own_reason(
    start: date | None, end: date | None
) -> None:
    # Arrange / Act
    with pytest.raises(expected_exception=InvalidDateRangeError) as refused:
        checked_date_range(start=start, end=end, today=TODAY)

    # Assert
    assert refused.value.reason_code is ReasonCode.INVALID_DATE_RANGE
    assert refused.value.status_code == 422
