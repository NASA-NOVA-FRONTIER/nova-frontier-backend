import pytest

from nisar_hazard_watch.constants.sar import Direction
from nisar_hazard_watch.utils.series_choice import series_choice_problem


@pytest.mark.parametrize(
    ("direction", "series_key"),
    [
        (None, None),
        (Direction.DESCENDING, None),
        (None, "084_A_018_4005_DHDH"),
        (Direction.ASCENDING, "084_A_018_4005_DHDH"),
        # Not a series key: the request's pattern refuses it, not this check.
        (Direction.ASCENDING, "not-a-key"),
    ],
)
def test_a_choice_that_can_hold_has_no_problem(
    direction: Direction | None, series_key: str | None
) -> None:
    # Act / Assert
    assert series_choice_problem(direction=direction, series_key=series_key) is None


def test_a_series_from_the_other_direction_is_named_as_the_problem() -> None:
    # Act
    problem = series_choice_problem(direction=Direction.ASCENDING, series_key="063_D_072_4005_DHDH")

    # Assert
    assert problem == "seriesKey 063_D_072_4005_DHDH is not in direction A"
