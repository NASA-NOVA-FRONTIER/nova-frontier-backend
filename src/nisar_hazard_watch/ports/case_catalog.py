from typing import Protocol

from nisar_hazard_watch.models.case import CaseView
from nisar_hazard_watch.models.case_series import CaseSeriesView


class CaseCatalog(Protocol):
    async def cases(self) -> list[CaseView]:
        """The known cases in the source's order, layer URLs absolute on the source."""
        ...

    async def series(self, case_id: str) -> CaseSeriesView:
        """One known case's measured series: per-date values or pair intervals."""
        ...
