from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.openapi.models import Example

from nisar_hazard_watch.api.dependencies import ExplorationServiceDep, RateLimit
from nisar_hazard_watch.constants.explorations import DEFAULT_COVERAGE_LENS, Lens
from nisar_hazard_watch.constants.sar import SERIES_KEY_PATTERN, Direction
from nisar_hazard_watch.models.exploration import CoverageView

router = APIRouter(tags=["coverage"])

Longitude = Annotated[float, Query(ge=-180, le=180, allow_inf_nan=False)]
Latitude = Annotated[float, Query(ge=-90, le=90, allow_inf_nan=False)]
# Send the same lens and opticalEvidence as the exploration would, or the cache check can't match.
# Without opticalEvidence, the service assumes what the frontend sends for that lens.
LensQuery = Annotated[Lens, Query()]
OpticalEvidence = Annotated[bool | None, Query(alias="opticalEvidence")]
# Both or neither, 36 to 365 days apart and ending no later than today; none = the default window.
StartDate = Annotated[
    date | None,
    Query(
        alias="startDate",
        openapi_examples={"range": Example(summary="A user's range", value="2026-06-01")},
    ),
]
EndDate = Annotated[
    date | None,
    Query(
        alias="endDate",
        openapi_examples={"range": Example(summary="A user's range", value="2026-10-31")},
    ),
]

# Either or both, from a previous answer's `series`; none = the planner's own pick. Send the same
# ones as the exploration would, or the cache check can't match.
DirectionQuery = Annotated[
    Direction | None,
    Query(openapi_examples={"descending": Example(summary="Descending passes", value="D")}),
]
SeriesKey = Annotated[
    str | None,
    Query(
        alias="seriesKey",
        pattern=SERIES_KEY_PATTERN,
        openapi_examples={"series": Example(summary="One series", value="084_A_018_4005_DHDH")},
    ),
]


@router.get("", response_model=CoverageView, dependencies=[RateLimit])
async def get_coverage(
    lon: Longitude,
    lat: Latitude,
    service: ExplorationServiceDep,
    lens: LensQuery = DEFAULT_COVERAGE_LENS,
    optical_evidence: OpticalEvidence = None,
    start_date: StartDate = None,
    end_date: EndDate = None,
    direction: DirectionQuery = None,
    series_key: SeriesKey = None,
) -> CoverageView:
    return await service.coverage(
        geometry={"type": "Point", "coordinates": [lon, lat]},
        lens=lens,
        optical_evidence=optical_evidence,
        start_date=start_date,
        end_date=end_date,
        direction=direction,
        series_key=series_key,
    )
