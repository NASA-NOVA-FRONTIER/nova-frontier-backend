import re

from nisar_hazard_watch.constants.sar import SERIES_KEY_PATTERN, Direction


def series_choice_problem(direction: Direction | None, series_key: str | None) -> str | None:
    """Why a direction and a series key can't both hold, or None when they agree."""
    if direction is None or series_key is None:
        return None
    match = re.match(SERIES_KEY_PATTERN, series_key)
    if match is None or match["direction"] == direction.value:
        return None
    return f"seriesKey {series_key} is not in direction {direction.value}"
